"""Create the additive production reliability and operations schema.

Revision ID: 20260729_01
Revises:
Create Date: 2026-07-29
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

from alembic import op
import sqlalchemy as sa

from db import Base
import models  # noqa: F401  # register all tables


revision: str = "20260729_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_MESSAGE_RETENTION_DAYS = 30


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {
        str(index["name"])
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


def _dedupe_key_is_unique(bind) -> bool:
    inspector = sa.inspect(bind)
    if "outbox_jobs" not in inspector.get_table_names():
        return False
    for constraint in inspector.get_unique_constraints("outbox_jobs"):
        if constraint.get("column_names") == ["dedupe_key"]:
            return True
    return any(
        index.get("unique")
        and index.get("column_names") == ["dedupe_key"]
        for index in inspector.get_indexes("outbox_jobs")
    )


def _add_compatibility_columns(bind) -> None:
    """Upgrade databases created by pre-Alembic release candidates."""

    support_columns = _column_names(bind, "support_requests")
    support_indexes = _index_names(bind, "support_requests")
    if support_columns:
        with op.batch_alter_table("support_requests") as batch:
            if "resolution_note" not in support_columns:
                batch.add_column(sa.Column("resolution_note", sa.Text()))
            if "sla_due_at" not in support_columns:
                batch.add_column(sa.Column("sla_due_at", sa.DateTime()))
            if "ix_support_requests_sla_due_at" not in support_indexes:
                batch.create_index(
                    "ix_support_requests_sla_due_at",
                    ["sla_due_at"],
                    unique=False,
                )

    outbox_columns = _column_names(bind, "outbox_jobs")
    outbox_indexes = _index_names(bind, "outbox_jobs")
    if outbox_columns:
        with op.batch_alter_table("outbox_jobs") as batch:
            if "dedupe_key" not in outbox_columns:
                batch.add_column(sa.Column("dedupe_key", sa.String(255)))
            if not _dedupe_key_is_unique(bind):
                batch.create_unique_constraint(
                    "uq_outbox_jobs_dedupe_key",
                    ["dedupe_key"],
                )
            if "ix_outbox_jobs_dedupe_key" not in outbox_indexes:
                batch.create_index(
                    "ix_outbox_jobs_dedupe_key",
                    ["dedupe_key"],
                    unique=True,
                )


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _legacy_datetime(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            pass
    return _naive_utc_now()


def _backfill_legacy_message_claims(bind) -> None:
    tables = set(sa.inspect(bind).get_table_names())
    if not {"processed_messages", "inbound_message_events"}.issubset(tables):
        return

    metadata = sa.MetaData()
    legacy = sa.Table("processed_messages", metadata, autoload_with=bind)
    current = sa.Table("inbound_message_events", metadata, autoload_with=bind)
    result = bind.execute(
        sa.select(legacy.c.message_id, legacy.c.created_at).where(
            ~sa.exists(
                sa.select(1).where(
                    current.c.message_id == legacy.c.message_id
                )
            )
        )
    )
    while True:
        rows = result.fetchmany(500)
        if not rows:
            break
        payloads = []
        for row in rows:
            received_at = _legacy_datetime(row.created_at)
            payloads.append(
                {
                    "message_id": row.message_id,
                    "status": "DONE",
                    "attempts": 1,
                    "received_at": received_at,
                    "processed_at": received_at,
                    "expires_at": received_at
                    + timedelta(days=_LEGACY_MESSAGE_RETENTION_DAYS),
                }
            )
        bind.execute(current.insert(), payloads)


def _backfill_paid_fulfilments(bind) -> None:
    tables = set(sa.inspect(bind).get_table_names())
    if not {"bookings", "booking_fulfillments"}.issubset(tables):
        return

    bind.execute(
        sa.text(
            """
            INSERT INTO booking_fulfillments (
                booking_id,
                status,
                sla_due_at,
                created_at,
                updated_at,
                completed_at
            )
            SELECT
                booking.id,
                CASE
                    WHEN booking.status = 'COMPLETED' THEN 'COMPLETED'
                    ELSE 'UNASSIGNED'
                END,
                CASE
                    WHEN booking.status = 'COMPLETED' THEN NULL
                    ELSE COALESCE(booking.created_at, CURRENT_TIMESTAMP)
                END,
                COALESCE(booking.created_at, CURRENT_TIMESTAMP),
                COALESCE(booking.created_at, CURRENT_TIMESTAMP),
                CASE
                    WHEN booking.status = 'COMPLETED'
                        THEN COALESCE(booking.created_at, CURRENT_TIMESTAMP)
                    ELSE NULL
                END
            FROM bookings AS booking
            WHERE booking.status IN ('PAID', 'COMPLETED')
              AND NOT EXISTS (
                  SELECT 1
                  FROM booking_fulfillments AS fulfilment
                  WHERE fulfilment.booking_id = booking.id
              )
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()

    # The production origin already has the core tables but no migration
    # history. create_all is safe here because this revision is deliberately
    # additive: it creates missing tables and never rewrites existing ones.
    Base.metadata.create_all(bind=bind)
    _add_compatibility_columns(bind)
    _backfill_legacy_message_claims(bind)
    _backfill_paid_fulfilments(bind)


def downgrade() -> None:
    # Application rollback is schema-compatible with all additive tables.
    # Preserve operational/payment evidence rather than dropping it during an
    # emergency code rollback. A later upgrade is idempotent.
    pass
