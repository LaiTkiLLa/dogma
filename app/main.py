"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes_chat import router as chat_router
from app.api.routes_health import router as health_router

app = FastAPI(
    title="DOGMA Apartment Chat",
    version="0.1.0",
    description="Chat API for searching DOGMA apartments via DeepSeek tool calling",
)

app.include_router(health_router)
app.include_router(chat_router)
