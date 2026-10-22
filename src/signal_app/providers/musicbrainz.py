from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from signal_app.domain import NormalizedArtist, NormalizedRelease
from signal_app.providers.errors import (
    ProviderResponseError,
    ProviderUnavailableError,
)

logger = structlog.get_logger(__name__)


class MusicBrainzArea(BaseModel):
    model_config = ConfigDict(extra="ignore")
    iso_3166_1_codes: list[str] = Field(default_factory=list, alias="iso-3166-1-codes")


class MusicBrainzTag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    count: int = 0


class MusicBrainzArtist(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    sort_name: str | None = Field(default=None, alias="sort-name")
    country: str | None = None
    disambiguation: str | None = None
    score: int | None = None
    area: MusicBrainzArea | None = None
    tags: list[MusicBrainzTag] = Field(default_factory=list)
    type: str | None = None


class MusicBrainzArtistSearch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    artists: list[MusicBrainzArtist] = Field(default_factory=list)


class MusicBrainzReleaseGroup(BaseModel):
    model_config = ConfigDict(extra="ignore")
    primary_type: str | None = Field(default=None, alias="primary-type")


class MusicBrainzRelease(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    date: str | None = None
    status: str | None = None
    country: str | None = None
    release_group: MusicBrainzReleaseGroup | None = Field(default=None, alias="release-group")


class MusicBrainzReleaseSearch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    releases: list[MusicBrainzRelease] = Field(default_factory=list)


def normalize_artist(artist: MusicBrainzArtist) -> NormalizedArtist:
    country = artist.country
    if country is None and artist.area and artist.area.iso_3166_1_codes:
        country = artist.area.iso_3166_1_codes[0]
    return NormalizedArtist(
        external_id=artist.id,
        name=artist.name,
        sort_name=artist.sort_name,
        country=country,
        disambiguation=artist.disambiguation or None,
        score=artist.score,
        metadata={
            "type": artist.type,
            "tags": [tag.name for tag in artist.tags if tag.count >= 0],
        },
    )


def _parse_partial_date(value: str | None) -> date | None:
    if not value:
        return None
    parts = value.split("-")
    try:
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        return date(int(parts[0]), 1, 1)
    except (ValueError, IndexError):
        return None


def normalize_release(release: MusicBrainzRelease) -> NormalizedRelease:
    return NormalizedRelease(
        external_id=release.id,
        title=release.title,
        release_date=_parse_partial_date(release.date),
        release_type=(release.release_group.primary_type if release.release_group else None),
        status=release.status,
        metadata={"country": release.country, "source_date": release.date},
    )


class OneRequestPerSecondLimiter:
    def __init__(
        self,
        interval_seconds: float = 1.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last_request_at is not None:
                delay = self._interval - (now - self._last_request_at)
                if delay > 0:
                    self._sleeper(delay)
                    now = self._clock()
            self._last_request_at = now


class MusicBrainzProvider:
    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        timeout_seconds: float = 10,
        client: httpx.Client | None = None,
        limiter: OneRequestPerSecondLimiter | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
        cache_ttl_seconds: float = 300,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout_seconds,
        )
        self._limiter = limiter or OneRequestPerSecondLimiter()
        self._sleeper = sleeper
        self._max_attempts = max_attempts
        self._cache_ttl_seconds = cache_ttl_seconds
        self._clock = clock
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_lock = threading.Lock()

    def _cache_key(self, path: str, params: dict[str, Any]) -> str:
        return f"{path}?{sorted(params.items())!r}"

    def _get_cached(self, key: str) -> dict[str, Any] | None:
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is None:
                return None
            cached_at, payload = cached
            if self._clock() - cached_at > self._cache_ttl_seconds:
                del self._cache[key]
                return None
            return payload.copy()

    def _set_cached(self, key: str, payload: dict[str, Any]) -> None:
        with self._cache_lock:
            self._cache[key] = (self._clock(), payload.copy())

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        params = {**params, "fmt": "json"}
        cache_key = self._cache_key(path, params)
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.info("provider_cache_hit", provider="musicbrainz", path=path)
            return cached
        for attempt in range(1, self._max_attempts + 1):
            self._limiter.wait()
            started = time.monotonic()
            try:
                response = self._client.get(f"{self._base_url}/{path.lstrip('/')}", params=params)
                response.raise_for_status()
                data = response.json()
                logger.info(
                    "provider_request",
                    provider="musicbrainz",
                    path=path,
                    status=response.status_code,
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                )
                if not isinstance(data, dict):
                    raise ProviderResponseError("MusicBrainz returned a non-object JSON response")
                self._set_cached(cache_key, data)
                return data
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == self._max_attempts:
                    raise ProviderUnavailableError("MusicBrainz request failed") from exc
            except httpx.HTTPStatusError as exc:
                if (
                    exc.response.status_code not in {429, 500, 502, 503, 504}
                    or attempt == self._max_attempts
                ):
                    raise ProviderUnavailableError(
                        f"MusicBrainz returned HTTP {exc.response.status_code}"
                    ) from exc
            self._sleeper(0.25 * (2 ** (attempt - 1)))
        raise AssertionError("unreachable")

    def search_artists(self, query: str, *, limit: int = 10) -> list[NormalizedArtist]:
        try:
            payload = MusicBrainzArtistSearch.model_validate(
                self._get("artist", {"query": query, "limit": min(limit, 25)})
            )
        except ValidationError as exc:
            raise ProviderResponseError("Invalid MusicBrainz artist search response") from exc
        return [normalize_artist(artist) for artist in payload.artists]

    def get_artist(self, external_id: str) -> NormalizedArtist:
        try:
            artist = MusicBrainzArtist.model_validate(
                self._get(f"artist/{external_id}", {"inc": "tags"})
            )
        except ValidationError as exc:
            raise ProviderResponseError("Invalid MusicBrainz artist response") from exc
        return normalize_artist(artist)

    def get_artist_releases(
        self, artist_external_id: str, *, limit: int = 25
    ) -> list[NormalizedRelease]:
        try:
            payload = MusicBrainzReleaseSearch.model_validate(
                self._get(
                    "release",
                    {
                        "artist": artist_external_id,
                        "limit": min(limit, 100),
                        "inc": "release-groups",
                    },
                )
            )
        except ValidationError as exc:
            raise ProviderResponseError("Invalid MusicBrainz release response") from exc
        return [normalize_release(release) for release in payload.releases]
