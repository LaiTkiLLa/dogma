"""POST /chat endpoint."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.agent.service import AgentResult, AgentService
from app.api.deps import get_agent_service
from app.api.schemas import ChatApartmentItem, ChatMeta, ChatRequest, ChatResponse, ErrorResponse
from app.llm.deepseek import DeepSeekError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def chat(
    payload: ChatRequest,
    agent: Annotated[AgentService, Depends(get_agent_service)],
) -> ChatResponse:
    """Run the apartment-search agent and return reply + structured tool data."""
    try:
        result = await agent.handle(payload.message)
    except DeepSeekError as exc:
        logger.exception("DeepSeek unavailable during /chat")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM provider is temporarily unavailable",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during /chat")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc

    return _to_chat_response(result)


def _to_chat_response(result: AgentResult) -> ChatResponse:
    apartments = [
        ChatApartmentItem(
            source_id=item.source_id,
            residential_complex=item.residential_complex,
            price=item.price,
            area=item.area,
            rooms=item.rooms,
            floor=item.floor,
            floors_total=item.floors_total,
            url=item.url,
        )
        for item in result.apartments
    ]
    return ChatResponse(
        reply=result.reply,
        apartments=apartments,
        meta=ChatMeta(
            tool_called=result.tool_called,
            total_found=result.total_found,
            model=result.model or "deepseek-chat",
        ),
    )
