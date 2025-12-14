# db.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import Base

DATABASE_URL = "sqlite:///./nyaysetu.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------- Migration helpers ----------

def ensure_schema_version(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        )
    """))

    result = conn.execute(text("SELECT COUNT(*) FROM schema_version")).scalar()
    if result == 0:
        conn.execute(text("INSERT INTO schema_version (version) VALUES (1)"))


def migrate_v1_to_v2(conn):
    """
    Adds location fields safely (idempotent)
    """
    columns = [
        row[1] for row in conn.execute(text("PRAGMA table_info(users)"))
    ]

    if "state_name" not in columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN state_name TEXT"))

    if "district_name" not in columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN district_name TEXT"))

    if "language" not in columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN language TEXT"))


def run_migrations():
    with engine.begin() as conn:
        ensure_schema_version(conn)

        version = conn.execute(
            text("SELECT version FROM schema_version")
        ).scalar()

        if version == 1:
            migrate_v1_to_v2(conn)
            conn.execute(text("UPDATE schema_version SET version = 2"))


# ---------- Init entrypoint ----------

def init_db():
    Base.metadata.create_all(bind=engine)
    run_migrations()
