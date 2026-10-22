from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from signal_app.api import app, get_listenbrainz_provider
from signal_app.config import Settings, get_settings
from signal_app.db import get_session
from signal_app.domain import ArtistListeningMetrics
from signal_app.models import Artist, ArtistExternalId, ArtistMetricSnapshot


class FakeListenBrainzProvider:
    def get_artist_metrics(self, artist_external_id: str) -> ArtistListeningMetrics:
        return ArtistListeningMetrics(
            source="listenbrainz",
            external_id=artist_external_id,
            listen_count=25_000,
            listener_count=1_250,
            metadata={"artist_mbid": artist_external_id, "metric_semantics": "cumulative"},
        )


def test_health_and_artist_not_found(session: Session) -> None:
    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            health = client.get("/health")
            missing = client.get("/artists/018f79ad-cbb0-7df9-8bd3-610467f94634")
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "database": "ok"}
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_query_endpoint_returns_tool_trace_and_verified_value(session: Session) -> None:
    artist = Artist(name="Bicep")
    session.add(artist)
    session.flush()
    session.add_all(
        [
            ArtistMetricSnapshot(
                artist_id=artist.id,
                snapshot_date=date(2026, 5, 1),
                source="test",
                listener_count=500,
            ),
            ArtistMetricSnapshot(
                artist_id=artist.id,
                snapshot_date=date(2026, 5, 31),
                source="test",
                listener_count=600,
            ),
        ]
    )
    session.commit()

    def override_session() -> Iterator[Session]:
        yield session

    def override_settings() -> Settings:
        return Settings(openai_api_key=None)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = override_settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/query",
                json={
                    "question": "How much has this artist grown over the last 30 days?",
                    "artist_id": str(artist.id),
                    "end_date": "2026-05-31",
                    "source": "test",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["supporting_data"]["percentage_change"] == 20.0
        assert body["tools"][0]["tool"] == "calculate_growth"
        assert body["sources"] == ["test"]
    finally:
        app.dependency_overrides.clear()


def test_refresh_metrics_endpoint_persists_real_source_idempotently(session: Session) -> None:
    artist = Artist(name="Floating Points")
    artist.external_ids.append(
        ArtistExternalId(provider="musicbrainz", external_id="artist-mbid")
    )
    session.add(artist)
    session.commit()

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_listenbrainz_provider] = FakeListenBrainzProvider
    try:
        with TestClient(app) as client:
            first = client.post(f"/artists/{artist.id}/metrics/refresh")
            second = client.post(f"/artists/{artist.id}/metrics/refresh")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert second.json()["source"] == "listenbrainz"
        assert second.json()["listen_count"] == 25_000
        assert second.json()["listener_count"] == 1_250
        snapshots = session.scalars(
            select(ArtistMetricSnapshot).where(
                ArtistMetricSnapshot.artist_id == artist.id,
                ArtistMetricSnapshot.source == "listenbrainz",
            )
        ).all()
        assert len(snapshots) == 1
    finally:
        app.dependency_overrides.clear()
