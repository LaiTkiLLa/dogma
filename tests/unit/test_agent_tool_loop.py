"""Unit tests for agent tool-calling loop with a mock LLM."""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agent.service import AgentService
from app.agent.tool_loop import ToolLoop
from app.apartments.schemas import ApartmentSearchItem, ApartmentSearchResult
from app.llm.types import ChatMessage, LLMResponse, MessageRole, ToolCall
from app.tools.registry import build_tool_registry
from app.tools.search_apartments import SearchApartmentsTool


def _search_result() -> ApartmentSearchResult:
    return ApartmentSearchResult(
        total=1,
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


def _tool_call(*, name: str = "search_apartments", arguments: str, call_id: str = "call_1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


@pytest.fixture
def search_tool() -> SearchApartmentsTool:
    search_service = AsyncMock()
    search_service.search.return_value = _search_result()
    return SearchApartmentsTool(search_service)


@pytest.fixture
def registry(search_tool: SearchApartmentsTool) -> dict[str, SearchApartmentsTool]:
    return {search_tool.name: search_tool}


@pytest.mark.asyncio
async def test_direct_text_response_does_not_call_tool(registry: dict[str, SearchApartmentsTool]) -> None:
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(content="Просто текст без поиска", tool_calls=[])
    loop = ToolLoop(llm=llm, tools=registry, max_iterations=3)

    result = await loop.run([ChatMessage(role=MessageRole.USER, content="привет")])

    assert result.reply == "Просто текст без поиска"
    assert result.tool_called is None
    assert result.apartments == []
    registry["search_apartments"]._search_service.search.assert_not_called()
    assert llm.chat.await_count == 1


@pytest.mark.asyncio
async def test_tool_call_invokes_search_apartments(registry: dict[str, SearchApartmentsTool]) -> None:
    llm = AsyncMock()
    llm.chat.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[_tool_call(arguments='{"max_price": 10000000, "rooms": 2}')],
        ),
        LLMResponse(content="Нашёл варианты", tool_calls=[]),
    ]
    loop = ToolLoop(llm=llm, tools=registry, max_iterations=3)

    result = await loop.run([ChatMessage(role=MessageRole.USER, content="2к до 10 млн")])

    assert result.tool_called == "search_apartments"
    assert result.apartments[0].source_id == "42"
    assert result.reply == "Нашёл варианты"
    registry["search_apartments"]._search_service.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_result_is_passed_back_to_model(registry: dict[str, SearchApartmentsTool]) -> None:
    llm = AsyncMock()
    llm.chat.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[_tool_call(arguments='{"min_area": 50}')],
        ),
        LLMResponse(content="Готово", tool_calls=[]),
    ]
    loop = ToolLoop(llm=llm, tools=registry, max_iterations=3)

    await loop.run([ChatMessage(role=MessageRole.USER, content="от 50 м2")])

    second_messages = llm.chat.await_args_list[1].args[0]
    tool_messages = [m for m in second_messages if m.role == MessageRole.TOOL]
    assert len(tool_messages) == 1
    payload = json.loads(tool_messages[0].content)
    assert payload["returned"] == 1
    assert payload["items"][0]["url"] == "https://dogma.ru/flat/42"


@pytest.mark.asyncio
async def test_final_answer_after_tool_call(registry: dict[str, SearchApartmentsTool]) -> None:
    llm = AsyncMock()
    llm.chat.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[_tool_call(arguments='{"residential_complex": "Самолёт"}')],
        ),
        LLMResponse(content="В ЖК Самолёт есть варианты", tool_calls=[]),
    ]
    agent = AgentService(llm=llm, tools=registry, max_iterations=3)

    result = await agent.handle("Найди квартиру в Самолёте")

    assert result.reply == "В ЖК Самолёт есть варианты"
    assert result.iterations == 2
    assert result.total_found == 1


@pytest.mark.asyncio
async def test_unknown_tool_is_not_executed(registry: dict[str, SearchApartmentsTool]) -> None:
    llm = AsyncMock()
    llm.chat.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[_tool_call(name="delete_database", arguments="{}")],
        ),
        LLMResponse(content="Не могу выполнить неизвестный инструмент", tool_calls=[]),
    ]
    loop = ToolLoop(llm=llm, tools=registry, max_iterations=3)

    result = await loop.run([ChatMessage(role=MessageRole.USER, content="хак")])

    registry["search_apartments"]._search_service.search.assert_not_called()
    tool_messages = [m for m in result.messages if m.role == MessageRole.TOOL]
    assert json.loads(tool_messages[0].content)["error"] == "unknown_tool"


@pytest.mark.asyncio
async def test_invalid_arguments_are_reported(registry: dict[str, SearchApartmentsTool]) -> None:
    llm = AsyncMock()
    llm.chat.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[_tool_call(arguments='{"max_price": "дорого"}')],
        ),
        LLMResponse(content="Уточните бюджет числом", tool_calls=[]),
    ]
    loop = ToolLoop(llm=llm, tools=registry, max_iterations=3)

    result = await loop.run([ChatMessage(role=MessageRole.USER, content="дешёвую")])

    registry["search_apartments"]._search_service.search.assert_not_called()
    tool_messages = [m for m in result.messages if m.role == MessageRole.TOOL]
    assert json.loads(tool_messages[0].content)["error"] == "invalid_arguments"


@pytest.mark.asyncio
async def test_max_iterations_stops_infinite_loop(registry: dict[str, SearchApartmentsTool]) -> None:
    llm = AsyncMock()
    llm.chat.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[_tool_call(arguments='{"rooms": 1}', call_id=f"c{i}")],
        )
        for i in range(5)
    ]
    # Different args each time so dedup does not short-circuit iterations.
    llm.chat.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[
                _tool_call(
                    arguments=json.dumps({"rooms": i}),
                    call_id=f"c{i}",
                )
            ],
        )
        for i in range(1, 6)
    ]
    loop = ToolLoop(llm=llm, tools=registry, max_iterations=3)

    result = await loop.run([ChatMessage(role=MessageRole.USER, content="ищи")])

    assert result.stopped_by_max_iterations is True
    assert result.iterations == 3
    assert llm.chat.await_count == 3
    assert "Не удалось завершить поиск" in result.reply


@pytest.mark.asyncio
async def test_build_registry_exposes_russian_tool_description() -> None:
    search_service = AsyncMock()
    registry = build_tool_registry(search_service)
    definition = registry["search_apartments"].definition()
    assert definition.name == "search_apartments"
    assert "Ищет активные квартиры DOGMA" in definition.description
    assert definition.parameters["type"] == "object"
    assert "max_price" in definition.parameters["properties"]
