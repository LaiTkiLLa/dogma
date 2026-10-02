"""Normalize DOGMA objects into internal sync payloads (no SQLAlchemy)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.parser.dogma_parser import DogmaObject, DogmaProject


@dataclass(frozen=True, slots=True)
class NormalizedResidentialComplex:
    source_project_id: int
    name: str
    name_normalized: str
    city_name: str | None


@dataclass(frozen=True, slots=True)
class NormalizedApartment:
    source_id: str
    source_project_id: int
    project_name: str
    price: int
    price_base: int | None
    area: Decimal
    rooms: int
    property_type: str
    floor: int | None
    floors_total: int | None
    status_code: int
    url: str
    address: str | None
    flat_number: str | None
    raw_payload: dict[str, Any]


def normalize_complex_name(name: str) -> str:
    """trim + lowercase + ё→е for exact/partial ЖК search."""
    return name.strip().lower().replace("ё", "е")


def map_property_type(dogma_type: int) -> str:
    """Map DOGMA object type code to internal property_type."""
    if dogma_type == 1:
        return "apartment"
    return str(dogma_type)


class Normalizer:
    """Map validated DOGMA DTOs to internal normalized records."""

    def __init__(self, *, public_base_url: str = "https://dogma.ru") -> None:
        self._public_base_url = public_base_url.rstrip("/")

    def normalize_project(self, project: DogmaProject) -> NormalizedResidentialComplex:
        name = project.name.strip()
        return NormalizedResidentialComplex(
            source_project_id=project.id,
            name=name,
            name_normalized=normalize_complex_name(name),
            city_name=project.city_name.strip() if project.city_name else None,
        )

    def normalize_apartment(self, obj: DogmaObject) -> NormalizedApartment:
        source_id = str(obj.id)
        price_base = int(obj.cost)
        cost_sale = int(obj.cost_sale)
        price = cost_sale if cost_sale > 0 else price_base
        flat_number = None if obj.flat_number is None else str(obj.flat_number)
        raw_payload = obj.model_dump(mode="python")

        return NormalizedApartment(
            source_id=source_id,
            source_project_id=obj.project_id,
            project_name=obj.project_name.strip(),
            price=price,
            price_base=price_base,
            area=Decimal(str(obj.area)),
            rooms=int(obj.room),
            property_type=map_property_type(obj.type),
            floor=obj.floor,
            floors_total=obj.floor_max,
            status_code=int(obj.status),
            url=f"{self._public_base_url}/flat/{source_id}",
            address=obj.address,
            flat_number=flat_number,
            raw_payload=raw_payload,
        )

    def complex_from_apartment(self, apartment: NormalizedApartment) -> NormalizedResidentialComplex:
        """Fallback ЖК record when project is missing from projects/config."""
        return NormalizedResidentialComplex(
            source_project_id=apartment.source_project_id,
            name=apartment.project_name,
            name_normalized=normalize_complex_name(apartment.project_name),
            city_name=None,
        )
