from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from signal_app.domain import ListeningMetricsProvider
from signal_app.models import Artist, ArtistMetricSnapshot


class MissingArtistExternalIdError(LookupError):
    pass


def _artist_external_id(artist: Artist, provider: str) -> str:
    external_id = next(
        (item.external_id for item in artist.external_ids if item.provider == provider),
        None,
    )
    if external_id is None:
        raise MissingArtistExternalIdError(
            f"Artist {artist.id} has no {provider} external identifier"
        )
    return external_id


def refresh_artist_metrics(
    session: Session,
    *,
    artist: Artist,
    provider: ListeningMetricsProvider,
    snapshot_date: date | None = None,
) -> ArtistMetricSnapshot:
    """Fetch and idempotently persist one provider-reported daily artist snapshot."""
    observed_on = snapshot_date or date.today()
    musicbrainz_id = _artist_external_id(artist, "musicbrainz")
    metrics = provider.get_artist_metrics(musicbrainz_id)
    snapshot = session.scalar(
        select(ArtistMetricSnapshot).where(
            ArtistMetricSnapshot.artist_id == artist.id,
            ArtistMetricSnapshot.snapshot_date == observed_on,
            ArtistMetricSnapshot.source == metrics.source,
        )
    )
    if snapshot is None:
        snapshot = ArtistMetricSnapshot(
            artist_id=artist.id,
            snapshot_date=observed_on,
            source=metrics.source,
        )
        session.add(snapshot)
    snapshot.listen_count = metrics.listen_count
    snapshot.listener_count = metrics.listener_count
    snapshot.provider_metadata = metrics.metadata
    session.commit()
    session.refresh(snapshot)
    return snapshot
