from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from signal_app.db import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), index=True)
    sort_name: Mapped[str | None] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(2))
    disambiguation: Mapped[str | None] = mapped_column(String(500))
    provider_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    external_ids: Mapped[list[ArtistExternalId]] = relationship(
        back_populates="artist", cascade="all, delete-orphan", lazy="selectin"
    )
    releases: Mapped[list[Release]] = relationship(
        secondary="release_artists", back_populates="artists", lazy="selectin"
    )
    snapshots: Mapped[list[ArtistMetricSnapshot]] = relationship(
        back_populates="artist", cascade="all, delete-orphan"
    )


class ArtistExternalId(Base):
    __tablename__ = "artist_external_ids"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_artist_provider_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(255))
    artist: Mapped[Artist] = relationship(back_populates="external_ids")


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500))
    release_date: Mapped[date | None] = mapped_column(Date)
    release_type: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str | None] = mapped_column(String(80))
    provider_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    external_ids: Mapped[list[ReleaseExternalId]] = relationship(
        back_populates="release", cascade="all, delete-orphan", lazy="selectin"
    )
    artists: Mapped[list[Artist]] = relationship(
        secondary="release_artists", back_populates="releases", lazy="selectin"
    )


class ReleaseExternalId(Base):
    __tablename__ = "release_external_ids"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_release_provider_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    release_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("releases.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(255))
    release: Mapped[Release] = relationship(back_populates="external_ids")


class ReleaseArtist(Base):
    __tablename__ = "release_artists"

    release_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("releases.id", ondelete="CASCADE"), primary_key=True
    )
    artist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)


class ArtistMetricSnapshot(Base):
    __tablename__ = "artist_metric_snapshots"
    __table_args__ = (
        CheckConstraint(
            "listen_count IS NULL OR listen_count >= 0", name="ck_snapshot_listen_count_nonnegative"
        ),
        CheckConstraint(
            "listener_count IS NULL OR listener_count >= 0",
            name="ck_snapshot_listener_count_nonnegative",
        ),
        UniqueConstraint(
            "artist_id", "snapshot_date", "source", name="uq_artist_snapshot_date_source"
        ),
        Index("ix_snapshot_artist_date", "artist_id", "snapshot_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(50))
    listen_count: Mapped[int | None] = mapped_column(BigInteger)
    listener_count: Mapped[int | None] = mapped_column(BigInteger)
    popularity: Mapped[float | None] = mapped_column(Float)
    release_activity: Mapped[int | None] = mapped_column(Integer)
    provider_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    artist: Mapped[Artist] = relationship(back_populates="snapshots")
