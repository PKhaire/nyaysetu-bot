"""Database engine, sessions, and health helpers."""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import (
    AUTO_CREATE_SCHEMA,
    DATABASE_URL as CONFIG_DATABASE_URL,
    DB_CONNECT_TIMEOUT_SECONDS,
    DB_MAX_OVERFLOW,
    DB_POOL_PRE_PING,
    DB_POOL_RECYCLE_SECONDS,
    DB_POOL_SIZE,
    SQLITE_BUSY_TIMEOUT_SECONDS,
    normalize_database_url,
)


logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nyaysetu.db")
EXPECTED_SCHEMA_REVISION = "20260819_01"


def _resolved_database_url(raw_url: str) -> URL:
    """Normalize PostgreSQL drivers and anchor relative SQLite files."""

    configured = normalize_database_url(raw_url or f"sqlite:///{DB_PATH}")
    url = make_url(configured)

    if url.get_backend_name() != "sqlite":
        return url

    database = url.database
    if not database or database == ":memory:":
        return url

    if not os.path.isabs(database):
        database = os.path.abspath(os.path.join(BASE_DIR, database))
        url = url.set(database=database)
    return url


_engine_url = _resolved_database_url(CONFIG_DATABASE_URL)
# Compatibility/debug value only; never expose database credentials through a
# module-level string or an accidental log statement.
DATABASE_URL = _engine_url.render_as_string(hide_password=True)
_is_sqlite = _engine_url.get_backend_name() == "sqlite"

_engine_options: dict[str, Any] = {
    "pool_pre_ping": DB_POOL_PRE_PING,
}

if _is_sqlite:
    _engine_options["connect_args"] = {
        "check_same_thread": False,
        "timeout": SQLITE_BUSY_TIMEOUT_SECONDS,
    }
else:
    _engine_options.update(
        {
            "pool_size": DB_POOL_SIZE,
            "max_overflow": DB_MAX_OVERFLOW,
            "pool_recycle": DB_POOL_RECYCLE_SECONDS,
            "connect_args": {
                "connect_timeout": DB_CONNECT_TIMEOUT_SECONDS,
            },
        }
    )

engine = create_engine(_engine_url, **_engine_options)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection: Any, _connection_record: Any) -> None:
        """Improve SQLite correctness while it is used as a local fallback."""

        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(
                f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_SECONDS * 1000}"
            )
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide one commit/rollback/close boundary for database work."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_db_health() -> bool:
    """Return whether the configured database can execute a trivial query."""

    try:
        with engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1
    except SQLAlchemyError:
        logger.warning("Database health check failed", exc_info=True)
        return False


def get_db_health() -> dict[str, object]:
    """Return a small, credential-free health payload for a readiness route."""

    started = time.monotonic()
    healthy = check_db_health()
    return {
        "ok": healthy,
        "backend": engine.url.get_backend_name(),
        "latency_ms": round((time.monotonic() - started) * 1000, 2),
    }


def get_schema_revision() -> str | None:
    """Return the applied Alembic revision without leaking connection details."""

    try:
        with engine.connect() as connection:
            table_exists = connection.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_name = 'alembic_version'
                    """
                )
            ).first() if engine.url.get_backend_name() != "sqlite" else None

            if engine.url.get_backend_name() == "sqlite":
                table_exists = connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM sqlite_master
                        WHERE type = 'table' AND name = 'alembic_version'
                        """
                    )
                ).first()

            if not table_exists:
                return None
            value = connection.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar()
            return str(value) if value else None
    except SQLAlchemyError:
        logger.warning("Unable to read database schema revision", exc_info=True)
        return None


def schema_is_current() -> bool:
    return get_schema_revision() == EXPECTED_SCHEMA_REVISION


def init_db() -> None:
    """Register models and create missing tables.

    ``create_all`` remains for compatibility and local development. Production
    schema evolution should be performed through migrations.
    """

    if not AUTO_CREATE_SCHEMA:
        raise RuntimeError(
            "Automatic schema creation is disabled; run 'alembic upgrade head'"
        )

    import models  # noqa: F401  # registers models with Base
    Base.metadata.create_all(bind=engine)
