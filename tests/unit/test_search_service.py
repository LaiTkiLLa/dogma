"""Unit tests for SearchService residential-complex resolution and filters."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.apartments.schemas import ApartmentSearchFilters
from app.apartments.search_service import SearchService


def _apartment(
    *,
    source_id: str,
    price: int,
    area: str,
    rooms: int,
    complex_name: str,
):
    apt = AsyncMock()
    apt.id = uuid4()
    apt.source_id = source_id
    apt.price = price
    apt.price_base = price + 1000
    apt.area = Decimal(area)
    apt.rooms = rooms
    apt.floor = 3
    apt.floors_total = 16
    apt.status_code = 2
    apt.address = "test address"
    apt.url = f"https://dogma.ru/flat/{source_id}"
    return apt, complex_name


@pytest.mark.asyncio
async def test_search_without_complex_calls_repository_once() -> None:
    repo = AsyncMock()
    repo.search_apartments.return_value = (
        1,
        [_apartment(source_id="1", price=5_000_000, area="40.0", rooms=1, complex_name="A")],
    )
    service = SearchService(repo)

    result = await service.search(ApartmentSearchFilters(max_price=10_000_000, limit=5))

    assert result.total == 1
    assert result.returned == 1
    assert result.items[0].source_id == "1"
    repo.find_complex_ids_by_name_exact.assert_not_called()
    repo.search_apartments.assert_awaited_once()
    kwargs = repo.search_apartments.await_args.kwargs
    assert kwargs["max_price"] == 10_000_000
    assert kwargs["residential_complex_ids"] is None
    assert kwargs["limit"] == 5


@pytest.mark.asyncio
async def test_search_uses_exact_complex_match_when_found() -> None:
    complex_id = uuid4()
    repo = AsyncMock()
    repo.find_complex_ids_by_name_exact.return_value = [complex_id]
    repo.search_apartments.return_value = (0, [])
    service = SearchService(repo)

    await service.search(ApartmentSearchFilters(residential_complex="  МКР Самолёт "))

    repo.find_complex_ids_by_name_exact.assert_awaited_once_with("мкр самолет")
    repo.find_complex_ids_by_name_partial.assert_not_called()
    assert repo.search_apartments.await_args.kwargs["residential_complex_ids"] == [complex_id]


@pytest.mark.asyncio
async def test_search_falls_back_to_partial_complex_match() -> None:
    complex_id = uuid4()
    repo = AsyncMock()
    repo.find_complex_ids_by_name_exact.return_value = []
    repo.find_complex_ids_by_name_partial.return_value = [complex_id]
    repo.search_apartments.return_value = (
        1,
        [_apartment(source_id="9", price=7_000_000, area="55.5", rooms=2, complex_name="X")],
    )
    service = SearchService(repo)

    result = await service.search(ApartmentSearchFilters(residential_complex="самол"))

    repo.find_complex_ids_by_name_partial.assert_awaited_once_with("самол")
    assert result.returned == 1
    assert result.items[0].rooms == 2


@pytest.mark.asyncio
async def test_search_returns_empty_when_complex_not_found() -> None:
    repo = AsyncMock()
    repo.find_complex_ids_by_name_exact.return_value = []
    repo.find_complex_ids_by_name_partial.return_value = []
    service = SearchService(repo)

    result = await service.search(ApartmentSearchFilters(residential_complex="несуществующий"))

    assert result == result.model_validate({"total": 0, "returned": 0, "items": []})
    repo.search_apartments.assert_not_called()


@pytest.mark.asyncio
async def test_limit_is_clamped_to_five() -> None:
    filters = ApartmentSearchFilters(limit=99)
    assert filters.limit == 5

    filters_low = ApartmentSearchFilters(limit=0)
    assert filters_low.limit == 5
