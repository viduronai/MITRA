"""AI team (TEAM-01/02/03, ONB-14, ACT-07): templates, one-tap hire, team map, hand-off rules."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.errors import AppError, not_found
from mitra_core.models import (
    Business,
    Contact,
    Employee,
    FollowUpTask,
    HandoffRule,
    Team,
    TeamMember,
)
from mitra_core.models.enums import Locale, MemberRole
from mitra_core.schemas.team import (
    HireTeamIn,
    MemberOut,
    RuleIn,
    RuleOut,
    RulePatch,
    TaskOut,
    TeamMapOut,
    TeamOut,
    TeamTemplateOut,
    TemplateRoleOut,
    TemplateRuleOut,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role
from mitra_core.team.service import activate_team, edge_counts, hire_team, member_counts
from mitra_core.team.templates import TEAM_TEMPLATES, TEMPLATE_FOR_INDUSTRY

router = APIRouter(prefix="/team", tags=["team"])
_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)


async def _business(session: AsyncSession, tenant: Tenant) -> Business:
    business = await session.get(Business, tenant.business_id)
    if business is None:
        raise not_found("Business")
    return business


async def _employee_ids(session: AsyncSession, tenant: Tenant) -> set[uuid.UUID]:
    return set(
        await session.scalars(select(Employee.id).where(Employee.business_id == tenant.business_id))
    )


@router.get("/templates", response_model=list[TeamTemplateOut], summary="Ready-made AI teams")
async def list_templates(
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[TeamTemplateOut]:
    business = await _business(session, tenant)
    recommended = TEMPLATE_FOR_INDUSTRY.get(business.industry)
    return [
        TeamTemplateOut(
            id=t.id,
            industry=t.industry.value,
            name=t.name,
            recommended=t.id == recommended,
            roles=[
                TemplateRoleOut(
                    id=r.id, name=r.name, title=r.title, base_role=r.base, voice_id=r.voice_id
                )
                for r in t.roles
            ],
            rules=[
                TemplateRuleOut(
                    from_role=r.from_role,
                    when_result=r.when_result,
                    to_role=r.to_role,
                    task=r.task,
                    channel=r.channel,
                    delay_minutes=r.delay_minutes,
                )
                for r in t.rules
            ],
        )
        for t in TEAM_TEMPLATES.values()
    ]


async def _map(session: AsyncSession, tenant: Tenant, clock: Clock) -> TeamMapOut:
    now = clock()
    counts = await member_counts(session, tenant.business_id, now)
    edges = await edge_counts(session, tenant.business_id, now)
    employees = {
        e.id: e
        for e in await session.scalars(
            select(Employee).where(Employee.business_id == tenant.business_id)
        )
    }

    def member(employee: Employee, team_role: str, position: int) -> MemberOut:
        c = counts.get(employee.id, {})
        return MemberOut(
            employee_id=employee.id,
            name=employee.name,
            team_role=team_role,
            base_role=employee.role_template,
            status=employee.status,
            position=position,
            calls_7d=c.get("calls", 0),
            received_7d=c.get("received", 0),
            waiting=c.get("waiting", 0),
        )

    teams = list(
        await session.scalars(
            select(Team).where(Team.business_id == tenant.business_id).order_by(Team.created_at)
        )
    )
    members = list(
        await session.scalars(
            select(TeamMember)
            .where(TeamMember.business_id == tenant.business_id)
            .order_by(TeamMember.position)
        )
    )
    rules = list(
        await session.scalars(
            select(HandoffRule)
            .where(HandoffRule.business_id == tenant.business_id)
            .order_by(HandoffRule.created_at)
        )
    )
    in_team = {m.employee_id for m in members}
    out = []
    for team in teams:
        out.append(
            TeamOut(
                id=team.id,
                name=team.name,
                template_id=team.template_id,
                active=team.active,
                members=[
                    member(employees[m.employee_id], m.team_role, m.position)
                    for m in members
                    if m.team_id == team.id and m.employee_id in employees
                ],
                rules=[
                    RuleOut.model_validate(r).model_copy(update={"handoffs_7d": edges.get(r.id, 0)})
                    for r in rules
                    if r.team_id == team.id
                ],
            )
        )
    loose = [r for r in rules if r.team_id is None]
    if loose and out:
        out[0].rules.extend(
            RuleOut.model_validate(r).model_copy(update={"handoffs_7d": edges.get(r.id, 0)})
            for r in loose
        )
    others = [
        member(e, e.role_template.value, i)
        for i, e in enumerate(employees.values())
        if e.id not in in_team
    ]
    return TeamMapOut(teams=out, others=others)


@router.get("", response_model=TeamMapOut, summary="Team map with 7-day counts")
async def team_map(
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> TeamMapOut:
    return await _map(session, tenant, clock)


@router.post(
    "/hire",
    response_model=TeamMapOut,
    status_code=status.HTTP_201_CREATED,
    summary="Hire a whole AI team from a template (one tap)",
)
async def hire(
    body: HireTeamIn,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> TeamMapOut:
    template = TEAM_TEMPLATES[body.template_id]
    exists = await session.scalar(
        select(Team.id).where(
            Team.business_id == tenant.business_id, Team.template_id == template.id
        )
    )
    if exists is not None:
        raise AppError(409, "team_exists", "This team is already hired")
    business = await _business(session, tenant)
    languages = (
        body.languages or [Locale(x) for x in business.languages if x in Locale] or [Locale.EN]
    )
    reuse: dict[str, uuid.UUID] = {}
    if body.reuse_existing:
        taken: set[uuid.UUID] = set(
            await session.scalars(
                select(TeamMember.employee_id).where(TeamMember.business_id == tenant.business_id)
            )
        )
        existing = list(
            await session.scalars(
                select(Employee)
                .where(Employee.business_id == tenant.business_id)
                .order_by(Employee.created_at)
            )
        )
        for role in template.roles:
            match = next(
                (e for e in existing if e.role_template == role.base and e.id not in taken), None
            )
            if match is not None and role.id in {"lead_caller", "receptionist"}:
                reuse[role.id] = match.id
                taken.add(match.id)
    await hire_team(
        session,
        tenant.business_id,
        template,
        languages=languages[:3],
        names=dict(body.names),
        reuse=reuse,
    )
    await session.commit()
    return await _map(session, tenant, clock)


@router.post("/{team_id}/activate", response_model=TeamMapOut, summary="Put the team to work")
async def activate(
    team_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> TeamMapOut:
    team = await session.scalar(
        select(Team).where(Team.id == team_id, Team.business_id == tenant.business_id)
    )
    if team is None:
        raise not_found("Team")
    await activate_team(session, team)
    await session.commit()
    return await _map(session, tenant, clock)


# --- hand-off rules ------------------------------------------------------------------------------


async def _check_rule(
    session: AsyncSession, tenant: Tenant, from_id: uuid.UUID, to_id: uuid.UUID | None, task: str
) -> None:
    ids = await _employee_ids(session, tenant)
    if from_id not in ids or (to_id is not None and to_id not in ids):
        raise AppError(422, "validation_error", "Unknown employee")
    if to_id is None and task != "brief_staff":
        raise AppError(422, "validation_error", "Choose who the customer is passed to")


async def _get_rule(session: AsyncSession, tenant: Tenant, rule_id: uuid.UUID) -> HandoffRule:
    rule = await session.scalar(
        select(HandoffRule).where(
            HandoffRule.id == rule_id, HandoffRule.business_id == tenant.business_id
        )
    )
    if rule is None:
        raise not_found("Hand-off rule")
    return rule


@router.post(
    "/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED, summary="Add a hand-off"
)
async def create_rule(
    body: RuleIn,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> HandoffRule:
    await _check_rule(session, tenant, body.from_employee_id, body.to_employee_id, body.task)
    if body.team_id is not None:
        team = await session.scalar(
            select(Team.id).where(Team.id == body.team_id, Team.business_id == tenant.business_id)
        )
        if team is None:
            raise not_found("Team")
    data = body.model_dump(exclude={"condition"})
    rule = HandoffRule(
        business_id=tenant.business_id,
        condition=body.condition.model_dump() if body.condition else {},
        **data,
    )
    session.add(rule)
    await session.commit()
    return rule


@router.patch("/rules/{rule_id}", response_model=RuleOut, summary="Change a hand-off")
async def update_rule(
    rule_id: uuid.UUID,
    body: RulePatch,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> HandoffRule:
    rule = await _get_rule(session, tenant, rule_id)
    changes = body.model_dump(exclude_unset=True)
    if "condition" in changes:
        changes["condition"] = changes["condition"] or {}
    for key, value in changes.items():
        setattr(rule, key, value)
    await _check_rule(session, tenant, rule.from_employee_id, rule.to_employee_id, rule.task)
    rule.version += 1  # tasks keep the version they were created under
    await session.commit()
    return rule


@router.delete(
    "/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a hand-off"
)
async def delete_rule(
    rule_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    await session.delete(await _get_rule(session, tenant, rule_id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- follow-up tasks -----------------------------------------------------------------------------


@router.get("/tasks", response_model=list[TaskOut], summary="Follow-up tasks (hand-offs, briefs)")
async def list_tasks(
    status_: list[str] | None = Query(None, alias="status", max_length=7),
    employee_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[TaskOut]:
    query = (
        select(FollowUpTask, Contact.name)
        .outerjoin(Contact, Contact.id == FollowUpTask.contact_id)
        .where(FollowUpTask.business_id == tenant.business_id)
        .order_by(FollowUpTask.created_at.desc())
        .limit(limit)
    )
    if status_:
        query = query.where(FollowUpTask.status.in_(status_))
    if employee_id is not None:
        query = query.where(FollowUpTask.to_employee_id == employee_id)
    rows = await session.execute(query)
    return [
        TaskOut.model_validate(task).model_copy(update={"customer_name": name})
        for task, name in rows
    ]
