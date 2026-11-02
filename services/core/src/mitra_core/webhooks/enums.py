"""Outgoing webhook enums (INT-13)."""

from __future__ import annotations

from enum import StrEnum


class WebhookEvent(StrEnum):
    CALL_ENDED = "call.ended"
    LEAD_CREATED = "lead.created"
    CAMPAIGN_FINISHED = "campaign.finished"
    TEST = "test"  # "Send test event": one endpoint, regardless of its subscriptions


SUBSCRIBABLE = (WebhookEvent.CALL_ENDED, WebhookEvent.LEAD_CREATED, WebhookEvent.CAMPAIGN_FINISHED)


class DeliveryStatus(StrEnum):
    PENDING = "pending"  # waiting for its first try or a retry
    SUCCEEDED = "succeeded"
    FAILED = "failed"  # gave up after the last retry
