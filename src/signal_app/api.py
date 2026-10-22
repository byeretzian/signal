from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from functools import lru_cache
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from signal_app.agent import (
    GrowthAgent,
    OpenAIQuestionInterpreter,
    QueryResponse,
    RuleBasedQuestionInterpreter,
)
from signal_app.catalog import ArtistNotFoundError, get_artist, import_artist
from signal_app.config import Settings, get_settings
from signal_app.db import get_session
from signal_app.domain import ArtistRead, MetricSnapshotRead, NormalizedArtist, ReleaseRead
from signal_app.ingestion import MissingArtistExternalIdError, refresh_artist_metrics
from signal_app.logging import configure_logging
from signal_app.models import Artist, ArtistMetricSnapshot, Release
from signal_app.providers.errors import ProviderError
from signal_app.providers.listenbrainz import ListenBrainzProvider
from signal_app.providers.musicbrainz import MusicBrainzProvider

logger = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    status: str
    database: str


class ImportedArtistResponse(BaseModel):
    artist: ArtistRead
    release_count: int


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1_000)
    artist_id: uuid.UUID
    end_date: date = Field(default_factory=date.today)
    source: str = Field(default="demo", min_length=1, max_length=50)


def artist_to_read(artist: Artist) -> ArtistRead:
    return ArtistRead(
        id=str(artist.id),
        name=artist.name,
        sort_name=artist.sort_name,
        country=artist.country,
        disambiguation=artist.disambiguation,
        external_ids={item.provider: item.external_id for item in artist.external_ids},
    )


def release_to_read(release: Release) -> ReleaseRead:
    return ReleaseRead(
        id=str(release.id),
        title=release.title,
        release_date=release.release_date,
        release_type=release.release_type,
        status=release.status,
        external_ids={item.provider: item.external_id for item in release.external_ids},
    )


def snapshot_to_read(snapshot: ArtistMetricSnapshot) -> MetricSnapshotRead:
    return MetricSnapshotRead(
        id=str(snapshot.id),
        artist_id=str(snapshot.artist_id),
        snapshot_date=snapshot.snapshot_date,
        source=snapshot.source,
        listen_count=snapshot.listen_count,
        listener_count=snapshot.listener_count,
        provider_metadata=snapshot.provider_metadata,
    )


@lru_cache
def get_musicbrainz_provider() -> MusicBrainzProvider:
    settings = get_settings()
    return MusicBrainzProvider(
        base_url=settings.musicbrainz_base_url,
        user_agent=settings.musicbrainz_user_agent,
        timeout_seconds=settings.musicbrainz_timeout_seconds,
    )


@lru_cache
def get_listenbrainz_provider() -> ListenBrainzProvider:
    settings = get_settings()
    return ListenBrainzProvider(
        base_url=settings.listenbrainz_base_url,
        user_agent=settings.listenbrainz_user_agent,
        user_token=settings.listenbrainz_user_token,
        timeout_seconds=settings.listenbrainz_timeout_seconds,
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    yield


app = FastAPI(
    title="Signal API",
    version="0.1.0",
    description="Evidence-backed music intelligence",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_observability(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    started = time.monotonic()
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    logger.info(
        "api_request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round((time.monotonic() - started) * 1000, 2),
    )
    return response


@app.get("/health", response_model=HealthResponse)
def health(session: Annotated[Session, Depends(get_session)]) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("health_database_failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return HealthResponse(status="ok", database="ok")


@app.get("/artists/search", response_model=list[NormalizedArtist])
def search_artists(
    provider: Annotated[MusicBrainzProvider, Depends(get_musicbrainz_provider)],
    q: Annotated[str, Query(min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> list[NormalizedArtist]:
    try:
        return provider.search_artists(q, limit=limit)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/artists/import/{musicbrainz_id}", response_model=ImportedArtistResponse)
def import_musicbrainz_artist(
    musicbrainz_id: str,
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[MusicBrainzProvider, Depends(get_musicbrainz_provider)],
    include_demo_metrics: Annotated[bool, Query()] = False,
) -> ImportedArtistResponse:
    try:
        normalized = provider.get_artist(musicbrainz_id)
        releases = provider.get_artist_releases(musicbrainz_id)
        persisted = import_artist(
            session,
            normalized,
            releases,
            include_demo_metrics=include_demo_metrics,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ImportedArtistResponse(artist=artist_to_read(persisted), release_count=len(releases))


@app.get("/artists/{artist_id}", response_model=ArtistRead)
def read_artist(
    artist_id: uuid.UUID, session: Annotated[Session, Depends(get_session)]
) -> ArtistRead:
    try:
        return artist_to_read(get_artist(session, artist_id))
    except ArtistNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artist not found") from exc


@app.get("/artists/{artist_id}/releases", response_model=list[ReleaseRead])
def read_artist_releases(
    artist_id: uuid.UUID, session: Annotated[Session, Depends(get_session)]
) -> list[ReleaseRead]:
    try:
        artist = get_artist(session, artist_id)
    except ArtistNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artist not found") from exc
    return [release_to_read(release) for release in artist.releases]


@app.post("/artists/{artist_id}/metrics/refresh", response_model=MetricSnapshotRead)
def refresh_artist_listening_metrics(
    artist_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    provider: Annotated[ListenBrainzProvider, Depends(get_listenbrainz_provider)],
) -> MetricSnapshotRead:
    try:
        artist = get_artist(session, artist_id)
        snapshot = refresh_artist_metrics(session, artist=artist, provider=provider)
    except ArtistNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artist not found") from exc
    except MissingArtistExternalIdError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return snapshot_to_read(snapshot)


@app.post("/query", response_model=QueryResponse)
def query_signal(
    payload: QueryRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> QueryResponse:
    try:
        artist = get_artist(session, payload.artist_id)
    except ArtistNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artist not found") from exc
    interpreter = (
        OpenAIQuestionInterpreter(model=settings.openai_model, api_key=settings.openai_api_key)
        if settings.openai_api_key
        else RuleBasedQuestionInterpreter()
    )
    agent = GrowthAgent(session=session, interpreter=interpreter)
    return agent.run(
        question=payload.question,
        artist_id=artist.id,
        artist_name=artist.name,
        end_date=payload.end_date,
        source=payload.source,
    )
