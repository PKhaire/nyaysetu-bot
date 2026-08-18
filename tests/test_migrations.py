from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import sqlalchemy as sa

from db import Base
from models import (
    Advocate,
    Booking,
    BookingStatus,
    ProcessedMessage,
    User,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _database_url(path: Path) -> str:
    return "sqlite:///" + path.resolve().as_posix()


def _upgrade(path: Path) -> None:
    environment = os.environ.copy()
    environment["ENV"] = "test"
    environment["DATABASE_URL"] = _database_url(path)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(PROJECT_ROOT / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_fresh_database_upgrade_builds_current_schema(tmp_path):
    database_path = tmp_path / "fresh.db"

    _upgrade(database_path)

    engine = sa.create_engine(_database_url(database_path))
    try:
        inspector = sa.inspect(engine)
        assert set(Base.metadata.tables).issubset(inspector.get_table_names())
        assert "alembic_version" in inspector.get_table_names()

        inbound_columns = {
            column["name"]
            for column in inspector.get_columns("inbound_message_events")
        }
        assert {
            "status",
            "lease_expires_at",
            "processed_at",
            "expires_at",
        }.issubset(inbound_columns)

        outbox_columns = {
            column["name"]
            for column in inspector.get_columns("outbox_jobs")
        }
        assert "dedupe_key" in outbox_columns

        with engine.connect() as connection:
            assert (
                connection.execute(
                    sa.text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                == "20260818_01"
            )
    finally:
        engine.dispose()


def _create_legacy_database(path: Path) -> None:
    engine = sa.create_engine(_database_url(path))
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                User.__table__,
                Booking.__table__,
                Advocate.__table__,
                ProcessedMessage.__table__,
            ],
        )

        legacy = sa.MetaData()
        support = sa.Table(
            "support_requests",
            legacy,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer()),
            sa.Column("case_id", sa.String(32)),
            sa.Column("request_type", sa.String(64), nullable=False),
            sa.Column("subject", sa.String(160)),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("priority", sa.String(16), nullable=False),
            sa.Column("assigned_to", sa.String(120)),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.Column("resolved_at", sa.DateTime()),
        )
        outbox = sa.Table(
            "outbox_jobs",
            legacy,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(80), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("available_at", sa.DateTime(), nullable=False),
            sa.Column("last_error", sa.String(500)),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        legacy.create_all(engine)

        now = datetime(2026, 7, 29, 12, 0, 0)
        with engine.begin() as connection:
            connection.execute(
                ProcessedMessage.__table__.insert(),
                {
                    "message_id": "wamid.legacy-migrated",
                    "created_at": None,
                },
            )
            connection.execute(
                Booking.__table__.insert(),
                [
                    {
                        "whatsapp_id": "919700000001",
                        "name": "Legacy Paid User",
                        "phone": "919700000001",
                        "state_name": "Maharashtra",
                        "district_name": "Pune",
                        "category": "Family",
                        "date": date(2026, 8, 1),
                        "slot_code": "10_11",
                        "slot_readable": "10:00 AM - 11:00 AM",
                        "amount": 499,
                        "status": BookingStatus.PAID,
                        "payment_token": "legacy-paid-token",
                        "payment_processed": True,
                        "created_at": None,
                    },
                    {
                        "whatsapp_id": "919700000002",
                        "name": "Legacy Completed User",
                        "phone": "919700000002",
                        "state_name": "Maharashtra",
                        "district_name": "Pune",
                        "category": "Family",
                        "date": date(2026, 7, 1),
                        "slot_code": "10_11",
                        "slot_readable": "10:00 AM - 11:00 AM",
                        "amount": 499,
                        "status": BookingStatus.COMPLETED,
                        "payment_token": "legacy-completed-token",
                        "payment_processed": True,
                        "created_at": now,
                    },
                ],
            )
            connection.execute(
                support.insert(),
                {
                    "request_type": "GENERAL",
                    "message": "Legacy private support message",
                    "status": "OPEN",
                    "priority": "NORMAL",
                    "created_at": now,
                    "updated_at": now,
                },
            )
            connection.execute(
                outbox.insert(),
                {
                    "kind": "payment_success_message",
                    "payload_json": '{"booking_id":1}',
                    "status": "COMPLETED",
                    "attempts": 1,
                    "available_at": now,
                    "created_at": now,
                    "updated_at": now,
                },
            )
    finally:
        engine.dispose()


def test_legacy_upgrade_adds_compatibility_and_backfills_safely(tmp_path):
    database_path = tmp_path / "legacy.db"
    _create_legacy_database(database_path)

    _upgrade(database_path)

    engine = sa.create_engine(_database_url(database_path))
    try:
        inspector = sa.inspect(engine)
        support_columns = {
            column["name"]
            for column in inspector.get_columns("support_requests")
        }
        assert {"resolution_note", "sla_due_at"}.issubset(support_columns)
        assert "ix_support_requests_sla_due_at" in {
            index["name"]
            for index in inspector.get_indexes("support_requests")
        }

        outbox_columns = {
            column["name"]
            for column in inspector.get_columns("outbox_jobs")
        }
        assert "dedupe_key" in outbox_columns
        dedupe_is_unique = any(
            constraint.get("column_names") == ["dedupe_key"]
            for constraint in inspector.get_unique_constraints("outbox_jobs")
        ) or any(
            index.get("unique")
            and index.get("column_names") == ["dedupe_key"]
            for index in inspector.get_indexes("outbox_jobs")
        )
        assert dedupe_is_unique is True

        with engine.connect() as connection:
            inbound = connection.execute(
                sa.text(
                    """
                    SELECT status, received_at, processed_at, expires_at
                    FROM inbound_message_events
                    WHERE message_id = 'wamid.legacy-migrated'
                    """
                )
            ).mappings().one()
            assert inbound["status"] == "DONE"
            assert inbound["received_at"] is not None
            assert inbound["processed_at"] is not None
            assert inbound["expires_at"] is not None
            assert (
                connection.execute(
                    sa.text(
                        """
                        SELECT COUNT(*)
                        FROM processed_messages
                        WHERE message_id = 'wamid.legacy-migrated'
                        """
                    )
                ).scalar_one()
                == 1
            )

            fulfillments = connection.execute(
                sa.text(
                    """
                    SELECT booking.status AS booking_status,
                           fulfillment.status AS fulfillment_status,
                           fulfillment.sla_due_at,
                           fulfillment.completed_at,
                           fulfillment.created_at
                    FROM booking_fulfillments AS fulfillment
                    JOIN bookings AS booking
                      ON booking.id = fulfillment.booking_id
                    ORDER BY booking.id
                    """
                )
            ).mappings().all()
            assert len(fulfillments) == 2
            paid = next(
                item for item in fulfillments if item["booking_status"] == "PAID"
            )
            completed = next(
                item
                for item in fulfillments
                if item["booking_status"] == "COMPLETED"
            )
            assert paid["fulfillment_status"] == "UNASSIGNED"
            assert paid["sla_due_at"] is not None
            assert paid["created_at"] is not None
            assert completed["fulfillment_status"] == "COMPLETED"
            assert completed["completed_at"] is not None
    finally:
        engine.dispose()
