"""Knowledge ingestion: turn a source into facts (synchronously for text, in the background
for URLs)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.db import tenant_session
from mitra_core.knowledge.extract import Extraction, extract_from_html, extract_from_text
from mitra_core.knowledge.fetch import Fetcher, FetchError
from mitra_core.logging import get_logger
from mitra_core.models import Fact, KnowledgeSource
from mitra_core.models.enums import KnowledgeSourceStatus
from mitra_core.tenancy import TenantContext

log = get_logger(__name__)


def apply_extraction(session: AsyncSession, source: KnowledgeSource, result: Extraction) -> None:
    source.title = result.title or source.title
    source.status = KnowledgeSourceStatus.READY
    source.error = None
    for fact in result.facts:
        session.add(
            Fact(
                business_id=source.business_id,
                source_id=source.id,
                category=fact.category,
                key=fact.key,
                value=fact.value,
                status=fact.status,
            )
        )


def ingest_text(session: AsyncSession, source: KnowledgeSource, text: str) -> None:
    apply_extraction(session, source, extract_from_text(text))


async def ingest_url(ctx: TenantContext, source_id: uuid.UUID, fetcher: Fetcher) -> None:
    """Background task: fetch the page, extract facts, mark the source ready or failed."""
    error: str | None = None
    extraction: Extraction | None = None
    async with tenant_session(ctx) as session:
        source = await session.get(KnowledgeSource, source_id)
        if source is None or source.url is None:
            return
        url = source.url
        await session.rollback()  # don't hold a transaction open while fetching

        try:
            page = await fetcher.fetch(url)
            extraction = extract_from_html(page.text)
        except FetchError as exc:
            error = str(exc)
        except Exception as exc:  # the task must always leave the source in a final state
            log.warning("knowledge_ingest_failed", exc_type=type(exc).__name__)
            error = "Something went wrong while reading this page."

        source = await session.get(KnowledgeSource, source_id, populate_existing=True)
        if source is None:
            return
        if extraction is not None:
            apply_extraction(session, source, extraction)
        else:
            source.status = KnowledgeSourceStatus.FAILED
            source.error = error
        await session.commit()
