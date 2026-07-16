import uuid
import datetime as dt
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .db import Base


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


class ReferenceAsset(Base):
    """Style guide / approved exemplar images a studio uploads before generation starts."""
    __tablename__ = "reference_assets"

    id = Column(String, primary_key=True, default=gen_id)
    studio_id = Column(String, index=True, nullable=False)
    label = Column(String, nullable=False)          # e.g. "style_guide" or "exemplar_engineer_01"
    b2_url = Column(String, nullable=False)
    embedding_json = Column(Text, nullable=True)     # cached embedding for duplicate checks
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class Job(Base):
    """One creative request, e.g. 'female cyberpunk engineer, yellow safety jacket'."""
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=gen_id)
    studio_id = Column(String, index=True, nullable=False)
    original_prompt = Column(Text, nullable=False)
    status = Column(String, default="in_progress")   # in_progress | approved | needs_human_review
    final_attempt_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    attempts = relationship("Attempt", back_populates="job", order_by="Attempt.attempt_number")


class Attempt(Base):
    """One Genblaze run within a job. attempt_number 1..MAX_RETRY_ATTEMPTS."""
    __tablename__ = "attempts"

    id = Column(String, primary_key=True, default=gen_id)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)

    prompt_used = Column(Text, nullable=False)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)

    genblaze_run_id = Column(String, nullable=True)
    genblaze_parent_run_id = Column(String, nullable=True)
    asset_b2_url = Column(String, nullable=True)
    manifest_b2_url = Column(String, nullable=True)
    asset_sha256 = Column(String, nullable=True)

    style_check_passed = Column(Boolean, nullable=True)
    style_check_reason = Column(Text, nullable=True)
    duplicate_check_passed = Column(Boolean, nullable=True)
    duplicate_check_similarity = Column(Float, nullable=True)
    duplicate_check_matched_asset_id = Column(String, nullable=True)

    final_status = Column(String, nullable=True)     # approved | rejected | error
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    job = relationship("Job", back_populates="attempts")
