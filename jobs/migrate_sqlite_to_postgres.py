"""One-shot, fail-closed migration from a frozen SQLite copy to PostgreSQL.

This command deliberately never reads the application's ``DATABASE_URL``.
The target must be supplied through the dedicated
``NYAYSETU_CUTOVER_TARGET_URL`` environment variable so credentials cannot
leak through shell history or process arguments. The SQLite source is opened
read-only, and importing requires the exact confirmation phrase exposed by
``--help``. Running without that phrase performs preflight checks only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from contextlib import suppress
from pathlib import Path
from typing import Callable, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine, URL, make_url

from db import Base, EXPECTED_SCHEMA_REVISION
import models  # noqa: F401  # register every application table


IMPORT_CONFIRMATION = "IMPORT_SQLITE_COPY_INTO_EMPTY_POSTGRESQL"
TARGET_POSTGRESQL_URL_ENV = "NYAYSETU_CUTOVER_TARGET_URL"
DEFAULT_BATCH_SIZE = 500
MAX_BATCH_SIZE = 5_000
_SQLITE_SIDECAR_SUFFIXES = ("-journal", "-shm", "-wal")


class CutoverError(RuntimeError):
    """An operator-safe migration failure identified by a stable code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _JsonArgumentParser(argparse.ArgumentParser):
    """Keep invalid operational invocations free of supplied URL values."""

    def error(self, _message: str) -> None:
        raise CutoverError("invalid_arguments")


def application_tables() -> tuple[sa.Table, ...]:
    """Return all current application tables in SQLAlchemy's FK-safe order."""

    return tuple(Base.metadata.sorted_tables)


def _table_counts(connection: Connection) -> dict[str, int]:
    return {
        table.name: int(
            connection.execute(
                sa.select(sa.func.count()).select_from(table)
            ).scalar_one()
        )
        for table in application_tables()
    }


def _validate_revision(
    connection: Connection,
    *,
    role: str,
    expected_revision: str,
) -> None:
    inspector = sa.inspect(connection)
    if "alembic_version" not in inspector.get_table_names():
        raise CutoverError(f"{role}_schema_revision_missing")

    revisions = [
        str(value)
        for value in connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalars()
        if value
    ]
    if revisions != [expected_revision]:
        raise CutoverError(f"{role}_schema_revision_mismatch")


def _validate_schema_shape(connection: Connection, *, role: str) -> None:
    """Reject stamped-but-incomplete schemas before any row is read/copied."""

    inspector = sa.inspect(connection)
    actual_tables = set(inspector.get_table_names())
    expected_tables = {table.name for table in application_tables()}
    if not expected_tables.issubset(actual_tables):
        raise CutoverError(f"{role}_schema_tables_incomplete")

    for table in application_tables():
        actual_columns = {
            str(column["name"])
            for column in inspector.get_columns(table.name)
        }
        expected_columns = {column.name for column in table.columns}
        if actual_columns != expected_columns:
            raise CutoverError(f"{role}_schema_columns_mismatch")


def _validate_sqlite_integrity(connection: Connection) -> None:
    result = [
        str(value)
        for value in connection.exec_driver_sql("PRAGMA quick_check").scalars()
    ]
    if result != ["ok"]:
        raise CutoverError("source_integrity_check_failed")

    if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
        raise CutoverError("source_foreign_key_check_failed")


def preflight_databases(
    source: Connection,
    target: Connection,
    *,
    expected_revision: str = EXPECTED_SCHEMA_REVISION,
) -> dict[str, int]:
    """Validate both schemas and return source counts if the target is empty."""

    if source.dialect.name != "sqlite":
        raise CutoverError("source_must_be_sqlite")

    _validate_sqlite_integrity(source)
    _validate_revision(
        source,
        role="source",
        expected_revision=expected_revision,
    )
    _validate_schema_shape(source, role="source")
    _validate_revision(
        target,
        role="target",
        expected_revision=expected_revision,
    )
    _validate_schema_shape(target, role="target")

    source_counts = _table_counts(source)
    if any(_table_counts(target).values()):
        raise CutoverError("target_application_tables_not_empty")
    return source_counts


