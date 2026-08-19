from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from signal_app.api import app
from signal_app.config import Settings, get_settings
from signal_app.db import get_session
from signal_app.models import Artist, ArtistMetricSnapshot


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
