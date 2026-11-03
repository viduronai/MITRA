"""Owner-facing lead setup: intake URL + secret, per-source routines, recent leads (Connect)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.api.lead_intake import intake_deps
from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.errors import AppError, not_found
from mitra_core.leads import attestation as attestations
from mitra_core.leads import consent as consent_policy
from mitra_core.leads import intake as intake_mod
from mitra_core.leads.enums import LeadSourceKind
from mitra_core.leads.providers import IndiaMartProvider, get_indiamart_provider
from mitra_core.leads.pull import pull_indiamart
from mitra_core.leads.samples import sample_lead
from mitra_core.leads.service import IntakeDeps, check_rate, ingest, source_for
from mitra_core.models import (
    Business,
    Employee,
    Lead,
    LeadConsentAttestation,
    LeadIntake,
    LeadSource,
)
from mitra_core.models.enums import MemberRole
from mitra_core.schemas.leads import (
    IntakeUrls,
    LeadList,
    LeadOut,
    LeadSetupOut,
    LeadSetupPatch,
    LeadSourceOut,
    LeadSourcePatch,
    PullOut,
    TestLeadOut,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role
from mitra_core.telephony.compliance import REASON_TEXT
from mitra_core.webhooks.service import deliver_due

router = APIRouter(prefix="/leads", tags=["leads"])
_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)

EXTRA_REASONS = {"dialer_refused": "the call could not be queued"}


def _urls(settings: Settings, slug: str) -> IntakeUrls:
    base = f"{settings.public_api_url.rstrip('/')}/lead-intake/{slug}"
    return IntakeUrls(
        generic=base,
        form=f"{base}/form",
        google_ads=f"{base}/google-ads",
        indiamart=f"{base}/indiamart",
        justdial=f"{base}/justdial",
        meta_webhook=f"{settings.public_api_url.rstrip('/')}/webhooks/meta/leadgen",
    )


def _simulated(kind: LeadSourceKind, settings: Settings) -> bool:
    if kind == LeadSourceKind.META:
        return settings.meta_leads_provider == "sim"
    return kind == LeadSourceKind.INDIAMART and settings.indiamart_provider == "sim"


def source_out(
    kind: LeadSourceKind,
    row: LeadSource | None,
    settings: Settings,
    attested: LeadConsentAttestation | None = None,
) -> LeadSourceOut:
    sim = _simulated(kind, settings)
    policy: dict[str, object] = {
        "consent_policy": consent_policy.policy_of(kind),
        "attested_at": attested.attested_at if attested else None,
        "attested_by": attested.user_name if attested else None,
    }
    if row is None:
        return LeadSourceOut(kind=kind, connected=False, simulated=sim).model_copy(update=policy)
    return LeadSourceOut(
        kind=kind,
        connected=True,
        enabled=row.enabled,
        auto_call=row.auto_call,
        call_delay_seconds=row.call_delay_seconds,
        heads_up=row.heads_up,
        employee_id=row.employee_id,
        external_id=row.external_id,
        credential_hint=row.credential_hint,
        last_lead_at=row.last_lead_at,
        last_pulled_at=row.last_pulled_at,
        lead_count=row.lead_count,
        last_error=row.last_error,
        simulated=sim,
    ).model_copy(update=policy)


def lead_out(lead: Lead) -> LeadOut:
    reasons = list(lead.reasons or [])
    return LeadOut(
        id=lead.id,
        source=LeadSourceKind(lead.source),
        source_detail=lead.source_detail,
        name=lead.name,
        phone_last4=lead.phone_last4,
        fields={k: str(v) for k, v in (lead.fields or {}).items()},
        status=lead.status,  # type: ignore[arg-type]
        reasons=reasons,
        reason_text=[REASON_TEXT.get(r) or EXTRA_REASONS.get(r, r) for r in reasons],
        employee_id=lead.employee_id,
        call_at=lead.call_at,
        received_at=lead.received_at,
        duplicate_of=lead.duplicate_of,
    )


async def _setup_out(
    session: AsyncSession, tenant: Tenant, settings: Settings, secret: str | None = None
) -> LeadSetupOut:
    intake = await intake_mod.get_intake(session, tenant.business_id)
    rows = {
        r.kind: r
        for r in await session.scalars(
            select(LeadSource).where(LeadSource.business_id == tenant.business_id)
        )
    }
    business = await session.get(Business, tenant.business_id)
    attested = {
        k: await attestations.active(session, tenant.business_id, k)
        for k in consent_policy.GENERIC_SOURCES
    }
    sources = [source_out(k, rows.get(k.value), settings, attested.get(k)) for k in LeadSourceKind]
    name = business.name if business else ""
    texts = LeadSetupOut(
        enabled=False,
        sources=sources,
        consent_version=consent_policy.CONSENT_VERSION,
        consent_texts={
            lang: consent_policy.consent_text(name, lang) for lang in consent_policy.LANGS
        },
        attestation_texts=dict(consent_policy.ATTESTATION_TEXTS),
    )
    if intake is None:
        return texts
    return texts.model_copy(
        update={
            "enabled": True,
            "slug": intake.slug,
            "secret_hint": intake.secret_hint,
            "secret": secret,
            "rotated_at": intake.rotated_at,
            "previous_valid_until": intake.previous_valid_until,
            "dedupe_minutes": intake.dedupe_minutes,
            "urls": _urls(settings, intake.slug),
        }
    )


async def _require_intake(session: AsyncSession, tenant: Tenant) -> LeadIntake:
    intake = await intake_mod.get_intake(session, tenant.business_id)
    if intake is None:
        raise AppError(409, "leads_not_set_up", "Turn on lead intake first")
    return intake


@router.get("/setup", response_model=LeadSetupOut, summary="Lead intake URL, sources, status")
async def get_setup(
    settings: Settings = Depends(get_settings),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> LeadSetupOut:
    return await _setup_out(session, tenant, settings)


@router.post("/setup", response_model=LeadSetupOut, summary="Turn on lead intake (idempotent)")
async def create_setup(
    settings: Settings = Depends(get_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> LeadSetupOut:
    business = await session.get(Business, tenant.business_id)
    if business is None:
        raise not_found("Business")
    _, secret = await intake_mod.ensure_intake(session, business)
    out = await _setup_out(session, tenant, settings, secret)
    await session.commit()
    return out


@router.patch("/setup", response_model=LeadSetupOut)
async def patch_setup(
    body: LeadSetupPatch,
    settings: Settings = Depends(get_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> LeadSetupOut:
    intake = await _require_intake(session, tenant)
    if body.dedupe_minutes is not None:
        intake.dedupe_minutes = body.dedupe_minutes
    await session.commit()
    return await _setup_out(session, tenant, settings)


@router.post("/setup/rotate-secret", response_model=LeadSetupOut)
async def rotate_secret(
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> LeadSetupOut:
    intake = await _require_intake(session, tenant)
    secret = intake_mod.rotate(intake, clock())
    await session.commit()
    await session.refresh(intake)
    return await _setup_out(session, tenant, settings, secret)


@router.patch("/sources/{kind}", response_model=LeadSourceOut, summary="Source routine (AUTO-02)")
async def patch_source(
    kind: LeadSourceKind,
    body: LeadSourcePatch,
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> LeadSourceOut:
    await _require_intake(session, tenant)
    row = await source_for(session, tenant.business_id, kind)
    fields = body.model_fields_set
    if "employee_id" in fields and body.employee_id is not None:
        found = await session.scalar(
            select(Employee.id).where(
                Employee.id == body.employee_id, Employee.business_id == tenant.business_id
            )
        )
        if found is None:
            raise not_found("Employee")
    if body.consent_attested is not None:
        if kind not in consent_policy.GENERIC_SOURCES:
            raise AppError(422, "not_applicable", "This source records consent by itself")
        if body.consent_attested:
            await attestations.attest(
                session, tenant.business_id, kind, tenant.user, body.attestation_lang, clock()
            )
        else:
            await attestations.revoke(session, tenant.business_id, kind, clock())
    for name in ("enabled", "auto_call", "call_delay_seconds", "heads_up"):
        if name in fields:
            setattr(row, name, getattr(body, name))
    if "employee_id" in fields:
        row.employee_id = body.employee_id
    if "external_id" in fields:
        row.external_id = body.external_id
    if "credential" in fields:
        row.credential = body.credential
        row.credential_hint = f"…{body.credential[-4:]}" if body.credential else None
        row.last_error = None
    try:
        await session.commit()
    except IntegrityError:
        # The page id belongs to another business (invisible here through RLS).
        await session.rollback()
        raise AppError(409, "conflict", "This page is already connected to Mitra") from None
    attested = await attestations.active(session, tenant.business_id, kind)
    return source_out(kind, row, settings, attested)


@router.post("/sources/{kind}/test", response_model=TestLeadOut, summary="Send a test lead")
async def send_test_lead(
    kind: LeadSourceKind,
    background: BackgroundTasks,
    clock: Clock = Depends(get_clock),
    deps: IntakeDeps = Depends(intake_deps),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> TestLeadOut:
    intake = await _require_intake(session, tenant)
    business = await session.get(Business, tenant.business_id)
    if business is None:
        raise not_found("Business")
    now = clock()
    await check_rate(session, business.id, now, deps.settings)
    source = await source_for(session, business.id, kind)
    data = sample_lead(kind, tenant.user.phone_e164)
    result = await ingest(session, business, intake, source, data, now=now, deps=deps)
    await session.commit()
    if result.webhooks:
        background.add_task(deliver_due, business.id, None, now)
    return TestLeadOut(lead=lead_out(result.lead), duplicate=result.duplicate)


def indiamart_provider(settings: Settings = Depends(get_settings)) -> IndiaMartProvider:
    return get_indiamart_provider(settings)


@router.post("/sources/indiamart/pull", response_model=PullOut, summary="Fetch IndiaMART now")
async def pull_now(
    background: BackgroundTasks,
    clock: Clock = Depends(get_clock),
    deps: IntakeDeps = Depends(intake_deps),
    provider: IndiaMartProvider = Depends(indiamart_provider),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> PullOut:
    intake = await _require_intake(session, tenant)
    business = await session.get(Business, tenant.business_id)
    if business is None:
        raise not_found("Business")
    source = await source_for(session, business.id, LeadSourceKind.INDIAMART)
    now = clock()
    out = await pull_indiamart(session, business, intake, source, provider, now=now, deps=deps)
    await session.commit()
    if out.created:
        background.add_task(deliver_due, business.id, None, now)
    return out


@router.get("", response_model=LeadList, summary="Recent leads")
async def list_leads(
    source: LeadSourceKind | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> LeadList:
    stmt = select(Lead).where(Lead.business_id == tenant.business_id)
    if source is not None:
        stmt = stmt.where(Lead.source == source.value)
    rows = await session.scalars(stmt.order_by(Lead.received_at.desc(), Lead.id).limit(limit))
    return LeadList(items=[lead_out(r) for r in rows])
