"""Tool argument schemas exposed to the LLM agent."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchApartmentsArgs(BaseModel):
    """Аргументы инструмента `search_apartments`."""

    model_config = ConfigDict(extra="forbid")

    min_price: int | None = Field(
        default=None,
        description="Минимальная цена квартиры (включительно), в рублях",
    )
    max_price: int | None = Field(
        default=None,
        description="Максимальная цена квартиры (включительно), в рублях",
    )
    min_area: float | None = Field(
        default=None,
        description="Минимальная площадь в м² (включительно)",
    )
    max_area: float | None = Field(
        default=None,
        description="Максимальная площадь в м² (включительно)",
    )
    rooms: int | None = Field(
        default=None,
        description="Точное число комнат; 0 означает студию",
    )
    residential_complex: str | None = Field(
        default=None,
        description="Название ЖК (сначала точное совпадение, затем частичное)",
    )
    limit: int = Field(
        default=5,
        description="Сколько квартир вернуть (от 1 до 5, по умолчанию 5)",
    )

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
    def _limit_max(cls, value: int) -> int:
        return min(value, 5)
