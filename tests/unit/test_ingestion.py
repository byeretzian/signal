from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from signal_app.domain import ArtistListeningMetrics
from signal_app.ingestion import MissingArtistExternalIdError, refresh_artist_metrics
from signal_app.models import Artist, ArtistExternalId, ArtistMetricSnapshot


class FakeListeningMetricsProvider:
    def __init__(self, listen_count: int = 12_000, listener_count: int = 800) -> None:
        self.listen_count = listen_count
        self.listener_count = listener_count
        self.requested_ids: list[str] = []

    def get_artist_metrics(self, artist_external_id: str) -> ArtistListeningMetrics:
        self.requested_ids.append(artist_external_id)
        return ArtistListeningMetrics(
            source="listenbrainz",
            external_id=artist_external_id,
            listen_count=self.listen_count,
            listener_count=self.listener_count,
            metadata={"artist_mbid": artist_external_id, "metric_semantics": "cumulative"},
        )


def test_refresh_artist_metrics_is_idempotent_per_day(session: Session) -> None:
    artist = Artist(name="Bicep")
    artist.external_ids.append(
        ArtistExternalId(provider="musicbrainz", external_id="artist-mbid")
    )
    session.add(artist)
    session.commit()
    provider = FakeListeningMetricsProvider()

    first = refresh_artist_metrics(
        session,
        artist=artist,
        provider=provider,
        snapshot_date=date(2026, 8, 22),
    )
    provider.listen_count = 12_500
    second = refresh_artist_metrics(
        session,
        artist=artist,
        provider=provider,
        snapshot_date=date(2026, 8, 22),
    )

    assert first.id == second.id
    assert second.listen_count == 12_500
    assert second.listener_count == 800
    assert second.source == "listenbrainz"
    assert second.provider_metadata["metric_semantics"] == "cumulative"
    assert provider.requested_ids == ["artist-mbid", "artist-mbid"]
    assert session.scalar(select(func.count()).select_from(ArtistMetricSnapshot)) == 1


def test_refresh_requires_musicbrainz_artist_id(session: Session) -> None:
    artist = Artist(name="Unlinked artist")
    session.add(artist)
    session.commit()

    with pytest.raises(MissingArtistExternalIdError, match="musicbrainz"):
        refresh_artist_metrics(
            session,
            artist=artist,
            provider=FakeListeningMetricsProvider(),
            snapshot_date=date(2026, 8, 22),
        )
