import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

# ============================================================
# DATABASE CONFIGURATION (ABSOLUTE PATH – FIXED)
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nyaysetu.db")

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ============================================================
# DEBUG (SAFE – REMOVE LATER IF YOU WANT)
# ============================================================

print("✅ SQLite DB FILE IN USE:", engine.url.database)

# ============================================================
# INIT ENTRYPOINT
# ============================================================

def init_db():
    """
    Creates all tables defined in models.py
    Safe to call multiple times.
    No migration. No data loss.
    """
    Base.metadata.create_all(bind=engine)
