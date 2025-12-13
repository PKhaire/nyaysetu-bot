# db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base

# SQLite DB path (Render-safe)
DB_PATH = os.getenv("SQLITE_PATH", "nyaysetu.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def create_all():
    """
    Creates all tables.
    Call ONCE at app startup.
    """
    Base.metadata.create_all(bind=engine)
