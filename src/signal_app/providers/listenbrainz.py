from __future__ import annotations

import time
from collections.abc import Callable

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from signal_app.domain import ArtistListeningMetrics
from signal_app.providers.errors import ProviderResponseError, ProviderUnavailableError

logger = structlog.get_logger(__name__)


class ListenBrainzArtistPopularity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    artist_mbid: str
    total_listen_count: int | None = Field(default=None, ge=0)
    total_user_count: int | None = Field(default=None, ge=0)


class ListenBrainzProvider:
    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        user_token: str | None = None,
        timeout_seconds: float = 10,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ) -> None:
        headers = {"User-Agent": user_agent, "Accept": "application/json"}
        if user_token:
            headers["Authorization"] = f"Token {user_token}"
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(headers=headers, timeout=timeout_seconds)
        self._sleeper = sleeper
        self._max_attempts = max_attempts

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            reset_in = response.headers.get("X-RateLimit-Reset-In")
            if reset_in:
                try:
                    delay = float(reset_in)
                    return min(max(delay, 0.0), 30.0)
                except ValueError:
                    pass
        return 0.25 * (2.0 ** (attempt - 1))

    def get_artist_metrics(self, artist_external_id: str) -> ArtistListeningMetrics:
        path = "/1/popularity/artist"
        url = f"{self._base_url}{path}"
        for attempt in range(1, self._max_attempts + 1):
            response: httpx.Response | None = None
            started = time.monotonic()
            try:
                response = self._client.post(
                    url,
                    json={"artist_mbids": [artist_external_id]},
                )
                response.raise_for_status()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == self._max_attempts:
                    raise ProviderUnavailableError("ListenBrainz request failed") from exc
                self._sleeper(self._retry_delay(response, attempt))
                continue
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in {429, 500, 502, 503, 504} and attempt < self._max_attempts:
                    self._sleeper(self._retry_delay(exc.response, attempt))
                    continue
                if 400 <= status < 500 and status != 429:
                    raise ProviderResponseError(
                        f"ListenBrainz rejected the request with HTTP {status}"
                    ) from exc
                raise ProviderUnavailableError(
                    f"ListenBrainz returned HTTP {status}"
                ) from exc

            logger.info(
                "provider_request",
                provider="listenbrainz",
                path=path,
                status=response.status_code,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                rate_limit_remaining=response.headers.get("X-RateLimit-Remaining"),
            )
            try:
                payload = TypeAdapter(list[ListenBrainzArtistPopularity]).validate_python(
                    response.json()
                )
            except (ValidationError, ValueError) as exc:
                raise ProviderResponseError("Invalid ListenBrainz artist response") from exc
            if len(payload) != 1 or payload[0].artist_mbid != artist_external_id:
                raise ProviderResponseError("ListenBrainz returned an unexpected artist response")
            popularity = payload[0]
            return ArtistListeningMetrics(
                source="listenbrainz",
                external_id=popularity.artist_mbid,
                listen_count=popularity.total_listen_count,
                listener_count=popularity.total_user_count,
                metadata={
                    "artist_mbid": popularity.artist_mbid,
                    "metric_semantics": "cumulative",
                },
            )
        raise AssertionError("unreachable")
