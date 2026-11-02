"""One Manager conversation engine for WhatsApp and the in-app "Ask Mitra" thread (MGR-02/03/04,
MGR-08). Questions auto-run read-only tools; commands and coaching only ever produce a confirm
card (an approval), never an action. Permissions follow the sender's role.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.approvals import button_id
from mitra_core.manager import commands
from mitra_core.manager.answers import answer, with_links
from mitra_core.manager.i18n import t
from mitra_core.manager.intents import COMMAND_INTENTS, Lang
from mitra_core.manager.planner import Planner
from mitra_core.models import ManagerMessage
from mitra_core.models.enums import MemberRole

Channel = Literal["app", "whatsapp"]
COMMAND_ROLES = frozenset({MemberRole.OWNER, MemberRole.MANAGER})
MAX_INPUT = 1000


@dataclass(slots=True)
class Reply:
    text: str
    lang: Lang
    card: dict[str, Any] | None = None
    links: list[dict[str, str]] = field(default_factory=list)
    buttons: list[tuple[str, str]] = field(default_factory=list)

    def whatsapp_text(self) -> str:
        if self.card is not None or not self.links:
            return self.text
        from mitra_core.manager.answers import Answer

        return with_links(Answer(self.text, self.links), self.lang)


async def _store(
    session: AsyncSession,
    business_id: uuid.UUID,
    user_id: uuid.UUID,
    channel: Channel,
    role: Literal["owner", "mitra"],
    text: str,
    card: dict[str, Any] | None = None,
) -> ManagerMessage:
    msg = ManagerMessage(
        id=uuid.uuid4(),
        business_id=business_id,
        user_id=user_id,
        channel=channel,
        role=role,
        text=text,
        card=card,
    )
    session.add(msg)
    await session.flush()
    return msg


async def converse(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    user_id: uuid.UUID,
    role: MemberRole,
    channel: Channel,
    text: str,
    planner: Planner,
    now: datetime,
) -> Reply:
    """Handle one owner message; stores both turns. The caller commits."""
    text = " ".join(text.split())[:MAX_INPUT]
    await _store(session, business_id, user_id, channel, "owner", text)
    intent = await planner.plan(text)
    lang = intent.lang

    if intent.name in COMMAND_INTENTS:
        if role not in COMMAND_ROLES:
            reply = Reply(t("staff_only_questions", lang), lang)
        else:
            try:
                drafted = await commands.draft(session, business_id, intent, user_id, now)
            except commands.CommandError as exc:
                reply = Reply(str(exc), lang)
            else:
                approval = drafted.approval
                reply = Reply(
                    drafted.text,
                    lang,
                    card={
                        "type": "confirm",
                        "approval_id": str(approval.id),
                        "version": approval.version,
                        "kind": approval.kind,
                    },
                    buttons=[
                        (button_id(approval, "approve"), "Confirm"),
                        (button_id(approval, "decline"), "Cancel"),
                    ],
                )
    else:
        ans = await answer(session, business_id, intent, now)
        reply = Reply(ans.text, lang, links=ans.links)

    card = (
        reply.card if reply.card is not None else ({"links": reply.links} if reply.links else None)
    )
    await _store(session, business_id, user_id, channel, "mitra", reply.text, card)
    return reply
