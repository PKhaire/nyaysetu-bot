import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ============================================================
# DATABASE CONFIGURATION
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

# ✅ Base defined ONLY here
Base = declarative_base()

print("✅ SQLite DB FILE IN USE:", engine.url.database)

def init_db():
    """
    Load models and create tables.
    """
    import models  # IMPORTANT: registers models with Base
    Base.metadata.create_all(bind=engine)
