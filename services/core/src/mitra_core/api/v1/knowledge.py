"""What the employees know: sources, facts and gaps (contract §3)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core import idempotency
from mitra_core.errors import not_found
from mitra_core.knowledge.fetch import Fetcher, get_fetcher
from mitra_core.knowledge.gaps import missing_gaps
from mitra_core.knowledge.service import ingest_text, ingest_url
from mitra_core.models import Business, Fact, KnowledgeSource
from mitra_core.models.enums import (
    FactStatus,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
    MemberRole,
)
from mitra_core.schemas.knowledge import (
    FactIn,
    FactOut,
    FactUpdate,
    GapOut,
    SourceIn,
    SourceOut,
    UrlSourceIn,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role
from mitra_core.tenancy import TenantContext

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_SOURCE_ENDPOINT = "POST /v1/knowledge/sources"
_FACT_ENDPOINT = "POST /v1/knowledge/facts"
_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)


async def _get_fact(session: AsyncSession, tenant: Tenant, fact_id: uuid.UUID) -> Fact:
    fact = await session.scalar(
        select(Fact).where(Fact.id == fact_id, Fact.business_id == tenant.business_id)
    )
    if fact is None:
        raise not_found("Fact")
    return fact


@router.post(
    "/sources",
    status_code=status.HTTP_201_CREATED,
    response_model=SourceOut,
    summary="Teach from a web page (processed in the background) or pasted text",
)
async def create_source(
    body: SourceIn,
    background: BackgroundTasks,
    idempotency_key: idempotency.IdempotencyKey = None,
    fetcher: Fetcher = Depends(get_fetcher),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> SourceOut | JSONResponse:
    payload = body.model_dump(mode="json")
    req_hash, replayed = await idempotency.lookup_for_business(
        session,
        business_id=tenant.business_id,
        endpoint=_SOURCE_ENDPOINT,
        key=idempotency_key,
        payload=payload,
    )
    if replayed is not None:
        return replayed

    if isinstance(body, UrlSourceIn):
        url = str(body.url)
        source = KnowledgeSource(
            business_id=tenant.business_id,
            type=KnowledgeSourceType.URL,
            status=KnowledgeSourceStatus.PROCESSING,
            url=url,
            title=body.url.host,
        )
        session.add(source)
    else:
        source = KnowledgeSource(
            business_id=tenant.business_id,
            type=KnowledgeSourceType.TEXT,
            status=KnowledgeSourceStatus.PROCESSING,
            content=body.text,
        )
        session.add(source)
        await session.flush()
        ingest_text(session, source, body.text)
    await session.flush()
    result = SourceOut.model_validate(source)
    if idempotency_key:
        idempotency.save(
            session,
            business_id=tenant.business_id,
            user_id=tenant.user.id,
            endpoint=_SOURCE_ENDPOINT,
            key=idempotency_key,
            req_hash=req_hash,
            status=status.HTTP_201_CREATED,
            body=result.model_dump(mode="json"),
        )
    await session.commit()
    if source.type == KnowledgeSourceType.URL:
        ctx = TenantContext(user_id=tenant.user.id, business_id=tenant.business_id)
        background.add_task(ingest_url, ctx, source.id, fetcher)
    return result


@router.get("/sources", response_model=list[SourceOut], summary="List knowledge sources")
async def list_sources(
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[KnowledgeSource]:
    rows = await session.scalars(
        select(KnowledgeSource)
        .where(KnowledgeSource.business_id == tenant.business_id)
        .order_by(KnowledgeSource.created_at.desc(), KnowledgeSource.id)
        .limit(200)
    )
    return list(rows)


@router.get("/facts", response_model=list[FactOut], summary="List facts")
async def list_facts(
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[Fact]:
    rows = await session.scalars(
        select(Fact)
        .where(Fact.business_id == tenant.business_id)
        .order_by(Fact.category, Fact.created_at, Fact.id)
        .limit(1000)
    )
    return list(rows)


@router.post(
    "/facts",
    status_code=status.HTTP_201_CREATED,
    response_model=FactOut,
    summary="Add a fact by hand (confirmed)",
)
async def create_fact(
    body: FactIn,
    idempotency_key: idempotency.IdempotencyKey = None,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> FactOut | JSONResponse:
    payload = body.model_dump(mode="json")
    req_hash, replayed = await idempotency.lookup_for_business(
        session,
        business_id=tenant.business_id,
        endpoint=_FACT_ENDPOINT,
        key=idempotency_key,
        payload=payload,
    )
    if replayed is not None:
        return replayed
    fact = Fact(business_id=tenant.business_id, status=FactStatus.CONFIRMED, **payload)
    session.add(fact)
    await session.flush()
    result = FactOut.model_validate(fact)
    if idempotency_key:
        idempotency.save(
            session,
            business_id=tenant.business_id,
            user_id=tenant.user.id,
            endpoint=_FACT_ENDPOINT,
            key=idempotency_key,
            req_hash=req_hash,
            status=status.HTTP_201_CREATED,
            body=result.model_dump(mode="json"),
        )
    await session.commit()
    return result


@router.patch("/facts/{fact_id}", response_model=FactOut, summary="Edit or confirm a fact")
async def update_fact(
    fact_id: uuid.UUID,
    body: FactUpdate,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> Fact:
    fact = await _get_fact(session, tenant, fact_id)
    for field, value in body.model_dump(mode="json", exclude_unset=True).items():
        setattr(fact, field, value)
    await session.flush()
    await session.commit()
    return fact


@router.delete(
    "/facts/{fact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a fact",
)
async def delete_fact(
    fact_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    fact = await _get_fact(session, tenant, fact_id)
    await session.delete(fact)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/gaps", response_model=list[GapOut], summary="Important facts still missing")
async def list_gaps(
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[GapOut]:
    business = await session.get(Business, tenant.business_id)
    if business is None:
        raise not_found("Business")
    rows = await session.execute(
        select(Fact.category, Fact.key, Fact.value).where(Fact.business_id == tenant.business_id)
    )
    gaps = missing_gaps(business.industry, [(c, k, v) for c, k, v in rows])
    return [GapOut(category=g.category, key=g.key, question=g.question) for g in gaps]
