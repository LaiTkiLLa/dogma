"""Apartment persistence: upserts and sync-related SQL only here."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.apartments.models import Apartment, ParserRun, ResidentialComplex
from app.parser.normalizer import NormalizedApartment, NormalizedResidentialComplex

# Session-level advisory lock key for DOGMA sync jobs (fits in int4).
SYNC_ADVISORY_LOCK_KEY = 814_203_551


class ApartmentRepository:
    """SQLAlchemy repository for apartments, complexes, and parser runs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_acquire_sync_lock(self) -> bool:
        result = await self._session.execute(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": SYNC_ADVISORY_LOCK_KEY},
        )
        return bool(result.scalar_one())

    async def release_sync_lock(self) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_unlock(:key)"),
            {"key": SYNC_ADVISORY_LOCK_KEY},
        )

    async def create_parser_run(
        self,
        *,
        started_at: datetime,
        trigger: str,
    ) -> ParserRun:
        run = ParserRun(
            started_at=started_at,
            status="running",
            trigger=trigger,
            apartments_parsed=0,
            apartments_created=0,
            apartments_updated=0,
            apartments_deactivated=0,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def finish_parser_run(
        self,
        run: ParserRun,
        *,
        status: str,
        finished_at: datetime,
        apartments_parsed: int,
        apartments_created: int,
        apartments_updated: int,
        apartments_deactivated: int,
        error_message: str | None = None,
    ) -> ParserRun:
        run.status = status
        run.finished_at = finished_at
        run.apartments_parsed = apartments_parsed
        run.apartments_created = apartments_created
        run.apartments_updated = apartments_updated
        run.apartments_deactivated = apartments_deactivated
        run.error_message = error_message
        await self._session.flush()
        return run

    async def count_active_apartments(self) -> int:
        result = await self._session.scalar(
            select(func.count())
            .select_from(Apartment)
            .where(Apartment.is_active.is_(True))
        )
        return int(result or 0)

    async def upsert_residential_complex(
        self,
        data: NormalizedResidentialComplex,
    ) -> UUID:
        stmt = (
            insert(ResidentialComplex)
            .values(
                source_project_id=data.source_project_id,
                name=data.name,
                name_normalized=data.name_normalized,
                city_name=data.city_name,
            )
            .on_conflict_do_update(
                constraint="uq_residential_complexes_source_project_id",
                set_={
                    "name": data.name,
                    "name_normalized": data.name_normalized,
                    "city_name": data.city_name,
                    "updated_at": func.now(),
                },
            )
            .returning(ResidentialComplex.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def upsert_apartment(
        self,
        data: NormalizedApartment,
        *,
        residential_complex_id: UUID,
        sync_started_at: datetime,
    ) -> None:
        """Upsert apartment by source_id; sets is_active and last_seen_at."""
        stmt = (
            insert(Apartment)
            .values(
                source_id=data.source_id,
                residential_complex_id=residential_complex_id,
                price=data.price,
                price_base=data.price_base,
                area=data.area,
                rooms=data.rooms,
                property_type=data.property_type,
                floor=data.floor,
                floors_total=data.floors_total,
                status_code=data.status_code,
                url=data.url,
                address=data.address,
                flat_number=data.flat_number,
                raw_payload=data.raw_payload,
                is_active=True,
                last_seen_at=sync_started_at,
            )
            .on_conflict_do_update(
                constraint="uq_apartments_source_id",
                set_={
                    "residential_complex_id": residential_complex_id,
                    "price": data.price,
                    "price_base": data.price_base,
                    "area": data.area,
                    "rooms": data.rooms,
                    "property_type": data.property_type,
                    "floor": data.floor,
                    "floors_total": data.floors_total,
                    "status_code": data.status_code,
                    "url": data.url,
                    "address": data.address,
                    "flat_number": data.flat_number,
                    "raw_payload": data.raw_payload,
                    "is_active": True,
                    "last_seen_at": sync_started_at,
                    "updated_at": func.now(),
                },
            )
        )
        await self._session.execute(stmt)

    async def list_existing_source_ids(self, source_ids: list[str]) -> set[str]:
        if not source_ids:
            return set()
        result = await self._session.scalars(
            select(Apartment.source_id).where(Apartment.source_id.in_(source_ids))
        )
        return set(result.all())

    async def find_complex_ids_by_name_exact(self, name_normalized: str) -> list[UUID]:
        result = await self._session.scalars(
            select(ResidentialComplex.id).where(
                ResidentialComplex.name_normalized == name_normalized
            )
        )
        return list(result.all())

    async def find_complex_ids_by_name_partial(self, name_normalized: str) -> list[UUID]:
        pattern = f"%{name_normalized}%"
        result = await self._session.scalars(
            select(ResidentialComplex.id).where(
                ResidentialComplex.name_normalized.ilike(pattern)
            )
        )
        return list(result.all())

    async def search_apartments(
        self,
        *,
        min_price: int | None = None,
        max_price: int | None = None,
        min_area: float | None = None,
        max_area: float | None = None,
        rooms: int | None = None,
        residential_complex_ids: list[UUID] | None = None,
        limit: int = 5,
    ) -> tuple[int, list[tuple[Apartment, str]]]:
        """Return (total_count, [(apartment, complex_name), ...]) for active rows."""
        conditions = [Apartment.is_active.is_(True)]

        if min_price is not None:
            conditions.append(Apartment.price >= min_price)
        if max_price is not None:
            conditions.append(Apartment.price <= max_price)
        if min_area is not None:
            conditions.append(Apartment.area >= min_area)
        if max_area is not None:
            conditions.append(Apartment.area <= max_area)
        if rooms is not None:
            conditions.append(Apartment.rooms == rooms)
        if residential_complex_ids is not None:
            if not residential_complex_ids:
                return 0, []
            conditions.append(Apartment.residential_complex_id.in_(residential_complex_ids))

        base = (
            select(Apartment, ResidentialComplex.name)
            .join(
                ResidentialComplex,
                Apartment.residential_complex_id == ResidentialComplex.id,
            )
            .where(*conditions)
        )

        total = int(
            await self._session.scalar(
                select(func.count()).select_from(base.order_by(None).subquery())
            )
            or 0
        )

        rows = (
            await self._session.execute(
                base.order_by(Apartment.price.asc(), Apartment.area.asc()).limit(limit)
            )
        ).all()

        return total, [(apartment, complex_name) for apartment, complex_name in rows]

    async def deactivate_missing_apartments(self, *, sync_started_at: datetime) -> int:
        """Deactivate apartments not seen in the current successful sync."""
        result = await self._session.execute(
            update(Apartment)
            .where(
                Apartment.is_active.is_(True),
                Apartment.last_seen_at < sync_started_at,
                Apartment.property_type == "apartment",
            )
            .values(is_active=False, updated_at=func.now())
        )
        return int(result.rowcount or 0)
