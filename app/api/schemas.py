"""HTTP request/response schemas for the chat API."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CHAT_MESSAGE_MAX_LENGTH = 4000


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=CHAT_MESSAGE_MAX_LENGTH)

    @field_validator("message")
    @classmethod
    def _normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        if len(normalized) > CHAT_MESSAGE_MAX_LENGTH:
            raise ValueError(f"message must be at most {CHAT_MESSAGE_MAX_LENGTH} characters")
        return normalized


class ChatApartmentItem(BaseModel):
    """Apartment payload taken from search_apartments tool result."""

    model_config = ConfigDict(from_attributes=True)

    source_id: str
    residential_complex: str
    price: int
    area: Decimal
    rooms: int
    floor: int | None = None
    floors_total: int | None = None
    url: str


class ChatMeta(BaseModel):
    tool_called: str | None = None
    total_found: int | None = None
    model: str = "deepseek-chat"


class ChatResponse(BaseModel):
    reply: str
    apartments: list[ChatApartmentItem] = Field(default_factory=list)
    meta: ChatMeta


class HealthResponse(BaseModel):
    status: str = "ok"


class ErrorResponse(BaseModel):
    detail: str
