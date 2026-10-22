from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from signal_app.catalog import import_artist
from signal_app.domain import NormalizedArtist, NormalizedRelease
from signal_app.models import Artist, ArtistMetricSnapshot, Release


def test_import_artist_is_idempotent_and_demo_metrics_are_opt_in(session: Session) -> None:
    normalized_artist = NormalizedArtist(
        external_id="artist-mbid",
        name="Four Tet",
        country="GB",
    )
    normalized_release = NormalizedRelease(
        external_id="release-mbid",
        title="New Energy",
        release_date=date(2017, 9, 29),
        release_type="Album",
    )

    first = import_artist(session, normalized_artist, [normalized_release])
    second = import_artist(session, normalized_artist, [normalized_release])

    assert first.id == second.id
    assert session.scalar(select(func.count()).select_from(Artist)) == 1
    assert session.scalar(select(func.count()).select_from(Release)) == 1
    assert session.scalar(select(func.count()).select_from(ArtistMetricSnapshot)) == 0

    import_artist(
        session,
        normalized_artist,
        [normalized_release],
        include_demo_metrics=True,
    )

    assert session.scalar(select(func.count()).select_from(ArtistMetricSnapshot)) == 31
    first_snapshot = session.scalar(select(ArtistMetricSnapshot))
    assert first_snapshot is not None
    assert first_snapshot.source == "demo"
    assert first_snapshot.provider_metadata == {"synthetic": True}
