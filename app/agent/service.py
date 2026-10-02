"""Agent orchestration: LLM + tools + system prompt."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tool_loop import ToolLoop, ToolLoopResult
from app.apartments.schemas import ApartmentSearchItem
from app.llm.base import LLMProvider
from app.llm.types import ChatMessage, MessageRole
from app.tools.search_apartments import SearchApartmentsTool


@dataclass(frozen=True)
class AgentResult:
    reply: str
    tool_called: str | None = None
    apartments: list[ApartmentSearchItem] = field(default_factory=list)
    total_found: int | None = None
    iterations: int = 0
    model: str | None = None


class AgentService:
    """High-level agent entrypoint without SQL / HTTP DeepSeek details."""

    def __init__(
        self,
        *,
        llm: LLMProvider,
        tools: dict[str, SearchApartmentsTool],
        max_iterations: int = 3,
        system_prompt: str = SYSTEM_PROMPT,
        default_model: str = "deepseek-chat",
    ) -> None:
        self._system_prompt = system_prompt
        self._default_model = default_model
        self._loop = ToolLoop(llm=llm, tools=tools, max_iterations=max_iterations)

    async def handle(self, user_message: str) -> AgentResult:
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=self._system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_message),
        ]
        result: ToolLoopResult = await self._loop.run(messages)
        return AgentResult(
            reply=result.reply,
            tool_called=result.tool_called,
            apartments=result.apartments,
            total_found=result.total_found,
            iterations=result.iterations,
            model=result.model or self._default_model,
        )
