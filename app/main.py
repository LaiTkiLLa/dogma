"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_chat import router as chat_router
from app.api.routes_health import router as health_router
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build FastAPI app (used by tests and uvicorn entrypoint)."""
    resolved = settings or get_settings()
    application = FastAPI(
        title="DOGMA Apartment Chat",
        version="0.1.0",
        description="Chat service for searching DOGMA apartments via DeepSeek tool calling",
    )

    cors_origins = resolved.cors_origin_list
    if cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    application.include_router(health_router)
    application.include_router(chat_router)
    return application


app = create_app()
