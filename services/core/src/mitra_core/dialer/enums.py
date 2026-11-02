"""Dialer and campaign enums (Postgres native enums, prefixed ``dlr_``)."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"  # waiting for ``not_before`` and a free channel
    DIALING = "dialing"  # placed with the carrier; waiting for the outcome
    COMPLETED = "completed"  # answered (or the ladder ran out: see ``last_outcome``)
    FAILED = "failed"  # retries exhausted without an answer
    BLOCKED = "blocked"  # compliance said no (reasons logged)
    CANCELLED = "cancelled"  # campaign stopped / owner cancelled


ACTIVE_JOB_STATUSES = (JobStatus.QUEUED, JobStatus.DIALING)


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ContactStatus(StrEnum):
    PENDING = "pending"  # imported, not yet queued (campaign not started)
    QUEUED = "queued"  # has an active outbound job
    DONE = "done"  # has a result bucket
    SKIPPED = "skipped"  # called recently / duplicate: never queued


class ResultBucket(StrEnum):
    INTERESTED = "interested"
    CALL_BACK = "call_back"
    NOT_INTERESTED = "not_interested"
    NO_ANSWER = "no_answer"
    BLOCKED = "blocked"