def _lock_postgresql_target(connection: Connection) -> None:
    """Prevent application writes between emptiness validation and commit."""

    connection.exec_driver_sql("SET LOCAL lock_timeout = '10s'")
    preparer = connection.dialect.identifier_preparer
    table_names = ", ".join(
        preparer.format_table(table) for table in application_tables()
    )
    connection.exec_driver_sql(
        f"LOCK TABLE {table_names} IN ACCESS EXCLUSIVE MODE"
    )


def copy_application_tables(
    source: Connection,
    target: Connection,
    *,
    expected_counts: Mapping[str, int],
    batch_size: int,
) -> dict[str, int]:
    """Copy every application row in bounded, deterministic batches."""

    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise CutoverError("batch_size_out_of_range")
    if any(_table_counts(target).values()):
        raise CutoverError("target_application_tables_not_empty")

    copied_counts: dict[str, int] = {}
    for table in application_tables():
        expected_count = int(expected_counts.get(table.name, -1))
        if expected_count < 0:
            raise CutoverError("source_counts_incomplete")

        order_columns = tuple(table.primary_key.columns)
        statement = sa.select(table)
        if order_columns:
            statement = statement.order_by(*order_columns)
        result = source.execution_options(
            stream_results=True,
            max_row_buffer=batch_size,
        ).execute(statement)

        copied = 0
        while True:
            rows = result.fetchmany(batch_size)
            if not rows:
                break
            payload = [
                {
                    column.name: row._mapping[column]
                    for column in table.columns
                }
                for row in rows
            ]
            target.execute(table.insert(), payload)
            copied += len(payload)

        if copied != expected_count:
            raise CutoverError("source_count_changed_during_copy")
        copied_counts[table.name] = copied

    return copied_counts


def _postgresql_sequence(
    connection: Connection,
    *,
    table: sa.Table,
    column: sa.Column,
) -> tuple[str, str] | None:
    formatted_table = connection.dialect.identifier_preparer.format_table(
        table
    )
    row = connection.execute(
        sa.text(
            """
            SELECT namespace.nspname, sequence.relname
            FROM pg_class AS sequence
            JOIN pg_namespace AS namespace
              ON namespace.oid = sequence.relnamespace
            WHERE sequence.oid = CAST(
                pg_get_serial_sequence(:table_name, :column_name)
                AS regclass
            )
            """
        ),
        {
            "table_name": formatted_table,
            "column_name": column.name,
        },
    ).one_or_none()
    if row is None:
        return None
    return str(row[0]), str(row[1])


def reset_postgresql_sequences(connection: Connection) -> None:
    """Transactionally restart every current serial/identity PK sequence."""

    if connection.dialect.name != "postgresql":
        return

    preparer = connection.dialect.identifier_preparer
    for table in application_tables():
        primary_key = tuple(table.primary_key.columns)
        if len(primary_key) != 1:
            continue
        column = primary_key[0]
        if not isinstance(column.type, sa.Integer):
            continue

        sequence = _postgresql_sequence(
            connection,
            table=table,
            column=column,
        )
        if sequence is None:
            raise CutoverError("target_primary_key_sequence_missing")

        maximum = connection.execute(
            sa.select(sa.func.max(column))
        ).scalar_one()
        restart_with = max(1, int(maximum) + 1) if maximum is not None else 1
        if restart_with > 2_147_483_647:
            raise CutoverError("target_primary_key_sequence_exhausted")

        schema_name, sequence_name = sequence
        qualified_sequence = (
            f"{preparer.quote(schema_name)}."
            f"{preparer.quote(sequence_name)}"
        )
        # ALTER SEQUENCE RESTART is transactional in PostgreSQL, unlike
        # setval(), so a later verification/commit failure remains reversible.
        connection.exec_driver_sql(
            f"ALTER SEQUENCE {qualified_sequence} "
            f"RESTART WITH {restart_with}"
        )


