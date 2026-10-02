"""LLM provider protocol."""

from __future__ import annotations

from typing import Protocol

from app.llm.types import ChatMessage, LLMResponse, ToolDefinition


class LLMProvider(Protocol):
    """Provider-agnostic chat interface used by the agent."""

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        """Send messages (and optional tools) and return the assistant response."""
