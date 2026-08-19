from __future__ import annotations

import httpx

from signal_app.providers.musicbrainz import (
    MusicBrainzArtist,
    MusicBrainzProvider,
    OneRequestPerSecondLimiter,
    normalize_artist,
)


def test_normalize_artist_keeps_domain_fields_and_provider_metadata() -> None:
    wire_artist = MusicBrainzArtist.model_validate(
        {
            "id": "f2a7d9e5-7a02-44a5-a0af-e46061f6e6c8",
            "name": "The Field",
            "sort-name": "Field, The",
            "country": "SE",
            "disambiguation": "Swedish electronic musician Axel Willner",
            "score": 100,
            "type": "Person",
            "tags": [{"name": "minimal techno", "count": 8}],
            "unknown-field": "ignored",
        }
    )

    normalized = normalize_artist(wire_artist)

    assert normalized.name == "The Field"
    assert normalized.sort_name == "Field, The"
    assert normalized.country == "SE"
    assert normalized.metadata == {"type": "Person", "tags": ["minimal techno"]}


def test_provider_search_uses_typed_normalization_and_required_format() -> None:
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json={"artists": [{"id": "artist-1", "name": "Floating Points", "country": "GB"}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = MusicBrainzProvider(
        base_url="https://musicbrainz.test/ws/2",
        user_agent="Signal/0.1.0 (test@example.com)",
        client=client,
        limiter=OneRequestPerSecondLimiter(interval_seconds=0),
    )

    results = provider.search_artists("Floating Points", limit=5)

    assert results[0].name == "Floating Points"
    assert seen_request is not None
    assert seen_request.url.params["fmt"] == "json"
    assert seen_request.url.params["limit"] == "5"


def test_provider_retries_transient_errors() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"artists": []})

    provider = MusicBrainzProvider(
        base_url="https://musicbrainz.test/ws/2",
        user_agent="Signal/0.1.0 (test@example.com)",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        limiter=OneRequestPerSecondLimiter(interval_seconds=0),
        sleeper=lambda _: None,
    )

    assert provider.search_artists("test") == []
    assert attempts == 3


def test_provider_caches_repeated_identical_searches() -> None:
    requests = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json={"artists": []})

    provider = MusicBrainzProvider(
        base_url="https://musicbrainz.test/ws/2",
        user_agent="Signal/0.1.0 (test@example.com)",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        limiter=OneRequestPerSecondLimiter(interval_seconds=0),
    )

    provider.search_artists("Burial")
    provider.search_artists("Burial")

    assert requests == 1