def run_cutover(
    source_engine: Engine,
    target_engine: Engine,
    *,
    execute: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    source_stability_guard: Callable[[], None] | None = None,
    _allow_non_postgresql_target_for_tests: bool = False,
) -> dict[str, object]:
    """Run preflight or an atomic import and return privacy-safe counts."""

    if source_engine.dialect.name != "sqlite":
        raise CutoverError("source_must_be_sqlite")
    if (
        target_engine.dialect.name != "postgresql"
        and not _allow_non_postgresql_target_for_tests
    ):
        raise CutoverError("target_must_be_postgresql")
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise CutoverError("batch_size_out_of_range")

    try:
        with source_engine.connect() as source:
            source_transaction = source.begin()
            try:
                with target_engine.connect() as target:
                    target_transaction = target.begin()
                    try:
                        if execute and target.dialect.name == "postgresql":
                            _lock_postgresql_target(target)

                        source_counts = preflight_databases(source, target)
                        if execute:
                            copied_counts = copy_application_tables(
                                source,
                                target,
                                expected_counts=source_counts,
                                batch_size=batch_size,
                            )
                            if _table_counts(source) != source_counts:
                                raise CutoverError(
                                    "source_count_changed_during_copy"
                                )
                            if _table_counts(target) != source_counts:
                                raise CutoverError(
                                    "target_count_verification_failed"
                                )
                            if copied_counts != source_counts:
                                raise CutoverError(
                                    "copy_count_verification_failed"
                                )
                            reset_postgresql_sequences(target)

                        if source_stability_guard is not None:
                            source_stability_guard()

                        if execute:
                            target_transaction.commit()
                        else:
                            target_transaction.rollback()
                    except Exception:
                        if target_transaction.is_active:
                            target_transaction.rollback()
                        raise
            finally:
                if source_transaction.is_active:
                    source_transaction.rollback()
    except CutoverError:
        raise
    except Exception as exc:
        raise CutoverError("cutover_operation_failed") from exc

    mode = "import" if execute else "preflight"
    status = "completed" if execute else "ready"
    return {
        "counts": source_counts,
        "mode": mode,
        "status": status,
        "total_rows": sum(source_counts.values()),
    }


def _source_path(value: str) -> Path:
    """Resolve one explicit SQLite file path/URL without using app config."""

    raw = value.strip()
    if not raw:
        raise CutoverError("source_sqlite_required")

    if raw.lower().startswith("sqlite"):
        try:
            url = make_url(raw)
        except (ValueError, sa.exc.ArgumentError) as exc:
            raise CutoverError("source_sqlite_invalid") from exc
        if (
            url.get_backend_name() != "sqlite"
            or not url.database
            or url.database == ":memory:"
            or url.host
            or url.username
            or url.password
            or url.port
            or url.query
        ):
            raise CutoverError("source_sqlite_file_required")
        candidate = Path(url.database).expanduser()
    else:
        if "://" in raw:
            raise CutoverError("source_sqlite_invalid")
        candidate = Path(raw).expanduser()

    if candidate.is_symlink():
        raise CutoverError("source_sqlite_symlink_rejected")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CutoverError("source_sqlite_file_unavailable") from exc
    if not resolved.is_file():
        raise CutoverError("source_sqlite_file_required")
    _assert_no_sqlite_sidecars(resolved)
    return resolved


def _assert_no_sqlite_sidecars(path: Path) -> None:
    if any(
        Path(f"{path}{suffix}").exists()
        for suffix in _SQLITE_SIDECAR_SUFFIXES
    ):
        raise CutoverError("source_sqlite_not_frozen")


