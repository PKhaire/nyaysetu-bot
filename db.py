# db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    """Reusable DB session generator."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all():
    import models  # ensures table registration
    Base.metadata.create_all(bind=engine)
