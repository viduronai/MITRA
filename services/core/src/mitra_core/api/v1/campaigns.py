"""Campaigns (CALL-15): list -> create (CSV / pasted rows) -> start -> live progress -> export.

Calls are placed by the dialer worker (``mitra_core.dialer.worker``), which runs
``compliance.check`` before every dial. Owners and managers manage campaigns; staff can view.
"""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.dialer import campaigns as svc
from mitra_core.dialer.csvimport import SAMPLE_CSV, ListError, ParsedList, parse_list
from mitra_core.dialer.enums import CampaignStatus, ContactStatus, ResultBucket
from mitra_core.dialer.sealing import unseal
from mitra_core.dialer.settings import DialerSettings, get_dialer_settings
from mitra_core.errors import AppError, not_found
from mitra_core.models import Employee
from mitra_core.models.campaign import Campaign, CampaignContact, DialerConfig
from mitra_core.models.enums import MemberRole
from mitra_core.schemas.campaign import (
    CampaignCreatedOut,
    CampaignIn,
    CampaignList,
    CampaignOut,
    CampaignPatch,
    ContactList,
    ContactOut,
    ContactsAddedOut,
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


async def _out(session: AsyncSession, campaign: Campaign, settings: DialerSettings) -> CampaignOut:
    channels = await svc.channels_for(session, campaign.business_id, settings.default_channels)
    p = await svc.progress(session, campaign, channels)
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
        created_at=campaign.created_at,
        started_at=campaign.started_at,
        completed_at=campaign.completed_at,
        progress=Progress(
            total=p.total,
            skipped=p.skipped,
            remaining=p.remaining,
            dialing=p.dialing,
            done=p.total - p.skipped - p.remaining,
            buckets=p.buckets,
            reasons=p.reasons,
            blocked_summary=owner_summary(blocked),
            eta_minutes=p.eta_minutes,
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
    return CampaignList(items=[await _out(session, c, settings) for c in rows])


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
    session.add(campaign)
    await session.flush()
    added, skipped = await svc.add_contacts(session, campaign, parsed, clock())
    out = await _out(session, campaign, settings)
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
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> CampaignOut:
    return await _out(session, await _get(session, tenant, campaign_id), settings)


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def edit_campaign(
    campaign_id: uuid.UUID,
    body: CampaignPatch,
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
    out = await _out(session, campaign, settings)
    await session.commit()
    return out


async def _transition(
    action: str,
    campaign_id: uuid.UUID,
    clock: Clock,
    settings: DialerSettings,
    tenant: Tenant,
    session: AsyncSession,
) -> CampaignOut:
    campaign = await _get(session, tenant, campaign_id)
    now = clock()
    try:
        if action == "start":
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
    out = await _out(session, campaign, settings)
    await session.commit()
    return out


@router.post("/{campaign_id}/start", response_model=CampaignOut)
async def start_campaign(
    campaign_id: uuid.UUID,
    clock: Clock = Depends(get_clock),
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> CampaignOut:
    return await _transition("start", campaign_id, clock, settings, tenant, session)


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


@router.post("/{campaign_id}/contacts", response_model=ContactsAddedOut, summary="Extend")
async def add_contacts(
    campaign_id: uuid.UUID,
    body: ListIn,
    clock: Clock = Depends(get_clock),
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> ContactsAddedOut:
    campaign = await _get(session, tenant, campaign_id)
    if campaign.status == CampaignStatus.CANCELLED:
        raise AppError(409, "finished", "This campaign was cancelled")
    if body.column_map is None:
        body = body.model_copy(update={"column_map": dict(campaign.column_map)})
    parsed = _parse(body, settings)
    current = await svc.contact_count(session, campaign.id)
    if current + len(parsed.rows) > settings.max_contacts:
        raise AppError(422, "too_many", f"At most {settings.max_contacts} people per campaign")
    if campaign.status == CampaignStatus.COMPLETED:  # extending a finished list reopens it
        campaign.status, campaign.completed_at = CampaignStatus.RUNNING, None
    try:
        added, skipped = await svc.add_contacts(session, campaign, parsed, clock())
    except svc.CampaignError as e:
        raise _campaign_error(e) from e
    out = await _out(session, campaign, settings)
    await session.commit()
    return ContactsAddedOut(
        added=added,
        skipped_recent=skipped,
        invalid=parsed.invalid,
        duplicates=parsed.duplicates,
        campaign=out,
    )


@router.get("/{campaign_id}/contacts", response_model=ContactList)
async def list_contacts(
    campaign_id: uuid.UUID,
    bucket: ResultBucket | None = None,
    contact_status: ContactStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> ContactList:
    campaign = await _get(session, tenant, campaign_id)
    where = [CampaignContact.campaign_id == campaign.id]
    if bucket is not None:
        where.append(CampaignContact.bucket == bucket)
    if contact_status is not None:
        where.append(CampaignContact.status == contact_status)
    total = await session.scalar(select(func.count()).where(*where))
    rows = await session.scalars(
        select(CampaignContact)
        .where(*where)
        .order_by(CampaignContact.row_number)
        .limit(limit)
        .offset(offset)
    )
    return ContactList(
        items=[ContactOut.model_validate(r, from_attributes=True) for r in rows],
        total=int(total or 0),
    )


@router.get("/{campaign_id}/export.csv", summary="Results as CSV")
async def export_csv(
    campaign_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    campaign = await _get(session, tenant, campaign_id)
    variables = list(dict.fromkeys(campaign.column_map.values()))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "row",
            "name",
            "phone",
            "status",
            "result",
            "reasons",
            "attempts",
            "last_outcome",
            "last_called_at",
            "summary",
            *variables,
        ]
    )
    rows = await session.scalars(
        select(CampaignContact)
        .where(CampaignContact.campaign_id == campaign.id)
        .order_by(CampaignContact.row_number)
    )
    for c in rows:
        writer.writerow(
            [
                c.row_number,
                _safe(c.name or ""),
                unseal(c.phone_enc),
                c.status.value,
                c.bucket.value if c.bucket else "",
                " ".join(c.reasons),
                c.attempts,
                c.last_outcome.value if c.last_outcome else "",
                c.last_called_at.isoformat() if c.last_called_at else "",
                _safe(c.summary or ""),
                *(_safe(str(c.variables.get(v, ""))) for v in variables),
            ]
        )
    filename = f"campaign-{campaign.id.hex[:8]}.csv"
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _safe(value: str) -> str:
    """Spreadsheet formula injection guard for cells a customer could have influenced."""
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value
