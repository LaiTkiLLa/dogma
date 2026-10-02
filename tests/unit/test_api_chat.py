"""API unit tests with mocked AgentService (no real DeepSeek)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agent.service import AgentResult
from app.api.deps import get_agent_service
from app.apartments.schemas import ApartmentSearchItem
from app.main import app


class FakeAgentService:
    def __init__(self, result: AgentResult) -> None:
        self._result = result
        self.calls: list[str] = []

    async def handle(self, user_message: str) -> AgentResult:
        self.calls.append(user_message)
        return self._result


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def _apartment(**overrides) -> ApartmentSearchItem:
    data = {
        "id": uuid4(),
        "source_id": "216555",
        "residential_complex": "Парк Победы 3",
        "rooms": 2,
        "area": Decimal("50.94"),
        "price": 6_503_484,
        "price_base": 7_000_000,
        "floor": 4,
        "floors_total": 4,
        "status_code": 2,
        "address": "addr",
        "url": "https://dogma.ru/flat/216555",
    }
    data.update(overrides)
    return ApartmentSearchItem(**data)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_success_with_apartments_from_tool(client: TestClient) -> None:
    fake = FakeAgentService(
        AgentResult(
            reply="Нашёл подходящие варианты",
            tool_called="search_apartments",
            apartments=[_apartment()],
            total_found=566,
            iterations=2,
            model="deepseek-chat",
        )
    )

    async def override_agent():
        yield fake

    app.dependency_overrides[get_agent_service] = override_agent

    response = client.post(
        "/chat",
        json={"message": "Найди 2-комнатную квартиру до 10 миллионов"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Нашёл подходящие варианты"
    assert body["meta"] == {
        "tool_called": "search_apartments",
        "total_found": 566,
        "model": "deepseek-chat",
    }
    assert len(body["apartments"]) == 1
    assert body["apartments"][0]["source_id"] == "216555"
    assert body["apartments"][0]["url"] == "https://dogma.ru/flat/216555"
    assert body["apartments"][0]["price"] == 6_503_484
    assert "id" not in body["apartments"][0]
    assert fake.calls == ["Найди 2-комнатную квартиру до 10 миллионов"]


def test_chat_without_tool_call_returns_empty_apartments(client: TestClient) -> None:
    fake = FakeAgentService(
        AgentResult(
            reply="Уточните, пожалуйста, бюджет",
            tool_called=None,
            apartments=[],
            total_found=None,
            model="deepseek-chat",
        )
    )

    async def override_agent():
        yield fake

    app.dependency_overrides[get_agent_service] = override_agent

    response = client.post("/chat", json={"message": "привет"})
    assert response.status_code == 200
    body = response.json()
    assert body["apartments"] == []
    assert body["meta"]["tool_called"] is None
    assert body["meta"]["total_found"] is None


def test_chat_rejects_empty_message(client: TestClient) -> None:
    response = client.post("/chat", json={"message": "   "})
    assert response.status_code == 422


def test_chat_rejects_too_long_message(client: TestClient) -> None:
    response = client.post("/chat", json={"message": "x" * 4001})
    assert response.status_code == 422


def test_chat_rejects_invalid_json(client: TestClient) -> None:
    response = client.post(
        "/chat",
        content="{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_chat_agent_error_does_not_leak_stacktrace(client: TestClient) -> None:
    class BrokenAgent:
        async def handle(self, user_message: str) -> AgentResult:
            raise RuntimeError("secret internals")

    async def override_agent():
        yield BrokenAgent()

    app.dependency_overrides[get_agent_service] = override_agent

    response = client.post("/chat", json={"message": "найди квартиру"})
    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": "Internal server error"}
    assert "secret internals" not in response.text
    assert "Traceback" not in response.text
