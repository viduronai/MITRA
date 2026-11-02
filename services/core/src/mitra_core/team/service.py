"""Hire a team in one tap (TEAM-01, ONB-14) and read the team map with counts (TEAM-03)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.catalog import VOICES_BY_ID
from mitra_core.models import (
    Call,
    Employee,
    FollowUpTask,
    HandoffRule,
    Team,
    TeamMember,
)
from mitra_core.models.enums import EmployeeStatus, Locale
from mitra_core.team.templates import TEAM_TEMPLATES, TeamTemplate

MAP_WINDOW = timedelta(days=7)


async def hire_team(
    session: AsyncSession,
    business_id: uuid.UUID,
    template: TeamTemplate,
    *,
    languages: list[Locale],
    names: dict[str, str] | None = None,
    reuse: dict[str, uuid.UUID] | None = None,
) -> Team:
    """Create the team, one employee per role (or reuse existing ones), and its hand-off rules.

    New employees start in ``training`` so nothing calls customers until the owner activates.
    """
    names = names or {}
    reuse = reuse or {}
    team = Team(business_id=business_id, name=template.name, template_id=template.id)
    session.add(team)
    await session.flush()
    by_role: dict[str, uuid.UUID] = {}
    for position, role in enumerate(template.roles):
        employee_id = reuse.get(role.id)
        if employee_id is None:
            employee = Employee(
                business_id=business_id,
                name=names.get(role.id, role.name)[:60],
                role_template=role.base,
                languages=[lang.value for lang in languages],
                voice_id=role.voice_id,
                behaviour={
                    "ask_for": list(role.ask_for),
                    "never_say": [],
                    "transfer_when": list(role.transfer_when),
                },
            )
            employee.voice_tier = VOICES_BY_ID[role.voice_id].tier
            session.add(employee)
            await session.flush()
            employee_id = employee.id
        by_role[role.id] = employee_id
        session.add(
            TeamMember(
                business_id=business_id,
                team_id=team.id,
                employee_id=employee_id,
                team_role=role.id,
                position=position,
            )
        )
    for rule in template.rules:
        session.add(
            HandoffRule(
                business_id=business_id,
                team_id=team.id,
                from_employee_id=by_role[rule.from_role],
                when_result=rule.when_result,
                condition={},
                to_employee_id=by_role[rule.to_role] if rule.to_role else None,
                task=rule.task,
                channel=rule.channel,
                delay_minutes=rule.delay_minutes,
            )
        )
    await session.flush()
    return team


async def activate_team(session: AsyncSession, team: Team) -> int:
    """Put every member to work. Returns how many employees changed."""
    members = await session.scalars(
        select(Employee)
        .join(TeamMember, TeamMember.employee_id == Employee.id)
        .where(TeamMember.team_id == team.id)
    )
    changed = 0
    for employee in members:
        if employee.status != EmployeeStatus.WORKING:
            employee.status = EmployeeStatus.WORKING
            changed += 1
    team.active = True
    await session.flush()
    return changed


async def member_counts(
    session: AsyncSession, business_id: uuid.UUID, now: datetime
) -> dict[uuid.UUID, dict[str, int]]:
    """Per employee, last 7 days: calls, hand-offs received, tasks waiting."""
    since = now - MAP_WINDOW
    counts: dict[uuid.UUID, dict[str, int]] = {}

    def bump(employee_id: uuid.UUID | None, key: str, n: int) -> None:
        if employee_id is not None:
            counts.setdefault(employee_id, {"calls": 0, "received": 0, "waiting": 0})[key] = n

    calls = await session.execute(
        select(Call.employee_id, func.count())
        .where(Call.business_id == business_id, Call.started_at >= since)
        .group_by(Call.employee_id)
    )
    for employee_id, n in calls:
        bump(employee_id, "calls", n)
    received = await session.execute(
        select(FollowUpTask.to_employee_id, func.count())
        .where(FollowUpTask.business_id == business_id, FollowUpTask.created_at >= since)
        .where(FollowUpTask.kind == "handoff")
        .group_by(FollowUpTask.to_employee_id)
    )
    for employee_id, n in received:
        bump(employee_id, "received", n)
    waiting = await session.execute(
        select(FollowUpTask.to_employee_id, func.count())
        .where(FollowUpTask.business_id == business_id)
        .where(FollowUpTask.status.in_(("pending", "queued")))
        .group_by(FollowUpTask.to_employee_id)
    )
    for employee_id, n in waiting:
        bump(employee_id, "waiting", n)
    return counts


async def edge_counts(
    session: AsyncSession, business_id: uuid.UUID, now: datetime
) -> dict[uuid.UUID, int]:
    """Hand-offs per rule in the last 7 days (the number on each arrow)."""
    rows = await session.execute(
        select(FollowUpTask.rule_id, func.count())
        .where(FollowUpTask.business_id == business_id, FollowUpTask.rule_id.is_not(None))
        .where(FollowUpTask.created_at >= now - MAP_WINDOW)
        .group_by(FollowUpTask.rule_id)
    )
    return {rule_id: n for rule_id, n in rows if rule_id is not None}


def template_or_none(template_id: str) -> TeamTemplate | None:
    return TEAM_TEMPLATES.get(template_id)
