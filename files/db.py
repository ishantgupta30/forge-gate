"""
Job/attempt tracking DB.

Genblaze itself is stateless — each Pipeline.run() call is self-contained
and returns a manifest. It has no concept of "job -> attempt 1, 2, 3 -> final
decision." This DB is what ties multiple Genblaze runs together under one
job_id so the Timeline UI has something to read from.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./forge_gate.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
