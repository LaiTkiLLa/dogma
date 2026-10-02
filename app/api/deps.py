"""FastAPI dependencies — wire AgentService without a DI framework."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import AgentService
from app.apartments.repository import ApartmentRepository
from app.apartments.search_service import SearchService
from app.config import Settings, get_settings
from app.db.session import get_session
from app.llm.deepseek import DeepSeekProvider
from app.tools.registry import build_tool_registry


async def get_agent_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[AgentService]:
    """Build a request-scoped AgentService with LLM + tools + DB session."""
    async with DeepSeekProvider(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        timeout_seconds=settings.deepseek_timeout_seconds,
    ) as llm:
        tools = build_tool_registry(SearchService(ApartmentRepository(session)))
        yield AgentService(
            llm=llm,
            tools=tools,
            max_iterations=settings.chat_max_tool_iterations,
            default_model=settings.deepseek_model,
        )
