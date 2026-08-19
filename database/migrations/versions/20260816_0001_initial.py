"""Create the Milestone 1 catalog and metric tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260816_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False, index=True),
        sa.Column("sort_name", sa.String(300)),
        sa.Column("country", sa.String(2)),
        sa.Column("disambiguation", sa.String(500)),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "artist_external_ids",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "artist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.UniqueConstraint("provider", "external_id", name="uq_artist_provider_external_id"),
    )
    op.create_table(
        "releases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("release_date", sa.Date()),
        sa.Column("release_type", sa.String(80)),
        sa.Column("status", sa.String(80)),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "release_external_ids",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "release_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("releases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.UniqueConstraint("provider", "external_id", name="uq_release_provider_external_id"),
    )
    op.create_table(
        "release_artists",
        sa.Column(
            "release_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("releases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "artist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artists.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "artist_metric_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "artist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("listen_count", sa.BigInteger()),
        sa.Column("listener_count", sa.BigInteger()),
        sa.Column("popularity", sa.Float()),
        sa.Column("release_activity", sa.Integer()),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "listen_count IS NULL OR listen_count >= 0", name="ck_snapshot_listen_count_nonnegative"
        ),
        sa.CheckConstraint(
            "listener_count IS NULL OR listener_count >= 0",
            name="ck_snapshot_listener_count_nonnegative",
        ),
        sa.UniqueConstraint(
            "artist_id", "snapshot_date", "source", name="uq_artist_snapshot_date_source"
        ),
    )
    op.create_index(
        "ix_snapshot_artist_date", "artist_metric_snapshots", ["artist_id", "snapshot_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_snapshot_artist_date", table_name="artist_metric_snapshots")
    op.drop_table("artist_metric_snapshots")
    op.drop_table("release_artists")
    op.drop_table("release_external_ids")
    op.drop_table("releases")
    op.drop_table("artist_external_ids")
    op.drop_table("artists")
