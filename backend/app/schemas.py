from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

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
    # Input schemas remain strict EmailStr. Output must tolerate legacy local/test domains.
    email: str
    full_name: str
    role: Role
    status: UserStatus
    company_name: str | None
    location: str | None
    headline: str | None
    avatar_url: str | None = None
    phone: str | None = None
    bio: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    years_experience: int | None = None
    availability: str | None = None
    preferred_work_mode: str | None = None
    portfolio_url: str | None = None
    notice_period: str | None = None
    industry: str | None = None
    company_website: str | None = None
    company_size: str | None = None
    company_description: str | None = None
    founded_year: int | None = None
    email_verified: bool
    notification_preferences: dict[str, bool] = Field(default_factory=dict)
    created_at: datetime


class NotificationPreferencesUpdate(BaseModel):
    new_applications: bool | None = None
    application_status_changes: bool | None = None
    assignments: bool | None = None
    interviews_offers: bool | None = None
    ai_analysis_updates: bool | None = None
    weekly_summary: bool | None = None


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
    phone: str | None = Field(default=None, max_length=40)
    bio: str | None = Field(default=None, max_length=3000)
    website: str | None = Field(default=None, max_length=500)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    skills: list[str] | None = Field(default=None, max_length=100)
    languages: list[str] | None = Field(default=None, max_length=30)
    education: list[str] | None = Field(default=None, max_length=30)
    years_experience: int | None = Field(default=None, ge=0, le=80)
    availability: str | None = Field(default=None, max_length=80)
    preferred_work_mode: str | None = Field(default=None, max_length=40)
    portfolio_url: str | None = Field(default=None, max_length=500)
    notice_period: str | None = Field(default=None, max_length=80)
    industry: str | None = Field(default=None, max_length=120)
    company_website: str | None = Field(default=None, max_length=500)
    company_size: str | None = Field(default=None, max_length=40)
    company_description: str | None = Field(default=None, max_length=5000)
    founded_year: int | None = Field(default=None, ge=1800, le=2100)

    @field_validator("skills", "languages", "education")
    @classmethod
    def clean_lists(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return list(dict.fromkeys(item.strip() for item in values if item.strip()))


class ScorecardConfig(BaseModel):
    semantic: float = Field(default=15, ge=0, le=100)
    skills: float = Field(default=35, ge=0, le=100)
    experience: float = Field(default=25, ge=0, le=100)
    role_alignment: float = Field(default=15, ge=0, le=100)
    domain: float = Field(default=5, ge=0, le=100)
    education_certifications: float = Field(default=5, ge=0, le=100)

    @model_validator(mode="after")
    def weights_total_one_hundred(self):
        if abs(sum(self.model_dump().values()) - 100) > 0.01:
            raise ValueError("Scorecard weights must total 100")
        return self


class JobBase(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=20, max_length=20000)
    required_skills: list[str] = Field(min_length=1, max_length=50)
    scorecard: ScorecardConfig = Field(default_factory=ScorecardConfig)
    skill_priorities: dict[str, Literal["mandatory", "preferred", "optional"]] = Field(default_factory=dict)
    domain_keywords: list[str] = Field(default_factory=list, max_length=50)
    education_requirements: list[str] = Field(default_factory=list, max_length=20)
    certification_requirements: list[str] = Field(default_factory=list, max_length=20)
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
    scorecard: ScorecardConfig | None = None
    skill_priorities: dict[str, Literal["mandatory", "preferred", "optional"]] | None = None
    domain_keywords: list[str] | None = None
    education_requirements: list[str] | None = None
    certification_requirements: list[str] | None = None
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
    structured_profile: dict
    evidence_matrix: list[dict]
    analysis_version: str
    parser_version: str | None
    override_score: float | None
    override_reason: str | None
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


class AdminCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def strong_admin_password(cls, value: str) -> str:
        checks = (
            any(character.islower() for character in value),
            any(character.isupper() for character in value),
            any(character.isdigit() for character in value),
            any(not character.isalnum() for character in value),
        )
        if not all(checks):
            raise ValueError("Password must contain uppercase, lowercase, number, and special character")
        return value


class ScoreOverrideRequest(BaseModel):
    score: float = Field(ge=0, le=100)
    reason: str = Field(min_length=10, max_length=2000)


class TeamInviteRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "recruiter", "viewer"] = "recruiter"


class WorkspaceSwitchRequest(BaseModel):
    organization_id: str


class MembershipRoleUpdate(BaseModel):
    role: Literal["admin", "recruiter", "viewer"]


class StageCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    color: str = Field(default="#3157d5", pattern=r"^#[0-9a-fA-F]{6}$")
    category: Literal["active", "hired", "rejected"] = "active"


class StageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    position: int | None = Field(default=None, ge=0)


class CandidateMoveRequest(BaseModel):
    stage_id: str


class CandidateAssignRequest(BaseModel):
    user_id: str | None = None


class CandidateTagsRequest(BaseModel):
    tags: list[str] = Field(max_length=30)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip()[:40] for value in values if value.strip()))


class CandidateNoteRequest(BaseModel):
    body: str = Field(min_length=2, max_length=5000)


class Paginated(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
