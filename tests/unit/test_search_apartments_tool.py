"""Unit tests for search_apartments tool and registry."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.apartments.schemas import ApartmentSearchItem, ApartmentSearchResult
from app.tools.registry import build_tool_registry, get_tool
from app.tools.schemas import SearchApartmentsArgs
from app.tools.search_apartments import SearchApartmentsTool


@pytest.mark.asyncio
async def test_tool_delegates_to_search_service() -> None:
    search_service = AsyncMock()
    search_service.search.return_value = ApartmentSearchResult(
        total=2,
        returned=1,
        items=[
            ApartmentSearchItem(
                id=uuid4(),
                source_id="42",
                residential_complex="Рекорд 2",
                rooms=2,
                area=Decimal("54.10"),
                price=8_000_000,
                price_base=9_000_000,
                floor=5,
                floors_total=17,
                status_code=2,
                address="addr",
                url="https://dogma.ru/flat/42",
            )
        ],
    )
    tool = SearchApartmentsTool(search_service)

    result = await tool.execute({"max_price": 10_000_000, "rooms": 2, "limit": 3})

    assert result.returned == 1
    assert result.items[0].source_id == "42"
    search_service.search.assert_awaited_once()
    filters = search_service.search.await_args.args[0]
    assert filters.max_price == 10_000_000
    assert filters.rooms == 2
    assert filters.limit == 3


def test_tool_args_schema_matches_search_filters() -> None:
    args = SearchApartmentsArgs(
        min_price=1,
        max_price=10_000_000,
        min_area=50,
        rooms=0,
        residential_complex="МКР Самолёт",
        limit=5,
    )
    assert args.rooms == 0
    assert args.limit == 5


def test_registry_registers_search_apartments() -> None:
    search_service = AsyncMock()
    registry = build_tool_registry(search_service)
    tool = get_tool(registry, "search_apartments")
    assert isinstance(tool, SearchApartmentsTool)
    assert set(registry) == {"search_apartments"}
