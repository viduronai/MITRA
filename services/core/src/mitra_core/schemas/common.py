from __future__ import annotations

from typing import Annotated, Any, ClassVar, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from mitra_core.models.enums import Locale

E164_PATTERN = r"^\+[1-9][0-9]{7,14}$"

E164Phone = Annotated[str, StringConstraints(pattern=E164_PATTERN)]


def _unique[T](items: list[T]) -> list[T]:
    if len(set(items)) != len(items):
        raise ValueError("items must be unique")
    return items


Languages = Annotated[list[Locale], Field(min_length=1, max_length=3), AfterValidator(_unique)]


Name60 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Name120 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
City = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class RequestModel(BaseModel):
    """Base for request bodies: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PatchModel(RequestModel):
    """PATCH body: omitted fields are untouched; explicit null only for ``_nullable`` fields."""

    _nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_nulls(self) -> Self:
        bad = sorted(
            f for f in self.model_fields_set if getattr(self, f) is None and f not in self._nullable
        )
        if bad:
            raise ValueError(f"fields cannot be null: {', '.join(bad)}")
        return self


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
