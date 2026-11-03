"""Campaigns (CALL-15): list -> create (CSV / pasted rows) -> start -> live progress -> export.

Calls are placed by the dialer worker (``mitra_core.dialer.worker``), which runs
``compliance.check`` before every dial. Owners and managers manage campaigns; staff can view.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.dialer import campaigns as svc
from mitra_core.dialer import consent as list_consent
from mitra_core.dialer.csvimport import SAMPLE_CSV, ListError, ParsedList, parse_list
from mitra_core.dialer.settings import DialerSettings, get_dialer_settings
from mitra_core.errors import AppError, not_found
from mitra_core.models import Employee
from mitra_core.models.campaign import Campaign, DialerConfig
from mitra_core.models.enums import Locale, MemberRole
from mitra_core.schemas.campaign import (
    CampaignCreatedOut,
    CampaignIn,
    CampaignList,
    CampaignOut,
    CampaignPatch,
    ConsentIn,
    ConsentOut,
    ConsentTextOut,
    DialerSettingsIn,
    DialerSettingsOut,
    ListIn,
    ListPreviewOut,
    Progress,
    RowErrorOut,
    SampleRow,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role
from mitra_core.telephony.compliance import owner_summary
from mitra_core.telephony.enums import CallPurpose

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)
SAMPLE_ROWS = 5


def _parse(body: ListIn, settings: DialerSettings) -> ParsedList:
    try:
        return parse_list(
            body.text,
            phone_column=body.phone_column,
            name_column=body.name_column,
            column_map=body.column_map,
            max_rows=settings.max_contacts,
        )
    except ListError as e:
        raise AppError(422, "invalid_list", str(e)) from e


def _campaign_error(e: svc.CampaignError) -> AppError:
    return AppError(409, e.code, str(e))


async def _get(session: AsyncSession, tenant: Tenant, campaign_id: uuid.UUID) -> Campaign:
    campaign = await session.scalar(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.business_id == tenant.business_id
        )
    )
    if campaign is None:
        raise not_found("Campaign")
    return campaign


async def _out(
    session: AsyncSession, campaign: Campaign, settings: DialerSettings, now: datetime
) -> CampaignOut:
    channels = await svc.channels_for(session, campaign.business_id, settings.default_channels)
    p = await svc.progress(session, campaign, channels, now)
    employee = await session.get(Employee, campaign.employee_id) if campaign.employee_id else None
    # Deferrals are temporary and skips are counted separately: neither is a "block".
    deferred = {
        "outside_hours",
        "daily_cap",
        "weekly_cap",
        "called_recently",
        svc.REMOVED_AT_APPROVAL,
    }
    blocked = {k: v for k, v in p.reasons.items() if k not in deferred}
    return CampaignOut(
        id=campaign.id,
        name=campaign.name,
        employee_id=campaign.employee_id,
        employee_name=employee.name if employee else None,
        purpose=campaign.purpose,
        status=campaign.status,
        pause_reason=campaign.pause_reason,
        column_map=dict(campaign.column_map),
        variables=sorted(set(campaign.column_map.values())),
        skip_recent_days=campaign.skip_recent_days,
        calling_days=list(campaign.calling_days),
        holidays=list(campaign.holidays),
        retry_ladder=list(campaign.retry_ladder),
        ends_on=campaign.ends_on,
        avg_call_seconds=campaign.avg_call_seconds,
        approval_id=campaign.approval_id,
        consent=(
            ConsentOut(
                scope=campaign.consent_scope,
                text=campaign.consent_text or "",
                text_version=campaign.consent_text_version or "",
                by_name=campaign.consent_by_name,
                at=campaign.consent_at,
            )
            if list_consent.is_attested(campaign)
            and campaign.consent_scope is not None
            and campaign.consent_at is not None
            else None
        ),
        created_at=campaign.created_at,
        started_at=campaign.started_at,
        completed_at=campaign.completed_at,
        progress=Progress(
            total=p.total,
            skipped=p.skipped,
            remaining=p.remaining,
            dialing=p.dialing,
            called=p.called,
            blocked=p.blocked,
            done=p.total - p.skipped - p.remaining,
            buckets=p.buckets,
            reasons=p.reasons,
            blocked_summary=owner_summary(blocked),
            eta_minutes=p.eta_minutes,
            starts_at=p.starts_at,
            channels=channels,
        ),
    )


async def _check_employee(session: AsyncSession, tenant: Tenant, employee_id: uuid.UUID) -> None:
    found = await session.scalar(
        select(Employee.id).where(
            Employee.id == employee_id, Employee.business_id == tenant.business_id
        )
    )
    if found is None:
        raise not_found("Employee")


@router.get("/sample.csv", summary="Sample list to fill in")
async def sample_csv(_: Tenant = Depends(require_business)) -> Response:
    return Response(
        SAMPLE_CSV,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="mitra-campaign-sample.csv"'},
    )


@router.get("/settings", response_model=DialerSettingsOut, summary="Calls at the same time")
async def get_settings_(
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> DialerSettingsOut:
    return DialerSettingsOut(
        channels=await svc.channels_for(session, tenant.business_id, settings.default_channels)
    )


@router.put("/settings", response_model=DialerSettingsOut)
async def put_settings(
    body: DialerSettingsIn,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> DialerSettingsOut:
    config = await session.get(DialerConfig, tenant.business_id)
    if config is None:
        session.add(DialerConfig(business_id=tenant.business_id, channels=body.channels))
    else:
        config.channels = body.channels
    await session.commit()
    return DialerSettingsOut(channels=body.channels)


@router.get("/consent-text", response_model=ConsentTextOut, summary="Words the owner ticks")
async def consent_text(
    purpose: CallPurpose = CallPurpose.SERVICE,
    language: Locale | None = None,
    _: Tenant = Depends(require_business),
) -> ConsentTextOut:
    probe = Campaign(purpose=purpose)
    return ConsentTextOut(text=list_consent.wording(probe, language), version=list_consent.VERSION)


@router.post("/preview", response_model=ListPreviewOut, summary="Check a list before importing")
async def preview(
    body: ListIn,
    settings: DialerSettings = Depends(get_dialer_settings),
    _: Tenant = Depends(require_business),
) -> ListPreviewOut:
    parsed = _parse(body, settings)
    return ListPreviewOut(
        headers=parsed.headers,
        phone_column=parsed.phone_column,
        name_column=parsed.name_column,
        column_map=parsed.column_map,
        valid=len(parsed.rows),
        invalid=parsed.invalid,
        duplicates=parsed.duplicates,
        errors=[RowErrorOut(row_number=e.row_number, reason=e.reason) for e in parsed.errors[:50]],
        sample=[
            SampleRow(
                row_number=r.row_number,
                phone_last4=r.phone[-4:],
                name=r.name,
                variables=r.variables,
            )
            for r in parsed.rows[:SAMPLE_ROWS]
        ],
    )


@router.get("", response_model=CampaignList)
async def list_campaigns(
    clock: Clock = Depends(get_clock),
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> CampaignList:
    rows = await session.scalars(
        select(Campaign)
        .where(Campaign.business_id == tenant.business_id)
        .order_by(Campaign.created_at.desc(), Campaign.id)
        .limit(100)
    )
    return CampaignList(items=[await _out(session, c, settings, clock()) for c in rows])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CampaignCreatedOut)
async def create_campaign(
    body: CampaignIn,
    clock: Clock = Depends(get_clock),
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> CampaignCreatedOut:
    await _check_employee(session, tenant, body.employee_id)
    parsed = _parse(body, settings)
    if not parsed.rows:
        raise AppError(422, "invalid_list", "No valid Indian phone numbers in the list")
    campaign = Campaign(
        id=uuid.uuid4(),
        business_id=tenant.business_id,
        employee_id=body.employee_id,
        name=body.name,
        purpose=body.purpose,
        column_map=parsed.column_map,
        skip_recent_days=body.skip_recent_days,
        calling_days=sorted(set(body.calling_days)),
        holidays=sorted(set(body.holidays)),
        retry_ladder=body.retry_ladder,
        ends_on=body.ends_on,
        created_by=tenant.user.id,
    )
    now = clock()
    if body.consent_attested:
        list_consent.attest(campaign, tenant.user, body.consent_language, now)
    session.add(campaign)
    await session.flush()
    added, skipped = await svc.add_contacts(session, campaign, parsed, now)
    out = await _out(session, campaign, settings, clock())
    await session.commit()
    return CampaignCreatedOut(
        campaign=out,
        added=added,
        skipped_recent=skipped,
        invalid=parsed.invalid,
        duplicates=parsed.duplicates,
    )


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: uuid.UUID,
    clock: Clock = Depends(get_clock),
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> CampaignOut:
    return await _out(session, await _get(session, tenant, campaign_id), settings, clock())


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def edit_campaign(
    campaign_id: uuid.UUID,
    body: CampaignPatch,
    clock: Clock = Depends(get_clock),
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> CampaignOut:
    campaign = await _get(session, tenant, campaign_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("employee_id") is not None:
        await _check_employee(session, tenant, changes["employee_id"])
    for key in ("name", "employee_id", "ends_on", "avg_call_seconds"):
        if key in changes and (changes[key] is not None or key == "ends_on"):
            setattr(campaign, key, changes[key])
    if body.calling_days is not None:
        campaign.calling_days = sorted(set(body.calling_days))
    if body.holidays is not None:
        campaign.holidays = sorted(set(body.holidays))
    if body.retry_ladder is not None:
        await svc.set_retry_ladder(session, campaign, body.retry_ladder)
    await session.flush()
    out = await _out(session, campaign, settings, clock())
    await session.commit()
    return out


async def _transition(
    action: str,
    campaign_id: uuid.UUID,
    clock: Clock,
    settings: DialerSettings,
    tenant: Tenant,
    session: AsyncSession,
    consent: ConsentIn | None = None,
) -> CampaignOut:
    campaign = await _get(session, tenant, campaign_id)
    now = clock()
    try:
        if action == "start":
            if consent is not None and consent.consent_attested:
                list_consent.attest(campaign, tenant.user, consent.consent_language, now)
            await svc.start(session, campaign, now, user_id=tenant.user.id)
        elif action == "pause":
            svc.pause(campaign)
        elif action == "resume":
            await svc.resume(session, campaign, now)
        else:
            await svc.cancel(session, campaign, now)
    except svc.CampaignError as e:
        raise _campaign_error(e) from e
    await session.flush()
    out = await _out(session, campaign, settings, clock())
    await session.commit()
    return out


@router.post("/{campaign_id}/start", response_model=CampaignOut)
async def start_campaign(
    campaign_id: uuid.UUID,
    body: ConsentIn | None = None,
    clock: Clock = Depends(get_clock),
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> CampaignOut:
    return await _transition("start", campaign_id, clock, settings, tenant, session, body)


@router.post("/{campaign_id}/pause", response_model=CampaignOut)
async def pause_campaign(
    campaign_id: uuid.UUID,
    clock: Clock = Depends(get_clock),
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> CampaignOut:
    return await _transition("pause", campaign_id, clock, settings, tenant, session)


@router.post("/{campaign_id}/resume", response_model=CampaignOut)
async def resume_campaign(
    campaign_id: uuid.UUID,
    clock: Clock = Depends(get_clock),
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> CampaignOut:
    return await _transition("resume", campaign_id, clock, settings, tenant, session)


@router.post("/{campaign_id}/cancel", response_model=CampaignOut)
async def cancel_campaign(
    campaign_id: uuid.UUID,
    clock: Clock = Depends(get_clock),
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> CampaignOut:
    return await _transition("cancel", campaign_id, clock, settings, tenant, session)
