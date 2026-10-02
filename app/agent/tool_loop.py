"""Tool-calling loop over LLMProvider + ToolRegistry."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.apartments.schemas import ApartmentSearchItem, ApartmentSearchResult
from app.llm.base import LLMProvider
from app.llm.types import ChatMessage, LLMResponse, MessageRole, ToolCall
from app.tools.registry import get_tool, list_tool_definitions
from app.tools.search_apartments import SearchApartmentsTool

logger = logging.getLogger(__name__)

SAFE_MAX_ITERATIONS_REPLY = (
    "Не удалось завершить поиск за отведённое число шагов. "
    "Ниже — то, что уже удалось найти через search_apartments; "
    "уточните запрос, пожалуйста."
)


@dataclass
class ToolLoopResult:
    reply: str
    messages: list[ChatMessage]
    tool_called: str | None = None
    apartments: list[ApartmentSearchItem] = field(default_factory=list)
    total_found: int | None = None
    iterations: int = 0
    stopped_by_max_iterations: bool = False
    model: str | None = None


class ToolLoop:
    """Run LLM ↔ tools until a final text answer or iteration limit."""

    def __init__(
        self,
        *,
        llm: LLMProvider,
        tools: dict[str, SearchApartmentsTool],
        max_iterations: int = 3,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self._llm = llm
        self._tools = tools
        self._max_iterations = max_iterations

    async def run(self, messages: list[ChatMessage]) -> ToolLoopResult:
        working = list(messages)
        tool_defs = list_tool_definitions(self._tools)
        seen_calls: set[tuple[str, str]] = set()
        tool_called: str | None = None
        apartments: list[ApartmentSearchItem] = []
        total_found: int | None = None
        last_response: LLMResponse | None = None

        for iteration in range(1, self._max_iterations + 1):
            response = await self._llm.chat(working, tools=tool_defs)
            last_response = response

            if not response.has_tool_calls:
                return ToolLoopResult(
                    reply=(response.content or "").strip(),
                    messages=working,
                    tool_called=tool_called,
                    apartments=apartments,
                    total_found=total_found,
                    iterations=iteration,
                    model=response.model,
                )

            working.append(
                ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            for call in response.tool_calls:
                dedup_key = (call.name, call.arguments)
                if dedup_key in seen_calls:
                    content = json.dumps(
                        {"error": "duplicate_tool_call", "message": "Повторный вызов пропущен"},
                        ensure_ascii=False,
                    )
                else:
                    seen_calls.add(dedup_key)
                    content, maybe_result = await self._execute_tool_call(call)
                    if maybe_result is not None:
                        tool_called = call.name
                        apartments = list(maybe_result.items)
                        total_found = maybe_result.total

                working.append(
                    ChatMessage(
                        role=MessageRole.TOOL,
                        content=content,
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )

        # Max iterations reached while model still requests tools.
        summary = self._build_limit_reply(apartments, total_found)
        return ToolLoopResult(
            reply=summary,
            messages=working,
            tool_called=tool_called,
            apartments=apartments,
            total_found=total_found,
            iterations=self._max_iterations,
            stopped_by_max_iterations=True,
            model=last_response.model if last_response else None,
        )

    async def _execute_tool_call(
        self,
        call: ToolCall,
    ) -> tuple[str, ApartmentSearchResult | None]:
        if call.name not in self._tools:
            payload = {
                "error": "unknown_tool",
                "message": f"Инструмент '{call.name}' недоступен",
            }
            return json.dumps(payload, ensure_ascii=False), None

        try:
            arguments = json.loads(call.arguments or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            payload = {
                "error": "invalid_arguments",
                "message": f"Некорректный JSON аргументов: {exc}",
            }
            return json.dumps(payload, ensure_ascii=False), None

        tool = get_tool(self._tools, call.name)
        try:
            result = await tool.execute(arguments)
        except ValidationError as exc:
            payload = {
                "error": "invalid_arguments",
                "message": "Аргументы не прошли валидацию",
                "details": exc.errors(),
            }
            return json.dumps(payload, ensure_ascii=False), None
        except Exception as exc:
            logger.exception("tool %s failed", call.name)
            payload = {
                "error": "tool_execution_failed",
                "message": str(exc),
            }
            return json.dumps(payload, ensure_ascii=False), None

        return result.model_dump_json(), result

    @staticmethod
    def _build_limit_reply(
        apartments: list[ApartmentSearchItem],
        total_found: int | None,
    ) -> str:
        if not apartments:
            return SAFE_MAX_ITERATIONS_REPLY

        lines = [SAFE_MAX_ITERATIONS_REPLY]
        if total_found is not None:
            lines.append(f"Найдено всего: {total_found}.")
        for item in apartments:
            lines.append(
                f"- {item.residential_complex}: {item.rooms} комн., "
                f"{item.area} м², {item.price} ₽ — {item.url}"
            )
        return "\n".join(lines)
