import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(enum.StrEnum):
    ADMIN = "admin"
    EMPLOYER = "employer"
    APPLICANT = "applicant"


class UserStatus(enum.StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class JobStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    DELETED = "deleted"


class ApplicationStatus(enum.StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    WITHDRAWN = "withdrawn"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), default=UserStatus.ACTIVE, index=True
    )
    company_name: Mapped[str | None] = mapped_column(String(160))
    location: Mapped[str | None] = mapped_column(String(160))
    headline: Mapped[str | None] = mapped_column(String(180))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verified: Mapped[bool] = mapped_column(default=False, index=True)
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="employer", cascade="all, delete-orphan"
    )
    applications: Mapped[list["Application"]] = relationship(back_populates="applicant")


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(180), index=True)
    description: Mapped[str] = mapped_column(Text)
    required_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.OPEN, index=True)
    location: Mapped[str | None] = mapped_column(String(160))
    employment_type: Mapped[str | None] = mapped_column(String(80))
    experience_level: Mapped[str | None] = mapped_column(String(80))
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    employer: Mapped[User] = relationship(back_populates="jobs")
    applications: Mapped[list["Application"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    __table_args__ = (Index("ix_jobs_employer_status", "employer_id", "status"),)


class Resume(TimestampMixin, Base):
    __tablename__ = "resumes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    applicant_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text)


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    applicant_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id"))
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.PROCESSING, index=True
    )
    deterministic_score: Mapped[float | None] = mapped_column(Float)
    ai_score: Mapped[float | None] = mapped_column(Float)
    ai_status: Mapped[str] = mapped_column(String(24), default="pending")
    ai_error: Mapped[str | None] = mapped_column(String(500))
    final_score: Mapped[float | None] = mapped_column(Float, index=True)
    matched_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    component_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_strengths: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_gaps: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_recommendation: Mapped[str | None] = mapped_column(String(40))
    ai_provider: Mapped[str | None] = mapped_column(String(80))
    processing_error: Mapped[str | None] = mapped_column(String(500))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job: Mapped[Job] = relationship(back_populates="applications")
    applicant: Mapped[User] = relationship(back_populates="applications")
    resume: Mapped[Resume] = relationship()
    __table_args__ = (
        UniqueConstraint("job_id", "applicant_id", name="uq_application_job_applicant"),
        Index("ix_applications_job_score", "job_id", "final_score"),
    )


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailVerification(Base):
    __tablename__ = "email_verifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str | None] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(36))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
