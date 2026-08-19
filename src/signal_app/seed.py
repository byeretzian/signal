from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from signal_app.db import SessionLocal
from signal_app.models import Artist, ArtistExternalId, ArtistMetricSnapshot


def seed_demo_snapshots_for_artist(session: Session, artist: Artist) -> None:
    """Attach explicitly synthetic data so the Milestone 1 workflow is demonstrable."""
    today = date.today()
    existing_dates = set(
        session.scalars(
            select(ArtistMetricSnapshot.snapshot_date).where(
                ArtistMetricSnapshot.artist_id == artist.id,
                ArtistMetricSnapshot.source == "demo",
            )
        ).all()
    )
    for days_ago in range(30, -1, -1):
        snapshot_date = today - timedelta(days=days_ago)
        if snapshot_date not in existing_dates:
            session.add(
                ArtistMetricSnapshot(
                    artist_id=artist.id,
                    snapshot_date=snapshot_date,
                    source="demo",
                    listener_count=1_000 + (30 - days_ago) * 10,
                    listen_count=10_000 + (30 - days_ago) * 120,
                    provider_metadata={"synthetic": True},
                )
            )


def seed() -> None:
    with SessionLocal.begin() as session:
        artist = session.scalar(select(Artist).where(Artist.name == "Signal Demo Artist"))
        if artist is None:
            artist = Artist(name="Signal Demo Artist", sort_name="Signal Demo Artist")
            artist.external_ids.append(
                ArtistExternalId(provider="demo", external_id="signal-demo-artist")
            )
            session.add(artist)
            session.flush()
        seed_demo_snapshots_for_artist(session, artist)


if __name__ == "__main__":
    seed()
