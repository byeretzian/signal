from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from signal_app.models import ArtistMetricSnapshot

MetricName = Literal["listener_count", "listen_count"]


class GrowthStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"
    UNDEFINED_PERCENTAGE = "undefined_percentage"


class SnapshotValue(BaseModel):
    requested_date: date
    actual_date: date | None
    value: int | None


class GrowthResult(BaseModel):
    artist_id: uuid.UUID
    metric: MetricName
    source: str
    start: SnapshotValue
    end: SnapshotValue
    absolute_change: int | None = None
    percentage_change: float | None = None
    status: GrowthStatus
    caveat: str | None = None


def _nearest_snapshot(
    session: Session,
    *,
    artist_id: uuid.UUID,
    requested_date: date,
    source: str,
    tolerance_days: int,
) -> ArtistMetricSnapshot | None:
    candidates = session.scalars(
        select(ArtistMetricSnapshot).where(
            ArtistMetricSnapshot.artist_id == artist_id,
            ArtistMetricSnapshot.source == source,
            ArtistMetricSnapshot.snapshot_date.between(
                requested_date.fromordinal(requested_date.toordinal() - tolerance_days),
                requested_date.fromordinal(requested_date.toordinal() + tolerance_days),
            ),
        )
    ).all()
    return min(
        candidates, key=lambda item: abs((item.snapshot_date - requested_date).days), default=None
    )


def calculate_growth(
    session: Session,
    *,
    artist_id: uuid.UUID,
    start_date: date,
    end_date: date,
    metric: MetricName = "listener_count",
    source: str = "demo",
    tolerance_days: int = 3,
) -> GrowthResult:
    if end_date <= start_date:
        raise ValueError("end_date must be after start_date")

    start_snapshot = _nearest_snapshot(
        session,
        artist_id=artist_id,
        requested_date=start_date,
        source=source,
        tolerance_days=tolerance_days,
    )
    end_snapshot = _nearest_snapshot(
        session,
        artist_id=artist_id,
        requested_date=end_date,
        source=source,
        tolerance_days=tolerance_days,
    )
    start_value = getattr(start_snapshot, metric) if start_snapshot else None
    end_value = getattr(end_snapshot, metric) if end_snapshot else None
    result = GrowthResult(
        artist_id=artist_id,
        metric=metric,
        source=source,
        start=SnapshotValue(
            requested_date=start_date,
            actual_date=start_snapshot.snapshot_date if start_snapshot else None,
            value=start_value,
        ),
        end=SnapshotValue(
            requested_date=end_date,
            actual_date=end_snapshot.snapshot_date if end_snapshot else None,
            value=end_value,
        ),
        status=GrowthStatus.OK,
        caveat=(
            "The demo source contains synthetic snapshots for workflow demonstration, not "
            "provider-reported listening data."
            if source == "demo"
            else None
        ),
    )
    if start_value is None or end_value is None:
        return result.model_copy(
            update={
                "status": GrowthStatus.INSUFFICIENT_DATA,
                "caveat": "No usable metric snapshot was found near one or both requested dates.",
            }
        )
    absolute_change = end_value - start_value
    if start_value == 0:
        return result.model_copy(
            update={
                "absolute_change": absolute_change,
                "status": GrowthStatus.UNDEFINED_PERCENTAGE,
                "caveat": "Percentage growth is undefined because the starting value is zero.",
            }
        )
    return result.model_copy(
        update={
            "absolute_change": absolute_change,
            "percentage_change": round((absolute_change / start_value) * 100, 2),
        }
    )
