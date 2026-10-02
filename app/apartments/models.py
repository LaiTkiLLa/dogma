"""ORM models for residential complexes, apartments, and parser runs."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ResidentialComplex(Base):
    """DOGMA residential complex (project)."""

    __tablename__ = "residential_complexes"
    __table_args__ = (
        UniqueConstraint("source_project_id", name="uq_residential_complexes_source_project_id"),
        Index("ix_residential_complexes_name_normalized", "name_normalized"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source_project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    city_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    apartments: Mapped[list["Apartment"]] = relationship(
        back_populates="residential_complex",
    )


class Apartment(Base):
    """Apartment listing synced from DOGMA."""

    __tablename__ = "apartments"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_apartments_source_id"),
        Index(
            "ix_apartments_active_price",
            "is_active",
            "price",
            postgresql_where=text("is_active"),
        ),
        Index(
            "ix_apartments_active_area",
            "is_active",
            "area",
            postgresql_where=text("is_active"),
        ),
        Index(
            "ix_apartments_active_rooms",
            "is_active",
            "rooms",
            postgresql_where=text("is_active"),
        ),
        Index(
            "ix_apartments_active_residential_complex_id",
            "is_active",
            "residential_complex_id",
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    residential_complex_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("residential_complexes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_base: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    area: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    rooms: Mapped[int] = mapped_column(Integer, nullable=False)
    property_type: Mapped[str] = mapped_column(Text, nullable=False)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floors_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    flat_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    residential_complex: Mapped[ResidentialComplex] = relationship(
        back_populates="apartments",
    )


class ParserRun(Base):
    """Single DOGMA sync run metadata."""

    __tablename__ = "parser_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'failed')",
            name="ck_parser_runs_status",
        ),
        CheckConstraint(
            "trigger IN ('schedule', 'manual')",
            name="ck_parser_runs_trigger",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    apartments_parsed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    apartments_created: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    apartments_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    apartments_deactivated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
