# db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DATABASE_URL

# Create engine
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()

def create_all():
    # import models lazily to avoid circular imports
    from models import User, Booking, Rating  # noqa: F401
    Base.metadata.create_all(bind=engine)

# get_db generator for optional usage
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
