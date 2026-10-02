"""Apartment search input/output schemas."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApartmentSearchFilters(BaseModel):
    """Deterministic search filters for active apartments."""

    model_config = ConfigDict(extra="forbid")

    min_price: int | None = None
    max_price: int | None = None
    min_area: float | None = None
    max_area: float | None = None
    rooms: int | None = None  # 0 = studio
    residential_complex: str | None = None
    limit: int = 5

    @field_validator("limit", mode="before")
    @classmethod
    def _clamp_limit(cls, value: object) -> object:
        if value is None:
            return 5
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value < 1:
            return 5
        return value

    @field_validator("limit")
    @classmethod
    def _limit_range(cls, value: int) -> int:
        return min(value, 5)


class ApartmentSearchItem(BaseModel):
    """One apartment in a search result."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: str
    residential_complex: str
    rooms: int
    area: Decimal
    price: int
    price_base: int | None = None
    floor: int | None = None
    floors_total: int | None = None
    status_code: int
    address: str | None = None
    url: str


class ApartmentSearchResult(BaseModel):
    """SearchService / tool output."""

    total: int
    returned: int
    items: list[ApartmentSearchItem] = Field(default_factory=list)
