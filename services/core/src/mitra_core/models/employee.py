from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from mitra_core.models.enums import EmployeeStatus, RoleTemplate, VoiceTier

EMPTY_BEHAVIOUR_SQL = """'{"ask_for": [], "never_say": [], "transfer_when": []}'::jsonb"""


class Employee(UUIDPrimaryKey, Timestamps, Base):
    """An AI voice employee belonging to one business."""

    __tablename__ = "employee"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    role_template: Mapped[RoleTemplate] = mapped_column(pg_enum(RoleTemplate, "role_template"))
    voice_tier: Mapped[VoiceTier] = mapped_column(
        pg_enum(VoiceTier, "voice_tier"), server_default=VoiceTier.NATURAL.value
    )
    status: Mapped[EmployeeStatus] = mapped_column(
        pg_enum(EmployeeStatus, "employee_status"), server_default=EmployeeStatus.TRAINING.value
    )
    languages: Mapped[list[str]] = mapped_column(server_default=text("'{}'::text[]"))
    working_hours: Mapped[dict[str, Any] | None]
    voice_id: Mapped[str | None] = mapped_column(String(64))
    greeting: Mapped[str | None] = mapped_column(String(300))
    # {"ask_for": [...], "never_say": [...], "transfer_when": [...]}, validated by the API.
    behaviour: Mapped[dict[str, Any]] = mapped_column(server_default=text(EMPTY_BEHAVIOUR_SQL))
