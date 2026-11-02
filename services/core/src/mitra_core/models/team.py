"""AI team, hand-offs, routines and calls-with-humans (migration 0005_team). All tenant tables.

* ``team`` / ``team_member``: an industry team (TEAM-01) is an ordered chain of employees; each
  member has a ``team_role`` (visit_coordinator, ...) on top of the employee's base role.
* ``handoff_rule``: "When a lead is Interested, pass to Visit Coordinator" (TEAM-02), typed.
* ``follow_up_task``: work created for the next employee or for human staff (ACT-07), carrying
  the context packet (WORKFLOWS section 5) built from shared customer memory.
* ``staff_member``: the business's people: transfer targets, the escalation ladder (CALL-19)
  and who gets WhatsApp briefs (TEAM-04). Staff numbers are business contacts, stored as-is
  like ``app_user.phone_e164``; customers' numbers never are.
* ``handoff_card``: a message taken when nobody on the ladder answered.
* ``routine`` / ``routine_run``: autopilot (AUTO-01..05); ``spec`` is the typed JSON.
* ``supervisor_action``: every listen / whisper / takeover on a live call (CALL-18), logged.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey


def _business() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("business.id", ondelete="CASCADE"), index=True)


def _jsonb(default: str = "{}") -> Any:
    return mapped_column(JSONB, server_default=default, default=dict if default == "{}" else list)


class Team(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "team"

    business_id: Mapped[uuid.UUID] = _business()
    name: Mapped[str] = mapped_column(String(80))
    template_id: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class TeamMember(UUIDPrimaryKey, Base):
    __tablename__ = "team_member"
    __table_args__ = (UniqueConstraint("team_id", "employee_id"),)

    business_id: Mapped[uuid.UUID] = _business()
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employee.id", ondelete="CASCADE"), index=True
    )
    team_role: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(SmallInteger)


class HandoffRule(UUIDPrimaryKey, Timestamps, Base):
    """``when`` result (+ optional field condition) from one employee -> task for another."""

    __tablename__ = "handoff_rule"

    business_id: Mapped[uuid.UUID] = _business()
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"), index=True
    )
    from_employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employee.id", ondelete="CASCADE"), index=True
    )
    when_result: Mapped[str] = mapped_column(String(32))
    # Optional {"field": "budget", "op": "present"} style condition, validated by the API.
    condition: Mapped[dict[str, Any]] = _jsonb()
    to_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="CASCADE")
    )
    # None target + task "brief_staff" = WhatsApp brief to human staff instead of an employee.
    task: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(24))
    delay_minutes: Mapped[int] = mapped_column(Integer, server_default=text("10"))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class FollowUpTask(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "follow_up_task"

    business_id: Mapped[uuid.UUID] = _business()
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contact.id", ondelete="CASCADE"), index=True
    )
    from_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    to_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL"), index=True
    )
    source_call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("call.id", ondelete="SET NULL"), index=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("handoff_rule.id", ondelete="SET NULL")
    )
    routine_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("routine_run.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(24))  # handoff | routine | staff_brief | escalation
    task: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(24))
    due_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(16))
    context: Mapped[dict[str, Any]] = _jsonb()
    outcome: Mapped[dict[str, Any]] = _jsonb()


class StaffMember(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "staff_member"

    business_id: Mapped[uuid.UUID] = _business()
    name: Mapped[str] = mapped_column(String(80))
    phone_e164: Mapped[str] = mapped_column(String(16))
    role_label: Mapped[str | None] = mapped_column(String(60))
    # 1, 2, 3...: transfer order (CALL-19). None = not on the ladder.
    ladder_position: Mapped[int | None] = mapped_column(SmallInteger)
    ring_timeout_s: Mapped[int] = mapped_column(SmallInteger, server_default=text("20"))
    receives_briefs: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_owner: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class HandoffCard(UUIDPrimaryKey, Base):
    __tablename__ = "handoff_card"

    business_id: Mapped[uuid.UUID] = _business()
    # The voice service's call id; the call row may arrive after the card, so no FK.
    call_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contact.id", ondelete="CASCADE")
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    caller_last4: Mapped[str | None] = mapped_column(String(4))
    reason: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(String(1000))
    callback_by: Mapped[datetime | None]
    attempts: Mapped[list[dict[str, Any]]] = _jsonb("[]")
    status: Mapped[str] = mapped_column(String(16), server_default="open")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None]
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )


class Routine(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "routine"

    business_id: Mapped[uuid.UUID] = _business()
    name: Mapped[str] = mapped_column(String(120))
    library_id: Mapped[str | None] = mapped_column(String(40))
    spec: Mapped[dict[str, Any]] = _jsonb()
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    next_run_at: Mapped[datetime | None] = mapped_column(index=True)
    last_run_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )


class RoutineRun(UUIDPrimaryKey, Base):
    __tablename__ = "routine_run"

    business_id: Mapped[uuid.UUID] = _business()
    routine_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("routine.id", ondelete="CASCADE"), index=True
    )
    trigger: Mapped[str] = mapped_column(String(16))  # schedule | event | manual
    status: Mapped[str] = mapped_column(String(20))
    audience_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    contacted_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    skipped: Mapped[dict[str, Any]] = _jsonb()  # reason -> count
    # [{contact_id, name, last4, status}] for history (AUTO-05); results update it.
    contacts: Mapped[list[dict[str, Any]]] = _jsonb("[]")
    approval_ref: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    finished_at: Mapped[datetime | None]


class SupervisorAction(UUIDPrimaryKey, Base):
    __tablename__ = "supervisor_action"

    business_id: Mapped[uuid.UUID] = _business()
    call_id: Mapped[uuid.UUID] = mapped_column(index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16))  # listen | whisper | takeover
    text: Mapped[str | None] = mapped_column(String(300))
    delivered_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
