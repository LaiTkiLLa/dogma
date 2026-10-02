"""Deterministic apartment search over PostgreSQL via repository."""

from __future__ import annotations

from app.apartments.repository import ApartmentRepository
from app.apartments.schemas import (
    ApartmentSearchFilters,
    ApartmentSearchItem,
    ApartmentSearchResult,
)
from app.parser.normalizer import normalize_complex_name


class SearchService:
    """Apply search filters and return top matching apartments."""

    def __init__(self, repository: ApartmentRepository) -> None:
        self._repository = repository

    async def search(self, filters: ApartmentSearchFilters) -> ApartmentSearchResult:
        complex_ids = None
        if filters.residential_complex is not None and filters.residential_complex.strip():
            normalized = normalize_complex_name(filters.residential_complex)
            complex_ids = await self._repository.find_complex_ids_by_name_exact(normalized)
            if not complex_ids:
                complex_ids = await self._repository.find_complex_ids_by_name_partial(
                    normalized
                )
            if not complex_ids:
                return ApartmentSearchResult(total=0, returned=0, items=[])

        total, rows = await self._repository.search_apartments(
            min_price=filters.min_price,
            max_price=filters.max_price,
            min_area=filters.min_area,
            max_area=filters.max_area,
            rooms=filters.rooms,
            residential_complex_ids=complex_ids,
            limit=filters.limit,
        )

        items = [
            ApartmentSearchItem(
                id=apartment.id,
                source_id=apartment.source_id,
                residential_complex=complex_name,
                rooms=apartment.rooms,
                area=apartment.area,
                price=apartment.price,
                price_base=apartment.price_base,
                floor=apartment.floor,
                floors_total=apartment.floors_total,
                status_code=apartment.status_code,
                address=apartment.address,
                url=apartment.url,
            )
            for apartment, complex_name in rows
        ]
        return ApartmentSearchResult(total=total, returned=len(items), items=items)
