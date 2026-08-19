from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class NormalizedArtist(BaseModel):
    external_id: str
    name: str
    sort_name: str | None = None
    country: str | None = None
    disambiguation: str | None = None
    score: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedRelease(BaseModel):
    external_id: str
    title: str
    release_date: date | None = None
    release_type: str | None = None
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtistMetadataProvider(Protocol):
    def search_artists(self, query: str, *, limit: int = 10) -> list[NormalizedArtist]: ...

    def get_artist(self, external_id: str) -> NormalizedArtist: ...


class ReleaseMetadataProvider(Protocol):
    def get_artist_releases(
        self, artist_external_id: str, *, limit: int = 25
    ) -> list[NormalizedRelease]: ...


class ArtistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    sort_name: str | None
    country: str | None
    disambiguation: str | None
    external_ids: dict[str, str]


class ReleaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    release_date: date | None
    release_type: str | None
    status: str | None
    external_ids: dict[str, str]
