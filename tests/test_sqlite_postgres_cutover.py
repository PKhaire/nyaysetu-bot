from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from db import Base, EXPECTED_SCHEMA_REVISION
from jobs import migrate_sqlite_to_postgres as cutover
from models import (
    Advocate,
    Booking,
    BookingFulfillment,
    BookingStatus,
    User,
    UserConsent,
)


def _engine() -> Engine:
    return sa.create_engine("sqlite://")


def _current_empty_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        connection.execute(
            sa.text(
                "INSERT INTO alembic_version (version_num) "
                "VALUES (:revision)"
            ),
            {"revision": EXPECTED_SCHEMA_REVISION},
        )


def _seed_related_rows(engine: Engine) -> datetime:
    created_at = datetime(2026, 7, 29, 11, 12, 13)
    with engine.begin() as connection:
        connection.execute(
            User.__table__.insert(),
            {
                "id": 41,
                "whatsapp_id": "919700000001",
                "language": "English",
                "name": "Migration Test",
                "created_at": created_at,
            },
        )
        connection.execute(
            UserConsent.__table__.insert(),
            {
                "id": 51,
                "user_id": 41,
                "purpose": "AI",
                "policy_version": "test-v1",
                "granted": True,
                "source": "whatsapp",
                "consented_at": created_at,
            },
        )
        connection.execute(
            Advocate.__table__.insert(),
            {
                "id": 61,
                "name": "Advocate Test",
                "email": "test@example.invalid",
                "category": "Family",
                "district": "Pune",
                "active": True,
            },
        )
        connection.execute(
            Booking.__table__.insert(),
            {
                "id": 71,
                "whatsapp_id": "919700000001",
                "name": "Migration Test",
                "phone": "919700000001",
                "state_name": "Maharashtra",
                "district_name": "Pune",
                "category": "Family",
                "date": date(2026, 8, 4),
                "slot_code": "10_11",
                "slot_readable": "10:00 AM - 11:00 AM",
                "amount": 499,
                "status": BookingStatus.PAID,
                "payment_processed": True,
                "created_at": created_at,
            },
        )
        connection.execute(
            BookingFulfillment.__table__.insert(),
            {
                "id": 81,
                "booking_id": 71,
                "status": "ASSIGNED",
                "advocate_id": 61,
                "created_at": created_at,
                "updated_at": created_at,
            },
        )
    return created_at


def _counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            table.name: int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(table)
                ).scalar_one()
            )
            for table in cutover.application_tables()
        }


def test_application_table_plan_is_complete_fk_safe_and_excludes_alembic():
    names = [table.name for table in cutover.application_tables()]

    assert set(names) == set(Base.metadata.tables)
    assert "alembic_version" not in names
    assert names.index("users") < names.index("user_consents")
    assert names.index("bookings") < names.index("booking_fulfillments")
    assert names.index("advocates") < names.index("booking_fulfillments")


def test_preflight_reports_counts_and_does_not_mutate_target():
    source = _engine()
    target = _engine()
    _current_empty_schema(source)
    _current_empty_schema(target)
    _seed_related_rows(source)

    try:
        report = cutover.run_cutover(
            source,
            target,
            _allow_non_postgresql_target_for_tests=True,
        )
        assert report["status"] == "ready"
        assert report["mode"] == "preflight"
        assert report["counts"]["users"] == 1
        assert report["counts"]["booking_fulfillments"] == 1
        assert report["total_rows"] == 5
        assert all(value == 0 for value in _counts(target).values())
    finally:
        source.dispose()
        target.dispose()


def test_batched_copy_preserves_ids_timestamps_and_foreign_keys():
    source = _engine()
    target = _engine()
    _current_empty_schema(source)
    _current_empty_schema(target)
    expected_created_at = _seed_related_rows(source)

    try:
        report = cutover.run_cutover(
            source,
            target,
            execute=True,
            batch_size=1,
            _allow_non_postgresql_target_for_tests=True,
        )
        assert report["status"] == "completed"
        assert _counts(target) == _counts(source)

        with target.connect() as connection:
            copied_user = connection.execute(
                sa.select(User.__table__).where(User.id == 41)
            ).mappings().one()
            copied_fulfillment = connection.execute(
                sa.select(BookingFulfillment.__table__).where(
                    BookingFulfillment.id == 81
                )
            ).mappings().one()

        assert copied_user["created_at"] == expected_created_at
        assert copied_user["whatsapp_id"] == "919700000001"
        assert copied_fulfillment["booking_id"] == 71
        assert copied_fulfillment["advocate_id"] == 61
    finally:
        source.dispose()
        target.dispose()


def test_nonempty_target_is_rejected_without_writing_more_rows():
    source = _engine()
    target = _engine()
    _current_empty_schema(source)
    _current_empty_schema(target)
    _seed_related_rows(source)
    with target.begin() as connection:
        connection.execute(
            Advocate.__table__.insert(),
            {
                "id": 999,
                "name": "Existing",
                "email": "existing@example.invalid",
                "category": "Family",
                "district": "Pune",
                "active": True,
            },
        )

    try:
        with pytest.raises(
            cutover.CutoverError,
            match="target_application_tables_not_empty",
        ):
            cutover.run_cutover(
                source,
                target,
                execute=True,
                _allow_non_postgresql_target_for_tests=True,
            )
        counts = _counts(target)
        assert counts["advocates"] == 1
        assert sum(counts.values()) == 1
    finally:
        source.dispose()
        target.dispose()


