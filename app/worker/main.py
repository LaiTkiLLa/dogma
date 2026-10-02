"""Worker entrypoint: periodic DOGMA → PostgreSQL sync."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.parser.dogma_client import DogmaClient
from app.parser.sync_service import SyncService
from app.worker.runner import SyncWorker

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        if not stop_event.is_set():
            logger.info("Shutdown signal received")
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Fallback for platforms without add_signal_handler.
            signal.signal(sig, lambda *_args: _request_stop())


async def _async_main() -> int:
    settings = get_settings()
    _configure_logging(settings.app_log_level)

    if not settings.worker_enabled:
        logger.info("Worker disabled via WORKER_ENABLED=false")
        return 0

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    engine = get_engine()
    session_factory = get_session_factory()

    async with DogmaClient(
        base_url=settings.dogma_base_url,
        timeout_seconds=settings.dogma_request_timeout,
        page_limit=settings.dogma_page_limit,
    ) as client:
        sync_service = SyncService(
            client=client,
            session_factory=session_factory,
            settings=settings,
        )

        async def run_sync():
            return await sync_service.run(trigger="schedule")

        worker = SyncWorker(
            run_sync=run_sync,
            interval_seconds=settings.dogma_sync_interval_seconds,
            retry_delay_seconds=settings.dogma_retry_delay_seconds,
            stop_event=stop_event,
        )
        await worker.run()

    await engine.dispose()
    logger.info("DB engine disposed")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
