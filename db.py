# db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nyaysetu.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def create_all():
    from models import Base as ModelsBase  # local import to avoid circular imports
    ModelsBase.metadata.create_all(bind=engine)

# Optional generator-style helper (useful with frameworks or dependency injection)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