def test_copy_failure_rolls_back_every_preceding_table():
    source = _engine()
    target = _engine()
    _current_empty_schema(source)
    _current_empty_schema(target)
    with source.begin() as connection:
        connection.execute(
            Advocate.__table__.insert(),
            {
                "id": 1,
                "name": "Copied Before Failure",
                "email": "rollback@example.invalid",
                "category": "Family",
                "district": "Pune",
                "active": True,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO bookings (
                    id, whatsapp_id, name, phone, state_name, district_name,
                    category, date, slot_readable, amount, status,
                    payment_processed
                ) VALUES (
                    1, '919700000009', 'Invalid Enum', '919700000009',
                    'Maharashtra', 'Pune', 'Family', '2026-08-04',
                    '10:00 AM - 11:00 AM', 499, 'NOT_A_STATUS', 0
                )
                """
            )
        )

    try:
        with pytest.raises(
            cutover.CutoverError,
            match="cutover_operation_failed",
        ):
            cutover.run_cutover(
                source,
                target,
                execute=True,
                batch_size=1,
                _allow_non_postgresql_target_for_tests=True,
            )
        assert all(value == 0 for value in _counts(target).values())
    finally:
        source.dispose()
        target.dispose()


def test_stamped_but_incomplete_source_schema_is_rejected():
    source = _engine()
    target = _engine()
    _current_empty_schema(target)
    with source.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        connection.execute(
            sa.text(
                "INSERT INTO alembic_version (version_num) "
                "VALUES (:revision)"
            ),
            {"revision": EXPECTED_SCHEMA_REVISION},
        )

    try:
        with pytest.raises(
            cutover.CutoverError,
            match="source_schema_tables_incomplete",
        ):
            cutover.run_cutover(
                source,
                target,
                _allow_non_postgresql_target_for_tests=True,
            )
    finally:
        source.dispose()
        target.dispose()


def _file_database(path: Path) -> Engine:
    return sa.create_engine(f"sqlite:///{path.resolve().as_posix()}")


def test_source_file_engine_is_immutable_and_cli_rejects_sqlite_target(
    tmp_path,
    capsys,
    monkeypatch,
):
    source_path = tmp_path / "frozen-source.db"
    writable = _file_database(source_path)
    _current_empty_schema(writable)
    writable.dispose()

    readonly = cutover._readonly_sqlite_engine(source_path.resolve())
    try:
        with readonly.begin() as connection:
            with pytest.raises(sa.exc.OperationalError):
                connection.execute(
                    Advocate.__table__.insert(),
                    {
                        "name": "Must Fail",
                        "email": "readonly@example.invalid",
                        "category": "Family",
                        "district": "Pune",
                        "active": True,
                    },
                )
    finally:
        readonly.dispose()

    monkeypatch.setenv(
        cutover.TARGET_POSTGRESQL_URL_ENV,
        f"sqlite:///{tmp_path / 'target.db'}",
    )
    exit_code = cutover.main(
        [
            "--source-sqlite",
            str(source_path),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output == {
        "counts": {},
        "error": "target_must_be_postgresql",
        "mode": "preflight",
        "status": "failed",
    }
    assert str(source_path) not in json.dumps(output)


def test_wrong_confirmation_fails_before_connecting(
    tmp_path,
    capsys,
    monkeypatch,
):
    source_path = tmp_path / "unused.db"
    source_path.touch()
    monkeypatch.setenv(
        cutover.TARGET_POSTGRESQL_URL_ENV,
        "postgresql://user:secret@example.invalid/nyaysetu",
    )

    exit_code = cutover.main(
        [
            "--source-sqlite",
            str(source_path),
            "--confirm-import",
            "yes",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["error"] == "confirmation_mismatch"
    assert "secret" not in json.dumps(output)


def test_fixed_target_url_environment_value_is_never_printed(
    tmp_path,
    capsys,
    monkeypatch,
):
    source_path = tmp_path / "frozen-source.db"
    writable = _file_database(source_path)
    _current_empty_schema(writable)
    writable.dispose()
    monkeypatch.setenv(
        cutover.TARGET_POSTGRESQL_URL_ENV,
        "sqlite:///secret-target-name.db",
    )

    exit_code = cutover.main(
        [
            "--source-sqlite",
            str(source_path),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["error"] == "target_must_be_postgresql"
    assert "secret-target-name" not in json.dumps(output)


def test_target_requires_remote_managed_credentials():
    for url in (
        "postgresql:///nyaysetu",
        "postgresql://db.example.invalid/nyaysetu",
        "postgresql://user@db.example.invalid/nyaysetu",
    ):
        with pytest.raises(
            cutover.CutoverError,
            match="target_managed_credentials_required",
        ):
            cutover._postgresql_url(url)

    parsed = cutover._postgresql_url(
        "postgresql://user:secret@db.example.invalid/nyaysetu"
    )
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.host == "db.example.invalid"


def test_cli_rejects_credential_url_process_argument(tmp_path, capsys):
    source_path = tmp_path / "unused.db"
    source_path.touch()

    exit_code = cutover.main(
        [
            "--source-sqlite",
            str(source_path),
            "--target-postgresql-url",
            "postgresql://user:secret@example.invalid/nyaysetu",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["error"] == "invalid_arguments"
    assert "secret" not in json.dumps(output)


def test_cli_never_falls_back_to_application_database_url(
    tmp_path,
    capsys,
    monkeypatch,
):
    source_path = tmp_path / "frozen-source.db"
    source_path.touch()
    monkeypatch.delenv(cutover.TARGET_POSTGRESQL_URL_ENV, raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://app-user:app-secret@app-db.invalid/nyaysetu",
    )

    exit_code = cutover.main(
        ["--source-sqlite", str(source_path)]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["error"] == "target_postgresql_url_env_missing"
    assert "app-secret" not in json.dumps(output)
