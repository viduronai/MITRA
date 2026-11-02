"""Scheduled jobs for leads and webhooks (service-token auth, called by the scheduler).

* ``POST /internal/v1/webhooks/run``: deliver every due webhook (first tries and retries).
* ``POST /internal/v1/leads/pull``: IndiaMART pull for every business with a key (every 5-10
  min). Webhooks for the new leads go out with the next ``webhooks/run``.

Business ids come from SECURITY DEFINER functions (migration 0005_leads); each business is then
processed under its own RLS tenant.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.api.internal import require_service
from mitra_core.api.lead_intake import intake_deps
from mitra_core.api.v1.leads import indiamart_provider
from mitra_core.clock import Clock, get_clock
from mitra_core.db import get_session, get_sessionmaker
from mitra_core.leads.enums import LeadSourceKind
from mitra_core.leads.intake import get_intake
from mitra_core.leads.providers import IndiaMartProvider
from mitra_core.leads.pull import pull_indiamart
from mitra_core.leads.service import IntakeDeps
from mitra_core.logging import get_logger
from mitra_core.models import Business, LeadSource
from mitra_core.schemas.common import ResponseModel
from mitra_core.tenancy import TenantContext, set_tenant
from mitra_core.webhooks.sender import WebhookSender, get_webhook_sender
from mitra_core.webhooks.service import deliver_due_in

log = get_logger(__name__)
router = APIRouter(
    prefix="/internal/v1",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_service)],
)

_DUE = text("SELECT internal_webhook_due_businesses(:now)")
_PULL = text("SELECT internal_lead_pull_businesses(:kind)")


class JobOut(ResponseModel):
    businesses: int
    processed: int


@router.post("/webhooks/run", response_model=JobOut)
async def run_webhooks(
    clock: Clock = Depends(get_clock),
    sender: WebhookSender = Depends(get_webhook_sender),
    session: AsyncSession = Depends(get_session),
) -> JobOut:
    now = clock()
    business_ids = list((await session.execute(_DUE, {"now": now})).scalars())
    sent = 0
    for business_id in business_ids:
        async with get_sessionmaker()() as tenant:
            await set_tenant(tenant, TenantContext(business_id=business_id))
            sent += await deliver_due_in(tenant, business_id, sender, now)
    return JobOut(businesses=len(business_ids), processed=sent)


@router.post("/leads/pull", response_model=JobOut)
async def pull_leads(
    clock: Clock = Depends(get_clock),
    deps: IntakeDeps = Depends(intake_deps),
    provider: IndiaMartProvider = Depends(indiamart_provider),
    session: AsyncSession = Depends(get_session),
) -> JobOut:
    now = clock()
    business_ids = list(
        (await session.execute(_PULL, {"kind": LeadSourceKind.INDIAMART.value})).scalars()
    )
    created = 0
    for business_id in business_ids:
        async with get_sessionmaker()() as tenant:
            await set_tenant(tenant, TenantContext(business_id=business_id))
            business = await tenant.get(Business, business_id)
            intake = await get_intake(tenant, business_id)
            source = await tenant.scalar(
                select(LeadSource).where(
                    LeadSource.business_id == business_id,
                    LeadSource.kind == LeadSourceKind.INDIAMART,
                )
            )
            if business is None or intake is None or source is None:
                continue
            try:
                out = await pull_indiamart(
                    tenant, business, intake, source, provider, now=now, deps=deps
                )
                await tenant.commit()
                created += out.created
            except Exception as exc:  # one business must not stop the others
                await tenant.rollback()
                log.error(
                    "leads.pull_failed", business_id=str(business_id), exc_type=type(exc).__name__
                )
    return JobOut(businesses=len(business_ids), processed=created)
