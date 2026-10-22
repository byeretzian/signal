from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from signal_app.domain import NormalizedArtist, NormalizedRelease
from signal_app.models import Artist, ArtistExternalId, Release, ReleaseExternalId
from signal_app.seed import seed_demo_snapshots_for_artist


class ArtistNotFoundError(LookupError):
    pass


def get_artist(session: Session, artist_id: uuid.UUID) -> Artist:
    artist = session.get(Artist, artist_id)
    if artist is None:
        raise ArtistNotFoundError(str(artist_id))
    return artist


def upsert_artist(
    session: Session, normalized: NormalizedArtist, *, provider: str = "musicbrainz"
) -> Artist:
    external_id = session.scalar(
        select(ArtistExternalId).where(
            ArtistExternalId.provider == provider,
            ArtistExternalId.external_id == normalized.external_id,
        )
    )
    artist = external_id.artist if external_id else Artist(name=normalized.name)
    artist.name = normalized.name
    artist.sort_name = normalized.sort_name
    artist.country = normalized.country
    artist.disambiguation = normalized.disambiguation
    artist.provider_metadata = normalized.metadata
    if external_id is None:
        artist.external_ids.append(
            ArtistExternalId(provider=provider, external_id=normalized.external_id)
        )
        session.add(artist)
    session.flush()
    return artist


def upsert_release(
    session: Session,
    normalized: NormalizedRelease,
    artist: Artist,
    *,
    provider: str = "musicbrainz",
) -> Release:
    external_id = session.scalar(
        select(ReleaseExternalId).where(
            ReleaseExternalId.provider == provider,
            ReleaseExternalId.external_id == normalized.external_id,
        )
    )
    release = external_id.release if external_id else Release(title=normalized.title)
    release.title = normalized.title
    release.release_date = normalized.release_date
    release.release_type = normalized.release_type
    release.status = normalized.status
    release.provider_metadata = normalized.metadata
    if external_id is None:
        release.external_ids.append(
            ReleaseExternalId(provider=provider, external_id=normalized.external_id)
        )
        session.add(release)
    if artist not in release.artists:
        release.artists.append(artist)
    session.flush()
    return release


def import_artist(
    session: Session,
    artist: NormalizedArtist,
    releases: list[NormalizedRelease],
    *,
    include_demo_metrics: bool = False,
) -> Artist:
    persisted = upsert_artist(session, artist)
    for release in releases:
        upsert_release(session, release, persisted)
    if include_demo_metrics:
        seed_demo_snapshots_for_artist(session, persisted)
    session.commit()
    session.refresh(persisted)
    return persisted
