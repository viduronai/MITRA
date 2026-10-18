from __future__ import annotations

from typing import Literal

from mitra_core.schemas.common import ResponseModel

StepKey = Literal["business", "role", "teach", "voice", "test_call", "go_live"]


class StepOut(ResponseModel):
    key: StepKey
    done: bool


class ProgressOut(ResponseModel):
    steps: list[StepOut]
    percent: int
    next: StepKey | None
