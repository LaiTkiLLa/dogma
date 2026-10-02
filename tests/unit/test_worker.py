"""Unit tests for periodic SyncWorker loop."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.parser.sync_service import SyncResult
from app.worker.runner import SyncWorker


def _success(**overrides) -> SyncResult:
    data = {
        "status": "success",
        "parser_run_id": uuid4(),
        "apartments_parsed": 10,
        "apartments_created": 4,
        "apartments_updated": 6,
        "apartments_deactivated": 1,
    }
    data.update(overrides)
    return SyncResult(**data)


@pytest.mark.asyncio
async def test_success_uses_full_sync_interval(caplog: pytest.LogCaptureFixture) -> None:
    stop_event = asyncio.Event()
    sleeps: list[float] = []

    async def run_sync() -> SyncResult:
        return _success()

    worker = SyncWorker(
        run_sync=run_sync,
        interval_seconds=3600,
        retry_delay_seconds=10,
        stop_event=stop_event,
    )

    async def tracking_sleep(timeout_seconds: float) -> None:
        sleeps.append(timeout_seconds)
        stop_event.set()

    worker._sleep_until_next_or_stop = tracking_sleep  # type: ignore[method-assign]

    with caplog.at_level("INFO"):
        await worker.run()

    assert sleeps == [3600]
    assert "Sync interval: 3600 seconds" in caplog.text
    assert "Retry delay: 10 seconds" in caplog.text
    assert "DOGMA sync completed: parsed=10, created=4, updated=6, deactivated=1" in caplog.text


@pytest.mark.asyncio
async def test_failed_sync_uses_retry_delay(caplog: pytest.LogCaptureFixture) -> None:
    calls = 0
    stop_event = asyncio.Event()
    sleeps: list[float] = []

    async def run_sync() -> SyncResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return SyncResult(
                status="failed",
                parser_run_id=uuid4(),
                error_message="429 Too Many Requests",
            )
        stop_event.set()
        return _success()

    worker = SyncWorker(
        run_sync=run_sync,
        interval_seconds=3600,
        retry_delay_seconds=10,
        stop_event=stop_event,
    )

    async def tracking_sleep(timeout_seconds: float) -> None:
        sleeps.append(timeout_seconds)

    worker._sleep_until_next_or_stop = tracking_sleep  # type: ignore[method-assign]

    with caplog.at_level("ERROR"):
        await worker.run()

    assert calls == 2
    assert sleeps[0] == 10
    assert "DOGMA sync failed: 429 Too Many Requests" in caplog.text


@pytest.mark.asyncio
async def test_sync_error_does_not_crash_worker(caplog: pytest.LogCaptureFixture) -> None:
    calls = 0
    stop_event = asyncio.Event()
    sleeps: list[float] = []

    async def run_sync() -> SyncResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary network failure")
        stop_event.set()
        return _success(
            apartments_parsed=1,
            apartments_created=1,
            apartments_updated=0,
            apartments_deactivated=0,
        )

    worker = SyncWorker(
        run_sync=run_sync,
        interval_seconds=3600,
        retry_delay_seconds=10,
        stop_event=stop_event,
    )

    async def tracking_sleep(timeout_seconds: float) -> None:
        sleeps.append(timeout_seconds)

    worker._sleep_until_next_or_stop = tracking_sleep  # type: ignore[method-assign]

    with caplog.at_level("ERROR"):
        await worker.run()

    assert calls == 2
    assert sleeps[0] == 10
    assert "DOGMA sync failed: temporary network failure" in caplog.text


@pytest.mark.asyncio
async def test_stop_during_sleep_exits_without_extra_sync() -> None:
    calls = 0
    stop_event = asyncio.Event()

    async def run_sync() -> SyncResult:
        nonlocal calls
        calls += 1
        asyncio.get_running_loop().call_later(0.05, stop_event.set)
        return _success()

    worker = SyncWorker(
        run_sync=run_sync,
        interval_seconds=5,
        retry_delay_seconds=10,
        stop_event=stop_event,
    )
    await worker.run()

    assert calls == 1
