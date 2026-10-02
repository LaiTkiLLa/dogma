"""Periodic sync loop used by the worker process."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.parser.sync_service import SyncResult

logger = logging.getLogger(__name__)

SyncCallable = Callable[[], Awaitable[SyncResult]]


class SyncWorker:
    """Run SyncService on an interval until stop_event is set."""

    def __init__(
        self,
        *,
        run_sync: SyncCallable,
        interval_seconds: int,
        retry_delay_seconds: int,
        stop_event: asyncio.Event,
    ) -> None:
        if interval_seconds < 1:
            raise ValueError("interval_seconds must be >= 1")
        if retry_delay_seconds < 1:
            raise ValueError("retry_delay_seconds must be >= 1")
        self._run_sync = run_sync
        self._interval_seconds = interval_seconds
        self._retry_delay_seconds = retry_delay_seconds
        self._stop_event = stop_event

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    @property
    def retry_delay_seconds(self) -> int:
        return self._retry_delay_seconds

    async def run(self) -> None:
        logger.info("Worker started")
        logger.info("Sync interval: %s seconds", self._interval_seconds)
        logger.info("Retry delay: %s seconds", self._retry_delay_seconds)

        while not self._stop_event.is_set():
            succeeded = await self._run_once()
            if self._stop_event.is_set():
                break
            delay = (
                self._interval_seconds if succeeded else self._retry_delay_seconds
            )
            await self._sleep_until_next_or_stop(delay)

        logger.info("Worker stopped")

    async def _run_once(self) -> bool:
        logger.info("DOGMA sync started")
        try:
            result = await self._run_sync()
        except Exception as exc:
            logger.exception("DOGMA sync failed: %s", exc)
            return False

        if result.status == "success":
            logger.info(
                "DOGMA sync completed: parsed=%s, created=%s, updated=%s, deactivated=%s",
                result.apartments_parsed,
                result.apartments_created,
                result.apartments_updated,
                result.apartments_deactivated,
            )
            return True

        logger.error(
            "DOGMA sync failed: %s",
            result.error_message or result.status,
        )
        return False

    async def _sleep_until_next_or_stop(self, timeout_seconds: float) -> None:
        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            return
