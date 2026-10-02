"""DOGMA → PostgreSQL sync orchestration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apartments.models import ParserRun
from app.apartments.repository import ApartmentRepository
from app.config import Settings
from app.parser.dogma_client import DogmaClient, DogmaClientError
from app.parser.dogma_parser import DogmaParseError, DogmaParser
from app.parser.normalizer import Normalizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SyncResult:
    status: str
    parser_run_id: UUID | None
    apartments_parsed: int = 0
    apartments_created: int = 0
    apartments_updated: int = 0
    apartments_deactivated: int = 0
    error_message: str | None = None


class SyncService:
    """Run one full DOGMA catalog sync into PostgreSQL."""

    def __init__(
        self,
        *,
        client: DogmaClient,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        parser: DogmaParser | None = None,
        normalizer: Normalizer | None = None,
    ) -> None:
        self._client = client
        self._session_factory = session_factory
        self._settings = settings
        self._parser = parser or DogmaParser()
        self._normalizer = normalizer or Normalizer(
            public_base_url=settings.dogma_public_base_url,
        )

    async def run(self, *, trigger: str = "manual") -> SyncResult:
        sync_started_at = datetime.now(UTC)
        parsed = 0
        created = 0
        updated = 0
        deactivated = 0

        async with self._session_factory() as session:
            repo = ApartmentRepository(session)
            locked = await repo.try_acquire_sync_lock()
            if not locked:
                await session.rollback()
                return SyncResult(
                    status="failed",
                    parser_run_id=None,
                    error_message="another sync is already running",
                )

            run = None
            try:
                run = await repo.create_parser_run(
                    started_at=sync_started_at,
                    trigger=trigger,
                )
                await session.commit()

                complex_ids = await self._sync_projects(repo)
                await session.commit()

                page_limit = self._client.page_limit
                offset = 0
                total_count: int | None = None

                while True:
                    if offset > 0 and self._settings.dogma_request_delay_seconds > 0:
                        await asyncio.sleep(self._settings.dogma_request_delay_seconds)

                    raw_page = await self._client.fetch_objects_page(offset=offset)
                    page = self._parser.parse_filter_response(raw_page)

                    if total_count is None:
                        total_count = page.count
                        if total_count == 0:
                            active = await repo.count_active_apartments()
                            if active > 0:
                                raise DogmaParseError(
                                    "unexpected empty DOGMA catalog while active apartments exist"
                                )

                    if offset < (total_count or 0) and not page.objects:
                        raise DogmaParseError(
                            f"empty objects page at offset={offset}, count={total_count}"
                        )

                    source_ids = [str(obj.id) for obj in page.objects]
                    existing_ids = await repo.list_existing_source_ids(source_ids)

                    for obj in page.objects:
                        apartment = self._normalizer.normalize_apartment(obj)
                        complex_id = complex_ids.get(apartment.source_project_id)
                        if complex_id is None:
                            complex_id = await repo.upsert_residential_complex(
                                self._normalizer.complex_from_apartment(apartment),
                            )
                            complex_ids[apartment.source_project_id] = complex_id

                        await repo.upsert_apartment(
                            apartment,
                            residential_complex_id=complex_id,
                            sync_started_at=sync_started_at,
                        )
                        parsed += 1
                        if apartment.source_id in existing_ids:
                            updated += 1
                        else:
                            created += 1
                            existing_ids.add(apartment.source_id)

                    await session.commit()
                    offset += page_limit
                    if total_count is None or offset >= total_count:
                        break

                deactivated = await repo.deactivate_missing_apartments(
                    sync_started_at=sync_started_at,
                )
                await repo.finish_parser_run(
                    run,
                    status="success",
                    finished_at=datetime.now(UTC),
                    apartments_parsed=parsed,
                    apartments_created=created,
                    apartments_updated=updated,
                    apartments_deactivated=deactivated,
                )
                await session.commit()
                return SyncResult(
                    status="success",
                    parser_run_id=run.id,
                    apartments_parsed=parsed,
                    apartments_created=created,
                    apartments_updated=updated,
                    apartments_deactivated=deactivated,
                )
            except (DogmaClientError, DogmaParseError, Exception) as exc:
                logger.exception("DOGMA sync failed")
                await session.rollback()
                error_message = str(exc)[:2000]
                if run is not None:
                    async with self._session_factory() as fail_session:
                        fail_repo = ApartmentRepository(fail_session)
                        fail_run = await fail_session.get(ParserRun, run.id)
                        if fail_run is not None:
                            await fail_repo.finish_parser_run(
                                fail_run,
                                status="failed",
                                finished_at=datetime.now(UTC),
                                apartments_parsed=parsed,
                                apartments_created=created,
                                apartments_updated=updated,
                                apartments_deactivated=0,
                                error_message=error_message,
                            )
                            await fail_session.commit()
                return SyncResult(
                    status="failed",
                    parser_run_id=run.id if run is not None else None,
                    apartments_parsed=parsed,
                    apartments_created=created,
                    apartments_updated=updated,
                    apartments_deactivated=0,
                    error_message=error_message,
                )
            finally:
                try:
                    await repo.release_sync_lock()
                    await session.commit()
                except Exception:
                    logger.exception("failed to release sync advisory lock")
                    await session.rollback()

    async def _sync_projects(self, repo: ApartmentRepository) -> dict[int, UUID]:
        raw = await self._client.fetch_projects()
        projects = self._parser.parse_projects_response(raw)
        complex_ids: dict[int, UUID] = {}
        for project in projects:
            normalized = self._normalizer.normalize_project(project)
            complex_id = await repo.upsert_residential_complex(normalized)
            complex_ids[normalized.source_project_id] = complex_id
        return complex_ids
