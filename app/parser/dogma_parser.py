"""Parse and validate DOGMA API response payloads (no SQLAlchemy)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class DogmaParseError(Exception):
    """Raised when DOGMA payload does not match the expected schema."""


class DogmaObject(BaseModel):
    """Minimal validated fields of a DOGMA listing object."""

    model_config = ConfigDict(extra="allow")

    id: int | str
    project_id: int
    project_name: str
    cost: int
    cost_sale: int = 0
    area: float
    room: int
    type: int
    status: int
    floor: int | None = None
    floor_max: int | None = None
    address: str | None = None
    flat_number: int | str | None = None

    @field_validator("project_name")
    @classmethod
    def _non_empty_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("project_name must be non-empty")
        return value


class DogmaFilterPage(BaseModel):
    """Parsed `data` section of objects/filter response."""

    count: int = Field(ge=0)
    objects: list[DogmaObject]


class DogmaProject(BaseModel):
    """Project entry from /v4/projects/config."""

    model_config = ConfigDict(extra="allow")

    id: int
    name: str
    city_name: str | None = None

    @field_validator("name")
    @classmethod
    def _non_empty_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must be non-empty")
        return value


class DogmaParser:
    """Extract and validate DOGMA JSON structures."""

    def parse_filter_response(self, payload: dict[str, Any]) -> DogmaFilterPage:
        data = self._require_data_object(payload)
        if "objects" not in data or "count" not in data:
            raise DogmaParseError("filter response data must contain 'objects' and 'count'")
        if not isinstance(data["objects"], list):
            raise DogmaParseError("data.objects must be a list")
        try:
            return DogmaFilterPage.model_validate(
                {"count": data["count"], "objects": data["objects"]}
            )
        except ValidationError as exc:
            raise DogmaParseError(f"invalid filter objects schema: {exc}") from exc

    def parse_projects_response(self, payload: dict[str, Any]) -> list[DogmaProject]:
        data = self._require_data_object(payload)
        projects = data.get("projects")
        if not isinstance(projects, list):
            raise DogmaParseError("projects response data.projects must be a list")
        try:
            return [DogmaProject.model_validate(item) for item in projects]
        except ValidationError as exc:
            raise DogmaParseError(f"invalid projects schema: {exc}") from exc

    def _require_data_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise DogmaParseError("payload must be an object")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise DogmaParseError("payload.data must be an object")
        return data
