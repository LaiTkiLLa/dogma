"""DeepSeek Chat Completions provider via httpx."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.llm.types import ChatMessage, LLMResponse, MessageRole, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)


class DeepSeekError(Exception):
    """Raised when DeepSeek API request fails."""


class DeepSeekProvider:
    """HTTP adapter for DeepSeek OpenAI-compatible chat completions."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: float = 30,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is not configured")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> DeepSeekProvider:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
            self._owns_client = True
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        client = self._require_client()
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [self._to_api_message(message) for message in messages],
        }
        if tools:
            payload["tools"] = [self._to_api_tool(tool) for tool in tools]
            payload["tool_choice"] = "auto"

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.exception("DeepSeek request failed")
            raise DeepSeekError(f"DeepSeek request failed: {exc}") from exc
        except ValueError as exc:
            raise DeepSeekError(f"DeepSeek returned invalid JSON: {exc}") from exc

        return self._parse_response(data)

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("DeepSeekProvider is not started; use 'async with' or pass a client")
        return self._client

    @staticmethod
    def _to_api_tool(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    @staticmethod
    def _to_api_message(message: ChatMessage) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": message.role.value}
        if message.content is not None:
            payload["content"] = message.content
        elif message.role != MessageRole.ASSISTANT or not message.tool_calls:
            payload["content"] = ""

        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
                for call in message.tool_calls
            ]
        if message.tool_call_id is not None:
            payload["tool_call_id"] = message.tool_call_id
        if message.name is not None:
            payload["name"] = message.name
        return payload

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> LLMResponse:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise DeepSeekError("DeepSeek response has no choices")
        message = choices[0].get("message") or {}
        raw_tool_calls = message.get("tool_calls") or []
        tool_calls: list[ToolCall] = []
        for item in raw_tool_calls:
            function = item.get("function") or {}
            tool_calls.append(
                ToolCall(
                    id=str(item.get("id") or ""),
                    name=str(function.get("name") or ""),
                    arguments=str(function.get("arguments") or "{}"),
                )
            )
        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            model=data.get("model"),
            finish_reason=choices[0].get("finish_reason"),
        )
