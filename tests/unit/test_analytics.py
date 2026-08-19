from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session

from signal_app.analytics import GrowthStatus, calculate_growth
from signal_app.models import Artist, ArtistMetricSnapshot


def add_artist(session: Session) -> Artist:
    artist = Artist(name="Test Artist")
    session.add(artist)
    session.flush()
    return artist


def test_calculate_growth_uses_persisted_snapshots(session: Session) -> None:
    artist = add_artist(session)
    session.add_all(
        [
            ArtistMetricSnapshot(
                artist_id=artist.id,
                snapshot_date=date(2026, 1, 1),
                source="test",
                listener_count=1_000,
            ),
            ArtistMetricSnapshot(
                artist_id=artist.id,
                snapshot_date=date(2026, 1, 31),
                source="test",
                listener_count=1_250,
            ),
        ]
    )
    session.commit()

    result = calculate_growth(
        session,
        artist_id=artist.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        source="test",
    )

    assert result.status is GrowthStatus.OK
    assert result.absolute_change == 250
    assert result.percentage_change == 25.0


def test_calculate_growth_reports_missing_data(session: Session) -> None:
    artist = add_artist(session)

    result = calculate_growth(
        session,
        artist_id=artist.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        source="test",
    )

    assert result.status is GrowthStatus.INSUFFICIENT_DATA
    assert result.percentage_change is None


def test_calculate_growth_handles_zero_denominator(session: Session) -> None:
    artist = add_artist(session)
    session.add_all(
        [
            ArtistMetricSnapshot(
                artist_id=artist.id,
                snapshot_date=date(2026, 1, 1),
                source="test",
                listener_count=0,
            ),
            ArtistMetricSnapshot(
                artist_id=artist.id,
                snapshot_date=date(2026, 1, 31),
                source="test",
                listener_count=20,
            ),
        ]
    )
    session.commit()

    result = calculate_growth(
        session,
        artist_id=artist.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        source="test",
    )

    assert result.status is GrowthStatus.UNDEFINED_PERCENTAGE
    assert result.absolute_change == 20
    assert result.percentage_change is None


def test_calculate_growth_rejects_invalid_range(session: Session) -> None:
    import pytest

    with pytest.raises(ValueError, match="end_date must be after start_date"):
        calculate_growth(
            session,
            artist_id=uuid.uuid4(),
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
        )