def _source_fingerprint(path: Path) -> tuple[int, int, str]:
    try:
        stat = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as source_file:
            while chunk := source_file.read(4 * 1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise CutoverError("source_sqlite_file_unavailable") from exc
    return stat.st_size, stat.st_mtime_ns, digest.hexdigest()


def _readonly_sqlite_engine(path: Path) -> Engine:
    """Open a frozen SQLite artifact without creating journals or WAL files."""

    uri = f"{path.as_uri()}?mode=ro&immutable=1"

    def connect_read_only() -> sqlite3.Connection:
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    return sa.create_engine(
        "sqlite://",
        creator=connect_read_only,
        hide_parameters=True,
    )


def _postgresql_url(value: str) -> URL:
    raw = value.strip()
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql://", 1)
    try:
        url = make_url(raw)
    except (ValueError, sa.exc.ArgumentError) as exc:
        raise CutoverError("target_postgresql_invalid") from exc
    if url.get_backend_name() != "postgresql" or not url.database:
        raise CutoverError("target_must_be_postgresql")
    if not url.host or not url.username or not url.password:
        raise CutoverError("target_managed_credentials_required")
    return url.set(drivername="postgresql+psycopg")


def _target_engine(url: URL) -> Engine:
    return sa.create_engine(
        url,
        connect_args={"connect_timeout": 10},
        hide_parameters=True,
        pool_pre_ping=True,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(
        description=(
            "Preflight a frozen SQLite backup and an empty PostgreSQL schema; "
            "import only with the exact confirmation phrase. The target URL "
            f"must be set in {TARGET_POSTGRESQL_URL_ENV}; it is never "
            "accepted as a process argument."
        )
    )
    parser.add_argument(
        "--source-sqlite",
        required=True,
        help="Explicit frozen SQLite backup file or sqlite:/// URL.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows per insert batch (1-{MAX_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--confirm-import",
        help=(
            "Omit for dry-run. To import, pass exactly: "
            f"{IMPORT_CONFIRMATION}"
        ),
    )
    return parser


def _emit(report: Mapping[str, object]) -> None:
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    source_engine: Engine | None = None
    target_engine: Engine | None = None
    mode = "preflight"
    try:
        args = _build_parser().parse_args(argv)
        if (
            args.confirm_import is not None
            and args.confirm_import != IMPORT_CONFIRMATION
        ):
            raise CutoverError("confirmation_mismatch")
        execute = args.confirm_import == IMPORT_CONFIRMATION
        mode = "import" if execute else "preflight"

        if not 1 <= args.batch_size <= MAX_BATCH_SIZE:
            raise CutoverError("batch_size_out_of_range")
        path = _source_path(args.source_sqlite)
        raw_target_url = os.environ.get(TARGET_POSTGRESQL_URL_ENV, "").strip()
        if not raw_target_url:
            raise CutoverError("target_postgresql_url_env_missing")
        target_url = _postgresql_url(raw_target_url)
        initial_fingerprint = _source_fingerprint(path)

        def assert_source_stable() -> None:
            _assert_no_sqlite_sidecars(path)
            if _source_fingerprint(path) != initial_fingerprint:
                raise CutoverError("source_sqlite_changed")

        source_engine = _readonly_sqlite_engine(path)
        target_engine = _target_engine(target_url)
        report = run_cutover(
            source_engine,
            target_engine,
            execute=execute,
            batch_size=args.batch_size,
            source_stability_guard=assert_source_stable,
        )
        _emit(report)
        return 0
    except CutoverError as exc:
        _emit({"counts": {}, "error": exc.code, "mode": mode, "status": "failed"})
        return 2
    except (Exception, KeyboardInterrupt):
        _emit(
            {
                "counts": {},
                "error": "internal_error",
                "mode": mode,
                "status": "failed",
            }
        )
        return 2
    finally:
        if source_engine is not None:
            with suppress(Exception):
                source_engine.dispose()
        if target_engine is not None:
            with suppress(Exception):
                target_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
