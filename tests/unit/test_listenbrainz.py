from __future__ import annotations

import json

import httpx
import pytest

from signal_app.providers.errors import ProviderResponseError
from signal_app.providers.listenbrainz import ListenBrainzProvider


def test_provider_fetches_typed_artist_popularity() -> None:
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json=[
                {
                    "artist_mbid": "artist-mbid",
                    "total_listen_count": 12_345,
                    "total_user_count": 678,
                    "future-field": "ignored",
                }
            ],
            headers={"X-RateLimit-Remaining": "42"},
        )

    provider = ListenBrainzProvider(
        base_url="https://listenbrainz.test",
        user_agent="Signal/0.2.0 (test@example.com)",
        user_token="secret-token",
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            headers={
                "User-Agent": "Signal/0.2.0 (test@example.com)",
                "Authorization": "Token secret-token",
            },
        ),
    )

    metrics = provider.get_artist_metrics("artist-mbid")

    assert metrics.source == "listenbrainz"
    assert metrics.listen_count == 12_345
    assert metrics.listener_count == 678
    assert metrics.metadata["metric_semantics"] == "cumulative"
    assert seen_request is not None
    assert seen_request.method == "POST"
    assert seen_request.url.path == "/1/popularity/artist"
    assert json.loads(seen_request.content) == {"artist_mbids": ["artist-mbid"]}
    assert seen_request.headers["Authorization"] == "Token secret-token"


def test_provider_retries_rate_limit_using_reset_header() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"X-RateLimit-Reset-In": "2"})
        return httpx.Response(
            200,
            json=[
                {
                    "artist_mbid": "artist-mbid",
                    "total_listen_count": 100,
                    "total_user_count": 10,
                }
            ],
        )

    provider = ListenBrainzProvider(
        base_url="https://listenbrainz.test",
        user_agent="Signal/0.2.0 (test@example.com)",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=delays.append,
    )

    assert provider.get_artist_metrics("artist-mbid").listen_count == 100
    assert attempts == 2
    assert delays == [2.0]


def test_provider_rejects_mismatched_artist_response() -> None:
    provider = ListenBrainzProvider(
        base_url="https://listenbrainz.test",
        user_agent="Signal/0.2.0 (test@example.com)",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json=[
                        {
                            "artist_mbid": "different-artist",
                            "total_listen_count": 100,
                            "total_user_count": 10,
                        }
                    ],
                )
            )
        ),
    )

    with pytest.raises(ProviderResponseError, match="unexpected artist"):
        provider.get_artist_metrics("artist-mbid")
