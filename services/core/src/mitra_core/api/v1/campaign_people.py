"""Campaign people (CALL-15): add people to a campaign, list them by result, export as CSV.

Split from ``campaigns.py`` (same ``/v1/campaigns`` prefix). Adding people to a campaign that
already calls needs the owner's list attestation again (docs/08 section 8.5).
"""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.api.v1.campaigns import _campaign_error, _can_manage, _get, _out, _parse
from mitra_core.clock import Clock, get_clock
from mitra_core.dialer import campaigns as svc
from mitra_core.dialer import consent as list_consent
from mitra_core.dialer.enums import CampaignStatus, ContactStatus, ResultBucket
from mitra_core.dialer.sealing import unseal
from mitra_core.dialer.settings import DialerSettings, get_dialer_settings
from mitra_core.errors import AppError
from mitra_core.models.campaign import CampaignContact
from mitra_core.schemas.campaign import ContactList, ContactOut, ContactsAddedOut, ExtendIn
from mitra_core.security import Tenant, get_tenant_session, require_business

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("/{campaign_id}/contacts", response_model=ContactsAddedOut, summary="Extend")
async def add_contacts(
    campaign_id: uuid.UUID,
    body: ExtendIn,
    clock: Clock = Depends(get_clock),
    settings: DialerSettings = Depends(get_dialer_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> ContactsAddedOut:
    campaign = await _get(session, tenant, campaign_id)
    if campaign.status == CampaignStatus.CANCELLED:
        raise AppError(409, "finished", "This campaign was cancelled")
    now = clock()
    if body.consent_attested:
        list_consent.attest(campaign, tenant.user, body.consent_language, now)
    elif campaign.status != CampaignStatus.DRAFT:
        # New people on a list that already calls: the owner vouches for them too.
        raise AppError(
            409,
            "consent_required",
            "Confirm that the new people agreed to be contacted",
        )
    if body.column_map is None:
        # Reuse the campaign's mapping for the columns this list has (it may have fewer).
        headers = set(_parse(body, settings).headers)
        mapping = {h: v for h, v in campaign.column_map.items() if h in headers}
        body = body.model_copy(update={"column_map": mapping})
    parsed = _parse(body, settings)
    current = await svc.contact_count(session, campaign.id)
    if current + len(parsed.rows) > settings.max_contacts:
        raise AppError(422, "too_many", f"At most {settings.max_contacts} people per campaign")
    if campaign.status == CampaignStatus.COMPLETED:  # extending a finished list reopens it
        campaign.status, campaign.completed_at = CampaignStatus.RUNNING, None
    try:
        added, skipped = await svc.add_contacts(session, campaign, parsed, now)
    except svc.CampaignError as e:
        raise _campaign_error(e) from e
    out = await _out(session, campaign, settings, now)
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
                unseal(c.phone_enc, c.business_id) if c.phone_enc else "",  # '' = forgotten
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
