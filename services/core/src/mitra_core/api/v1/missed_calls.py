"""Missed-call number (CALL-20) on the Connect screen: choose the number, poster, stats, blocks.

Callers are shown masked (last four digits); blocking works from the recent list by id, so the
full number never needs to reach the browser.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.errors import AppError, not_found
from mitra_core.models import CallerBlock, MissedCall, OutboundJob, PhoneNumber
from mitra_core.models.enums import MemberRole
from mitra_core.phones import mask_phone
from mitra_core.pii import hash_phone, phone_last4
from mitra_core.schemas.missed_call import (
    CallerBlockIn,
    CallerBlockOut,
    MissedCallRow,
    MissedCallSetupOut,
    MissedCallStatsOut,
    MissedNumberIn,
    PosterLines,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role
from mitra_core.telephony import missed
from mitra_core.telephony.enums import KycStatus, NumberType
from mitra_core.telephony.service import display_number

router = APIRouter(prefix="/missed-call", tags=["missed-call number"])
_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)


def poster(display: str) -> PosterLines:
    return PosterLines(
        en=f"Give a missed call on {display} and we'll call you back in 1 minute.",
        hi=f"{display} पर मिस्ड कॉल दें, हम 1 मिनट में आपको वापस कॉल करेंगे।",
        te=f"{display} కి మిస్డ్ కాల్ ఇవ్వండి, మేము 1 నిమిషంలో మీకు తిరిగి కాల్ చేస్తాము.",
    )


@router.get("", response_model=MissedCallSetupOut, summary="Missed-call number, poster, stats")
async def get_setup(
    days: int = Query(30, ge=1, le=365),
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> MissedCallSetupOut:
    bid = tenant.business_id
    number = await session.scalar(
        select(PhoneNumber).where(PhoneNumber.business_id == bid, PhoneNumber.missed_call)
    )
    display = (
        display_number(number.e164, mobile=number.type == NumberType.MOBILE_VIRTUAL)
        if number
        else None
    )
    found = await missed.stats(session, bid, clock() - timedelta(days=days))
    rows = (
        await session.execute(
            select(MissedCall, OutboundJob.status, OutboundJob.last_outcome)
            .outerjoin(OutboundJob, OutboundJob.id == MissedCall.job_id)
            .where(MissedCall.business_id == bid)
            .order_by(MissedCall.received_at.desc())
            .limit(20)
        )
    ).all()
    blocks = await session.scalars(
        select(CallerBlock)
        .where(CallerBlock.business_id == bid)
        .order_by(CallerBlock.created_at.desc())
    )
    return MissedCallSetupOut(
        phone_number_id=number.id if number else None,
        e164=number.e164 if number else None,
        display=display,
        live=bool(number and number.e164 and number.kyc_status == KycStatus.APPROVED),
        tel_uri=f"tel:{number.e164}" if number and number.e164 else None,
        poster=poster(display) if display else None,
        stats=MissedCallStatsOut(
            days=days,
            missed=found.missed,
            called_back=found.called_back,
            answered=found.answered,
        ),
        recent=[
            MissedCallRow(
                id=m.id,
                phone_masked=mask_phone(m.phone_last4),
                status=m.status,  # type: ignore[arg-type]
                received_at=m.received_at,
                call_back_at=m.call_back_at,
                outcome=(outcome.value if outcome else (job_status.value if job_status else None)),
            )
            for m, job_status, outcome in rows
        ],
        blocks=[
            CallerBlockOut(
                id=b.id,
                phone_masked=mask_phone(b.phone_last4),
                reason=b.reason,
                created_at=b.created_at,
            )
            for b in blocks
        ],
    )


@router.put("/number", response_model=MissedCallSetupOut, summary="Choose the missed-call number")
async def set_number(
    body: MissedNumberIn,
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> MissedCallSetupOut:
    bid = tenant.business_id
    if body.phone_number_id is not None:
        number = await session.scalar(
            select(PhoneNumber).where(
                PhoneNumber.id == body.phone_number_id, PhoneNumber.business_id == bid
            )
        )
        if number is None:
            raise not_found("Phone number")
        if number.type in (NumberType.SERIES_140, NumberType.SERIES_1600, NumberType.SERIES_1601):
            raise AppError(
                422, "unsuitable_number", "Use a local or mobile number for missed calls"
            )
    await session.execute(
        update(PhoneNumber)
        .where(PhoneNumber.business_id == bid, PhoneNumber.missed_call)
        .values(missed_call=False)
    )
    if body.phone_number_id is not None:
        await session.execute(
            update(PhoneNumber)
            .where(PhoneNumber.id == body.phone_number_id, PhoneNumber.business_id == bid)
            .values(missed_call=True)
        )
    await session.commit()
    return await get_setup(30, clock, tenant, session)


@router.post(
    "/blocks",
    status_code=status.HTTP_201_CREATED,
    response_model=CallerBlockOut,
    summary="Block a caller from getting missed-call callbacks",
)
async def add_block(
    body: CallerBlockIn,
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> CallerBlockOut:
    bid = tenant.business_id
    if (body.missed_call_id is None) == (body.phone is None):
        raise AppError(422, "invalid_block", "Give either a missed call or a phone number")
    if body.missed_call_id is not None:
        seen = await session.scalar(
            select(MissedCall).where(
                MissedCall.id == body.missed_call_id, MissedCall.business_id == bid
            )
        )
        if seen is None:
            raise not_found("Missed call")
        phone_hash, last4 = seen.phone_hash, seen.phone_last4
    else:
        assert body.phone is not None  # noqa: S101 (checked above)
        phone_hash, last4 = hash_phone(body.phone), phone_last4(body.phone)
    block = CallerBlock(
        id=uuid.uuid4(),
        business_id=bid,
        phone_hash=phone_hash,
        phone_last4=last4,
        reason=body.reason,
        created_at=clock(),
    )
    session.add(block)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise AppError(409, "already_blocked", "This caller is already blocked") from exc
    out = CallerBlockOut(
        id=block.id,
        phone_masked=mask_phone(last4),
        reason=block.reason,
        created_at=block.created_at,
    )
    await session.commit()
    return out


@router.delete(
    "/blocks/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Unblock a caller",
)
async def remove_block(
    block_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    block = await session.scalar(
        select(CallerBlock).where(
            CallerBlock.id == block_id, CallerBlock.business_id == tenant.business_id
        )
    )
    if block is None:
        raise not_found("Block")
    await session.delete(block)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
