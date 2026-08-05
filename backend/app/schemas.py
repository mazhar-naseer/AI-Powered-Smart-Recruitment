from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import ApplicationStatus, JobStatus, Role, UserStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role
    company_name: str | None = Field(default=None, max_length=160)

    @field_validator("role")
    @classmethod
    def disallow_admin(cls, value: Role) -> Role:
        if value == Role.ADMIN:
            raise ValueError("Admin registration is not allowed")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: str
    email: EmailStr
    full_name: str
    role: Role
    status: UserStatus
    company_name: str | None
    location: str | None
    headline: str | None
    email_verified: bool
    created_at: datetime


class AuthOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    company_name: str | None = Field(default=None, max_length=160)
    location: str | None = Field(default=None, max_length=160)
    headline: str | None = Field(default=None, max_length=180)


class JobBase(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=20, max_length=20000)
    required_skills: list[str] = Field(min_length=1, max_length=50)
    location: str | None = Field(default=None, max_length=160)
    employment_type: str | None = Field(default=None, max_length=80)
    experience_level: str | None = Field(default=None, max_length=80)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)

    @field_validator("required_skills")
    @classmethod
    def normalize_skills(cls, skills: list[str]) -> list[str]:
        result = list(dict.fromkeys(skill.strip() for skill in skills if skill.strip()))
        if not result:
            raise ValueError("At least one required skill is required")
        return result


class JobCreate(JobBase):
    status: JobStatus = JobStatus.OPEN


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=180)
    description: str | None = Field(default=None, min_length=20, max_length=20000)
    required_skills: list[str] | None = None
    status: JobStatus | None = None
    location: str | None = None
    employment_type: str | None = None
    experience_level: str | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)


class EmployerSummary(ORMModel):
    id: str
    full_name: str
    company_name: str | None


class JobOut(JobBase, ORMModel):
    id: str
    employer_id: str
    status: JobStatus
    created_at: datetime
    employer: EmployerSummary
    application_count: int = 0


class ApplicationOut(ORMModel):
    id: str
    job_id: str
    applicant_id: str
    status: ApplicationStatus
    final_score: float | None
    deterministic_score: float | None
    ai_score: float | None
    ai_status: str
    ai_error: str | None
    matched_skills: list[str]
    component_scores: dict
    ai_summary: str | None
    ai_strengths: list[str]
    ai_gaps: list[str]
    ai_recommendation: str | None
    ai_provider: str | None
    processing_error: str | None
    created_at: datetime
    job: JobOut | None = None
    applicant: UserOut | None = None


class VerifyEmailRequest(BaseModel):
    email: EmailStr | None = None
    code: str | None = Field(default=None, min_length=6, max_length=6)
    token: str | None = None


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class UserStatusUpdate(BaseModel):
    status: UserStatus


class Paginated(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
