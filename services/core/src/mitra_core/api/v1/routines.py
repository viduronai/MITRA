"""Routines (AUTO-01..05): sentence-style builder, library, dry run, run now, history."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.errors import AppError, not_found
from mitra_core.models import Business, Contact, Employee, Routine, RoutineRun, TeamMember
from mitra_core.models.enums import MemberRole
from mitra_core.schemas.team import (
    DecisionIn,
    DryRunIn,
    DryRunOut,
    EventIn,
    FromLibraryIn,
    LibraryRoutineOut,
    PersonOut,
    RoutineIn,
    RoutineOut,
    RoutinePatch,
    RunOut,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role
from mitra_core.team import approval_handlers, ports  # noqa: F401  (registers the handler)
from mitra_core.team.routines.events import fire_event
from mitra_core.team.routines.library import LIBRARY_BY_ID, LibraryRoutine, library_for
from mitra_core.team.routines.runs import (
    decide_run,
    preview,
    refresh_results,
    schedule_next,
    start_run,
)
from mitra_core.team.routines.spec import EventTrigger, RoutineSpec, sentence

router = APIRouter(prefix="/routines", tags=["routines"])
_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)
MAX_ROUTINES = 50


async def _business(session: AsyncSession, tenant: Tenant) -> Business:
    business = await session.get(Business, tenant.business_id)
    if business is None:
        raise not_found("Business")
    return business


async def _employee(session: AsyncSession, tenant: Tenant, employee_id: uuid.UUID) -> Employee:
    employee = await session.scalar(
        select(Employee).where(
            Employee.id == employee_id, Employee.business_id == tenant.business_id
        )
    )
    if employee is None:
        raise AppError(422, "validation_error", "Unknown employee")
    return employee


async def _out(session: AsyncSession, tenant: Tenant, routine: Routine) -> RoutineOut:
    spec = RoutineSpec.model_validate(routine.spec)
    employee = await session.get(Employee, spec.action.employee_id)
    stock = LIBRARY_BY_ID.get(routine.library_id or "")
    return RoutineOut(
        id=routine.id,
        name=routine.name,
        library_id=routine.library_id,
        name_is_default=stock is not None and routine.name == stock.name,
        spec=routine.spec,
        sentence=sentence(spec, employee.name if employee else "Your employee"),
        enabled=routine.enabled,
        next_run_at=routine.next_run_at,
        last_run_at=routine.last_run_at,
    )


async def _get(session: AsyncSession, tenant: Tenant, routine_id: uuid.UUID) -> Routine:
    routine = await session.scalar(
        select(Routine).where(Routine.id == routine_id, Routine.business_id == tenant.business_id)
    )
    if routine is None:
        raise not_found("Routine")
    return routine


async def _pick_employee(
    session: AsyncSession, tenant: Tenant, item: LibraryRoutine
) -> uuid.UUID | None:
    """The first employee whose team role (or base role) the library routine prefers."""
    roles = {
        m.employee_id: m.team_role
        for m in await session.scalars(
            select(TeamMember).where(TeamMember.business_id == tenant.business_id)
        )
    }
    employees = list(
        await session.scalars(
            select(Employee)
            .where(Employee.business_id == tenant.business_id)
            .order_by(Employee.created_at)
        )
    )
    for wanted in item.roles:
        for e in employees:
            if roles.get(e.id) == wanted or e.role_template.value == wanted:
                return e.id
    return employees[0].id if employees else None


@router.get("/library", response_model=list[LibraryRoutineOut], summary="Ready-made routines")
async def library(
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[LibraryRoutineOut]:
    business = await _business(session, tenant)
    return [
        LibraryRoutineOut(
            id=item.id,
            name=item.name,
            trigger=item.trigger,
            audience=item.audience,
            goal=item.goal,
            verb=item.verb,
            employee_id=await _pick_employee(session, tenant, item),
        )
        for item in library_for(business.industry)
    ]


@router.get("", response_model=list[RoutineOut], summary="List routines")
async def list_routines(
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[RoutineOut]:
    rows = await session.scalars(
        select(Routine)
        .where(Routine.business_id == tenant.business_id)
        .order_by(Routine.created_at)
    )
    return [await _out(session, tenant, r) for r in rows]


async def _save(
    session: AsyncSession,
    tenant: Tenant,
    clock: Clock,
    *,
    name: str,
    spec: RoutineSpec,
    enabled: bool,
    library_id: str | None = None,
) -> Routine:
    await _employee(session, tenant, spec.action.employee_id)
    count = len(
        list(
            await session.scalars(
                select(Routine.id).where(Routine.business_id == tenant.business_id)
            )
        )
    )
    if count >= MAX_ROUTINES:
        raise AppError(409, "too_many_routines", f"At most {MAX_ROUTINES} routines")
    routine = Routine(
        business_id=tenant.business_id,
        name=name,
        library_id=library_id,
        spec=spec.model_dump(mode="json"),
        enabled=enabled,
        created_by=tenant.user.id,
    )
    schedule_next(routine, (await _business(session, tenant)).timezone, clock())
    session.add(routine)
    await session.commit()
    return routine


@router.post(
    "", response_model=RoutineOut, status_code=status.HTTP_201_CREATED, summary="New routine"
)
async def create_routine(
    body: RoutineIn,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> RoutineOut:
    routine = await _save(
        session, tenant, clock, name=body.name, spec=body.spec, enabled=body.enabled
    )
    return await _out(session, tenant, routine)


@router.post(
    "/from-library",
    response_model=RoutineOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a ready-made routine",
)
async def from_library(
    body: FromLibraryIn,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> RoutineOut:
    item = LIBRARY_BY_ID.get(body.library_id)
    if item is None:
        raise not_found("Routine template")
    employee_id = body.employee_id or await _pick_employee(session, tenant, item)
    if employee_id is None:
        raise AppError(409, "no_employee", "Hire an employee first")
    spec = RoutineSpec.model_validate(
        {
            "trigger": item.trigger,
            "audience": item.audience,
            "action": {"verb": item.verb, "employee_id": str(employee_id), "goal": item.goal},
        }
    )
    routine = await _save(
        session,
        tenant,
        clock,
        name=item.name,
        spec=spec,
        enabled=body.enabled,
        library_id=item.id,
    )
    return await _out(session, tenant, routine)


@router.patch("/{routine_id}", response_model=RoutineOut, summary="Edit / turn on / turn off")
async def update_routine(
    routine_id: uuid.UUID,
    body: RoutinePatch,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> RoutineOut:
    routine = await _get(session, tenant, routine_id)
    if body.spec is not None:
        await _employee(session, tenant, body.spec.action.employee_id)
        routine.spec = body.spec.model_dump(mode="json")
    if body.name is not None:
        routine.name = body.name
    if body.enabled is not None:
        routine.enabled = body.enabled
    schedule_next(routine, (await _business(session, tenant)).timezone, clock())
    await session.commit()
    return await _out(session, tenant, routine)


@router.delete("/{routine_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete")
async def delete_routine(
    routine_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    await session.delete(await _get(session, tenant, routine_id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/dry-run", response_model=DryRunOut, summary="Show me who will be contacted")
async def dry_run(
    body: DryRunIn,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> DryRunOut:
    employee = await _employee(session, tenant, body.spec.action.employee_id)
    found = await preview(session, tenant.business_id, body.spec, now=clock())
    note = None
    if isinstance(body.spec.trigger, EventTrigger):
        note = "event"  # contacts the one person each event is about
    return DryRunOut(
        sentence=sentence(body.spec, employee.name),
        would_contact=[
            PersonOut(contact_id=p.contact_id, name=p.name, last4=p.last4) for p in found.contacted
        ],
        skipped=[
            PersonOut(contact_id=p.contact_id, name=p.name, last4=p.last4, skip=p.skip)
            for p in found.skipped
        ],
        needs_approval=len(found.contacted) > body.spec.approval_over,
        note=note,
    )


@router.post("/{routine_id}/run", response_model=RunOut, summary="Run now")
async def run_now(
    routine_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> RoutineRun:
    routine = await _get(session, tenant, routine_id)
    if isinstance(RoutineSpec.model_validate(routine.spec).trigger, EventTrigger):
        raise AppError(422, "event_routine", "This routine runs when its event happens")
    run = await start_run(session, routine, trigger="manual", now=clock())
    await session.commit()
    return run


@router.get("/{routine_id}/runs", response_model=list[RunOut], summary="What ran, and results")
async def history(
    routine_id: uuid.UUID,
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[RunOut]:
    await _get(session, tenant, routine_id)
    runs = await session.scalars(
        select(RoutineRun)
        .where(RoutineRun.routine_id == routine_id, RoutineRun.business_id == tenant.business_id)
        .order_by(RoutineRun.started_at.desc())
        .limit(30)
    )
    out = []
    for run in runs:
        item = RunOut.model_validate(run)
        out.append(item.model_copy(update={"contacts": await refresh_results(session, run)}))
    return out


@router.post("/runs/{run_id}/decision", response_model=RunOut, summary="Approve or decline a run")
async def decide(
    run_id: uuid.UUID,
    body: DecisionIn,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> RoutineRun:
    run = await session.scalar(
        select(RoutineRun).where(
            RoutineRun.id == run_id, RoutineRun.business_id == tenant.business_id
        )
    )
    if run is None:
        raise not_found("Routine run")
    if run.status != "awaiting_approval":
        raise AppError(409, "already_decided", "This run is not waiting for approval")
    ref = run.approval_ref
    await decide_run(session, run, approved=body.approved, now=clock())
    if ref:
        await ports.withdraw_approval(session, tenant.business_id, ref)
    await session.commit()
    return run


@router.post(
    "/events", response_model=list[RunOut], summary="Tell routines something happened (no-show...)"
)
async def report_event(
    body: EventIn,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> list[RoutineRun]:
    contact = await session.scalar(
        select(Contact.id).where(
            Contact.id == body.contact_id, Contact.business_id == tenant.business_id
        )
    )
    if contact is None:
        raise not_found("Customer")
    runs = await fire_event(
        session, tenant.business_id, body.event, contact_id=body.contact_id, now=clock()
    )
    await session.commit()
    return runs
