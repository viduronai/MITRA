"""Ask Mitra thread (MGR-08), manager settings, and the WhatsApp simulator (dev only)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.errors import AppError
from mitra_core.manager.brain import converse
from mitra_core.manager.inbound import handle_inbound
from mitra_core.manager.planner import Planner, Transcriber, get_planner, get_transcriber
from mitra_core.models import Approval, ManagerMessage, Membership, WaMessage
from mitra_core.models.enums import MemberRole
from mitra_core.pii import phone_last4
from mitra_core.schemas.manager import (
    AskIn,
    ManagerSettingsOut,
    ManagerSettingsPatch,
    Recipient,
    SimInboundIn,
    SimInboundOut,
    ThreadMessageOut,
    ThreadOut,
    WaMessageList,
    WaMessageOut,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role
from mitra_core.whatsapp import manager_settings, owner_recipients
from mitra_core.whatsapp.inbound import InboundMessage

router = APIRouter(prefix="/manager", tags=["manager"])

THREAD_LIMIT = 60


def planner_dep(settings: Settings = Depends(get_settings)) -> Planner:
    return get_planner(settings)


def transcriber_dep(settings: Settings = Depends(get_settings)) -> Transcriber | None:
    return get_transcriber(settings)


async def _thread(session: AsyncSession, tenant: Tenant, limit: int) -> list[ThreadMessageOut]:
    rows = list(
        await session.scalars(
            select(ManagerMessage)
            .where(
                ManagerMessage.business_id == tenant.business_id,
                ManagerMessage.user_id == tenant.user.id,
            )
            .order_by(ManagerMessage.created_at.desc(), ManagerMessage.id.desc())
            .limit(limit)
        )
    )
    rows.reverse()
    # Confirm cards show their live state (pending / approved / declined / expired).
    ids = [
        uuid.UUID(m.card["approval_id"])
        for m in rows
        if m.card and m.card.get("type") == "confirm" and m.card.get("approval_id")
    ]
    states: dict[str, tuple[str, int, str | None]] = {}
    if ids:
        for a in await session.scalars(select(Approval).where(Approval.id.in_(ids))):
            states[str(a.id)] = (a.status, a.version, a.apply_error)
    out: list[ThreadMessageOut] = []
    for m in rows:
        card = dict(m.card) if m.card else None
        if card and card.get("approval_id") in states:
            status, version, error = states[card["approval_id"]]
            card |= {"status": status, "version": version, "apply_error": error}
        out.append(
            ThreadMessageOut(
                id=m.id,
                role=m.role,
                channel=m.channel,
                text=m.text,
                card=card,
                created_at=m.created_at,
            )
        )
    return out


@router.get("/thread", response_model=ThreadOut, summary="My Ask Mitra conversation")
async def get_thread(
    limit: int = Query(THREAD_LIMIT, ge=1, le=200),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> ThreadOut:
    return ThreadOut(items=await _thread(session, tenant, limit))


@router.post("/thread", response_model=ThreadOut, summary="Ask Mitra (question or command)")
async def ask(
    body: AskIn,
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
    planner: Planner = Depends(planner_dep),
    clock: Clock = Depends(get_clock),
) -> ThreadOut:
    await converse(
        session,
        business_id=tenant.business_id,
        user_id=tenant.user.id,
        role=tenant.role,
        channel="app",
        text=body.text,
        planner=planner,
        now=clock(),
    )
    await session.commit()
    return ThreadOut(items=await _thread(session, tenant, 2))


async def _settings_out(session: AsyncSession, tenant: Tenant) -> ManagerSettingsOut:
    s = await manager_settings(session, tenant.business_id)
    people = await owner_recipients(session, tenant.business_id)
    rows = await session.execute(
        select(Membership.user_id, Membership.role).where(
            Membership.business_id == tenant.business_id
        )
    )
    roles = dict(rows.tuples().all())
    return ManagerSettingsOut(
        report_enabled=s.report_enabled,
        report_time=s.report_time,
        language=s.language,
        report_user_ids=list(s.report_user_ids),
        alert_user_ids=list(s.alert_user_ids),
        alert_kinds=list(s.alert_kinds),
        people=[
            Recipient(
                user_id=u.id,
                name=u.name,
                role=str(roles.get(u.id, "")),
                phone_last4=phone_last4(u.phone_e164),
            )
            for u in people
        ],
    )


@router.get("/settings", response_model=ManagerSettingsOut, summary="Report and alert settings")
async def get_manager_settings(
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> ManagerSettingsOut:
    out = await _settings_out(session, tenant)
    await session.commit()  # the defaults row may have just been created
    return out


@router.patch("/settings", response_model=ManagerSettingsOut, summary="Change report and alerts")
async def patch_manager_settings(
    body: ManagerSettingsPatch,
    tenant: Tenant = Depends(require_role(MemberRole.OWNER, MemberRole.MANAGER)),
    session: AsyncSession = Depends(get_tenant_session),
) -> ManagerSettingsOut:
    s = await manager_settings(session, tenant.business_id)
    members = {u.id for u in await owner_recipients(session, tenant.business_id)}
    for field_name in ("report_user_ids", "alert_user_ids"):
        ids = getattr(body, field_name)
        if ids is not None and not set(ids) <= members:
            raise AppError(422, "validation_error", "Recipients must be owners or managers")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(s, key, value)
    await session.commit()
    return await _settings_out(session, tenant)


# --- WhatsApp simulator (dev only) ----------------------------------------------------------


def _require_sim(settings: Settings) -> None:
    if settings.whatsapp_provider != "sim" or settings.env in {"staging", "prod"}:
        raise AppError(404, "not_found", "The WhatsApp simulator is only available in development")


@router.get(
    "/whatsapp-sim/messages", response_model=WaMessageList, summary="Simulated WhatsApp messages"
)
async def sim_messages(
    limit: int = Query(100, ge=1, le=500),
    tenant: Tenant = Depends(require_role(MemberRole.OWNER, MemberRole.MANAGER)),
    session: AsyncSession = Depends(get_tenant_session),
    settings: Settings = Depends(get_settings),
) -> WaMessageList:
    _require_sim(settings)
    rows = list(
        await session.scalars(
            select(WaMessage)
            .where(WaMessage.business_id == tenant.business_id)
            .order_by(WaMessage.created_at.desc(), WaMessage.id.desc())
            .limit(limit)
        )
    )
    rows.reverse()
    return WaMessageList(items=[WaMessageOut.model_validate(m) for m in rows])


@router.post(
    "/whatsapp-sim/inbound",
    response_model=SimInboundOut,
    summary="Reply on simulated WhatsApp as yourself (text, voice note transcript, button tap)",
)
async def sim_inbound(
    body: SimInboundIn,
    tenant: Tenant = Depends(require_role(MemberRole.OWNER, MemberRole.MANAGER)),
    settings: Settings = Depends(get_settings),
    planner: Planner = Depends(planner_dep),
    transcriber: Transcriber | None = Depends(transcriber_dep),
    clock: Clock = Depends(get_clock),
) -> SimInboundOut:
    _require_sim(settings)
    if body.kind == "button_reply" and not body.button_id:
        raise AppError(422, "validation_error", "button_id is required for a button reply")
    msg = InboundMessage(
        from_phone=tenant.user.phone_e164,
        kind=body.kind,
        message_id=f"sim-in-{uuid.uuid4().hex}",
        text=body.text if body.kind != "voice" else "",
        button_id=body.button_id,
        context_id=body.context_id,
    )
    outcome = await handle_inbound(
        msg,
        provider="sim",
        planner=planner,
        transcriber=transcriber,
        now=clock(),
        voice_transcript=body.text if body.kind == "voice" else None,
    )
    return SimInboundOut(outcome=outcome)
