import hashlib
import math
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db
from app.models import (
    Application,
    ApplicationStatus,
    AuditLog,
    Job,
    JobStatus,
    RefreshSession,
    Resume,
    Role,
    User,
    UserStatus,
)
from app.resume_processing import process_application
from app.schemas import (
    AuthOut,
    JobCreate,
    JobOut,
    JobUpdate,
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    ResendVerificationRequest,
    UserOut,
    UserStatusUpdate,
    VerifyEmailRequest,
)
from app.email_service import consume_verification, issue_email_verification
from app.security import (
    create_token,
    current_user,
    decode_token,
    hash_password,
    require_roles,
    verify_password,
)

router = APIRouter(prefix="/api/v1")
settings = get_settings()


def envelope(data=None, message: str = "Success") -> dict:
    return {"success": True, "message": message, "data": data}


def job_dict(job: Job, count: int | None = None) -> dict:
    data = JobOut.model_validate(job).model_dump(mode="json")
    data["application_count"] = count if count is not None else len(job.applications)
    return data


def insight_dict(application: Application) -> dict:
    return {
        "deterministic_score": application.deterministic_score,
        "ai_score": application.ai_score,
        "ai_status": application.ai_status,
        "ai_error": application.ai_error,
        "component_scores": application.component_scores or {},
        "ai_summary": application.ai_summary,
        "ai_strengths": application.ai_strengths or [],
        "ai_gaps": application.ai_gaps or [],
        "ai_recommendation": application.ai_recommendation,
        "ai_provider": application.ai_provider,
    }


def public_processing_error(application: Application) -> str | None:
    if not application.processing_error:
        return None
    if "insufficient extractable text" in application.processing_error.lower():
        return "This PDF appears scanned or contains too little selectable text. Upload a text-based PDF."
    return "We could not analyze this PDF. You can retry now or upload a different text-based PDF."


def audit(
    db: Session,
    actor: str | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
) -> None:
    db.add(AuditLog(actor_id=actor, action=action, target_type=target_type, target_id=target_id))


@router.post("/auth/register", status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        company_name=payload.company_name,
        email_verified=False,
    )
    db.add(user)
    db.flush()
    _, dev_code = issue_email_verification(db, user)
    audit(db, user.id, "auth.register", "user", user.id)
    db.commit()
    db.refresh(user)
    data = UserOut.model_validate(user).model_dump(mode="json")
    data["verification_required"] = True
    if settings.environment == "development" and not settings.smtp_host:
        data["dev_verification_code"] = dev_code
    return envelope(data, "Account created. Check your email to verify it.")


@router.post("/auth/verify-email")
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = consume_verification(db, email=str(payload.email) if payload.email else None, code=payload.code, token=payload.token)
    if not user:
        raise HTTPException(400, "Verification code or link is invalid or expired")
    user.last_login_at = datetime.now(UTC)
    auth = issue_tokens(user, db)
    audit(db, user.id, "auth.email_verified", "user", user.id)
    audit(db, user.id, "auth.auto_login_after_verification", "user", user.id)
    db.commit()
    return envelope(auth.model_dump(mode="json"), "Email verified and logged in")


@router.post("/auth/resend-verification")
def resend_verification(payload: ResendVerificationRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower().strip()))
    dev_code = None
    if user and not user.email_verified:
        _, dev_code = issue_email_verification(db, user)
        db.commit()
    data = {"dev_verification_code": dev_code} if settings.environment == "development" and not settings.smtp_host and dev_code else None
    return envelope(data, "If an unverified account exists, a new email has been sent")


def issue_tokens(user: User, db: Session) -> AuthOut:
    access, _ = create_token(user, "access", timedelta(minutes=settings.access_token_minutes))
    refresh, jti = create_token(user, "refresh", timedelta(days=settings.refresh_token_days))
    db.add(
        RefreshSession(
            id=jti,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    return AuthOut(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user))


@router.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(403, "Account is not active")
    if not user.email_verified:
        raise HTTPException(403, "Email verification required")
    user.last_login_at = datetime.now(UTC)
    auth = issue_tokens(user, db)
    audit(db, user.id, "auth.login", "user", user.id)
    db.commit()
    return envelope(auth.model_dump(mode="json"), "Logged in")


@router.post("/auth/refresh")
def refresh(payload: dict, db: Session = Depends(get_db)):
    token = payload.get("refresh_token", "")
    decoded = decode_token(token, "refresh")
    session = db.get(RefreshSession, decoded["jti"])
    user = db.get(User, decoded["sub"])
    if not session or session.revoked_at or not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(401, "Refresh session is invalid")
    session.revoked_at = datetime.now(UTC)
    auth = issue_tokens(user, db)
    db.commit()
    return envelope(auth.model_dump(mode="json"), "Token refreshed")


@router.post("/auth/logout")
def logout(payload: dict, db: Session = Depends(get_db)):
    decoded = decode_token(payload.get("refresh_token", ""), "refresh")
    session = db.get(RefreshSession, decoded["jti"])
    if session and not session.revoked_at:
        session.revoked_at = datetime.now(UTC)
        db.commit()
    return envelope(message="Logged out")


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return envelope(UserOut.model_validate(user).model_dump(mode="json"))


@router.patch("/profiles/me")
def update_profile(
    payload: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return envelope(UserOut.model_validate(user).model_dump(mode="json"), "Profile updated")


@router.get("/jobs")
def list_jobs(
    q: str = "",
    location: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = (
        select(Job)
        .options(joinedload(Job.employer))
        .where(Job.status == JobStatus.OPEN, Job.employer.has(status=UserStatus.ACTIVE))
    )
    if q:
        stmt = stmt.where(or_(Job.title.ilike(f"%{q}%"), Job.description.ilike(f"%{q}%")))
    if location:
        stmt = stmt.where(Job.location.ilike(f"%{location}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    jobs = (
        db.scalars(
            stmt.order_by(Job.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .unique()
        .all()
    )
    return envelope(
        {
            "items": [job_dict(job) for job in jobs],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": math.ceil(total / page_size) if total else 0,
        }
    )


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    job = db.scalar(select(Job).options(joinedload(Job.employer)).where(Job.id == job_id))
    if not job or job.status == JobStatus.DELETED:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.OPEN and not (user.role == Role.ADMIN or user.id == job.employer_id):
        raise HTTPException(404, "Job not found")
    return envelope(job_dict(job))


@router.get("/employer/jobs")
def employer_jobs(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_roles(Role.EMPLOYER)),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Job)
        .options(joinedload(Job.employer), joinedload(Job.applications))
        .where(Job.employer_id == user.id, Job.status != JobStatus.DELETED)
    )
    jobs = (
        db.scalars(
            stmt.order_by(Job.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .unique()
        .all()
    )
    total = (
        db.scalar(
            select(func.count(Job.id)).where(
                Job.employer_id == user.id, Job.status != JobStatus.DELETED
            )
        )
        or 0
    )
    return envelope(
        {
            "items": [job_dict(job) for job in jobs],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/employer/jobs", status_code=201)
def create_job(
    payload: JobCreate,
    user: User = Depends(require_roles(Role.EMPLOYER)),
    db: Session = Depends(get_db),
):
    job = Job(employer_id=user.id, **payload.model_dump())
    db.add(job)
    audit(db, user.id, "job.created", "job", job.id)
    db.commit()
    db.refresh(job)
    job.employer = user
    return envelope(job_dict(job, 0), "Job created")


def owned_job(job_id: str, user: User, db: Session) -> Job:
    job = db.scalar(
        select(Job)
        .options(joinedload(Job.employer), joinedload(Job.applications))
        .where(Job.id == job_id, Job.employer_id == user.id, Job.status != JobStatus.DELETED)
    )
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.patch("/employer/jobs/{job_id}")
def update_job(
    job_id: str,
    payload: JobUpdate,
    user: User = Depends(require_roles(Role.EMPLOYER)),
    db: Session = Depends(get_db),
):
    job = owned_job(job_id, user, db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, key, value)
    audit(db, user.id, "job.updated", "job", job.id)
    db.commit()
    db.refresh(job)
    return envelope(job_dict(job), "Job updated")


@router.delete("/employer/jobs/{job_id}")
def delete_job(
    job_id: str, user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)
):
    job = owned_job(job_id, user, db)
    job.status = JobStatus.DELETED
    audit(db, user.id, "job.deleted", "job", job.id)
    db.commit()
    return envelope(message="Job deleted")


@router.post("/jobs/{job_id}/applications", status_code=status.HTTP_202_ACCEPTED)
async def apply(
    job_id: str,
    background: BackgroundTasks,
    resume: UploadFile = File(...),
    user: User = Depends(require_roles(Role.APPLICANT)),
    db: Session = Depends(get_db),
):
    job = db.scalar(select(Job).where(Job.id == job_id, Job.status == JobStatus.OPEN))
    if not job:
        raise HTTPException(404, "Open job not found")
    if db.scalar(
        select(Application).where(Application.job_id == job_id, Application.applicant_id == user.id)
    ):
        raise HTTPException(409, "You have already applied to this job")
    content = await resume.read(settings.max_resume_size_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_resume_size_mb * 1024 * 1024:
        raise HTTPException(413, "Resume exceeds size limit")
    if (
        not resume.filename
        or not resume.filename.lower().endswith(".pdf")
        or not content.startswith(b"%PDF-")
    ):
        raise HTTPException(422, "A valid PDF resume is required")
    storage = settings.resume_storage_path.resolve()
    storage.mkdir(parents=True, exist_ok=True)
    key = storage / f"{uuid.uuid4()}.pdf"
    key.write_bytes(content)
    record = Resume(
        applicant_id=user.id,
        storage_key=str(key),
        original_filename=Path(resume.filename).name,
        mime_type="application/pdf",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    application = Application(job_id=job_id, applicant_id=user.id, resume=record)
    db.add(application)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        key.unlink(missing_ok=True)
        raise HTTPException(409, "You have already applied to this job") from exc
    db.refresh(application)
    background.add_task(process_application, application.id)
    return envelope(
        {"id": application.id, "status": application.status.value},
        "Application accepted for processing",
    )


@router.get("/applicant/applications")
def applicant_apps(
    user: User = Depends(require_roles(Role.APPLICANT)), db: Session = Depends(get_db)
):
    apps = (
        db.scalars(
            select(Application)
            .options(joinedload(Application.job).joinedload(Job.employer))
            .where(Application.applicant_id == user.id)
            .order_by(Application.created_at.desc())
        )
        .unique()
        .all()
    )
    return envelope(
        [
            {
                "id": a.id,
                "job_id": a.job_id,
                "applicant_id": a.applicant_id,
                "status": a.status.value,
                "final_score": a.final_score,
                "matched_skills": a.matched_skills,
                **insight_dict(a),
                "processing_error": public_processing_error(a),
                "created_at": a.created_at.isoformat(),
                "job": job_dict(a.job),
            }
            for a in apps
        ]
    )


@router.post("/applicant/applications/{application_id}/retry", status_code=202)
def retry_application_processing(
    application_id: str,
    background: BackgroundTasks,
    user: User = Depends(require_roles(Role.APPLICANT)),
    db: Session = Depends(get_db),
):
    application = db.scalar(
        select(Application).where(
            Application.id == application_id,
            Application.applicant_id == user.id,
        )
    )
    if not application:
        raise HTTPException(404, "Application not found")
    if application.status != ApplicationStatus.FAILED:
        raise HTTPException(409, "Only failed applications can be retried")
    application.status = ApplicationStatus.PROCESSING
    application.processing_error = None
    application.processed_at = None
    db.commit()
    background.add_task(process_application, application.id)
    return envelope(
        {"id": application.id, "status": application.status.value},
        "Resume analysis restarted",
    )


@router.post("/applicant/applications/{application_id}/retry-ai", status_code=202)
def retry_application_ai(
    application_id: str,
    background: BackgroundTasks,
    user: User = Depends(require_roles(Role.APPLICANT)),
    db: Session = Depends(get_db),
):
    application = db.scalar(
        select(Application).where(
            Application.id == application_id,
            Application.applicant_id == user.id,
        )
    )
    if not application:
        raise HTTPException(404, "Application not found")
    if application.status != ApplicationStatus.COMPLETED:
        raise HTTPException(409, "Resume processing must complete before AI can be retried")
    if not settings.gemini_enabled or not settings.gemini_api_key:
        raise HTTPException(503, "Gemini analysis is not configured")
    application.ai_status = "processing"
    application.ai_error = None
    db.commit()
    background.add_task(process_application, application.id, True)
    return envelope({"id": application.id, "ai_status": "processing"}, "Gemini analysis restarted")


@router.get("/employer/jobs/{job_id}/applications")
def ranked_apps(
    job_id: str, user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)
):
    owned_job(job_id, user, db)
    apps = (
        db.scalars(
            select(Application)
            .options(joinedload(Application.applicant))
            .where(Application.job_id == job_id)
            .order_by(Application.final_score.desc().nullslast(), Application.created_at)
        )
        .unique()
        .all()
    )
    return envelope(
        [
            {
                "id": a.id,
                "status": a.status.value,
                "final_score": a.final_score,
                "matched_skills": a.matched_skills,
                **insight_dict(a),
                "created_at": a.created_at.isoformat(),
                "applicant": UserOut.model_validate(a.applicant).model_dump(mode="json"),
            }
            for a in apps
        ]
    )


@router.get("/employer/applications/{application_id}/resume")
def download_resume(
    application_id: str,
    user: User = Depends(require_roles(Role.EMPLOYER)),
    db: Session = Depends(get_db),
):
    app = db.scalar(
        select(Application)
        .options(joinedload(Application.job), joinedload(Application.resume))
        .where(Application.id == application_id)
    )
    if not app or app.job.employer_id != user.id:
        raise HTTPException(404, "Application not found")
    audit(db, user.id, "resume.downloaded", "application", app.id)
    db.commit()
    return FileResponse(
        app.resume.storage_key, media_type="application/pdf", filename=app.resume.original_filename
    )


@router.get("/employer/dashboard")
def employer_dashboard(
    user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)
):
    jobs = db.scalars(
        select(Job).where(Job.employer_id == user.id, Job.status != JobStatus.DELETED)
    ).all()
    job_ids = [job.id for job in jobs]
    apps = (
        db.scalars(
            select(Application)
            .options(joinedload(Application.applicant))
            .where(Application.job_id.in_(job_ids))
        )
        .unique()
        .all()
        if job_ids
        else []
    )
    completed = [a for a in apps if a.final_score is not None]
    top = sorted(completed, key=lambda a: a.final_score or 0, reverse=True)[:5]
    return envelope(
        {
            "active_jobs": sum(j.status == JobStatus.OPEN for j in jobs),
            "total_jobs": len(jobs),
            "total_applicants": len(apps),
            "average_score": round(sum(a.final_score or 0 for a in completed) / len(completed), 1)
            if completed
            else 0,
            "recent_jobs": [job_dict(j) for j in jobs[:5]],
            "top_applicants": [
                {"name": a.applicant.full_name, "score": a.final_score, "job_id": a.job_id}
                for a in top
            ],
        }
    )


@router.get("/admin/dashboard")
def admin_dashboard(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return envelope(
        {
            "total_users": db.scalar(
                select(func.count(User.id)).where(User.status != UserStatus.DELETED)
            )
            or 0,
            "employers": db.scalar(
                select(func.count(User.id)).where(
                    User.role == Role.EMPLOYER, User.status != UserStatus.DELETED
                )
            )
            or 0,
            "applicants": db.scalar(
                select(func.count(User.id)).where(
                    User.role == Role.APPLICANT, User.status != UserStatus.DELETED
                )
            )
            or 0,
            "jobs": db.scalar(select(func.count(Job.id)).where(Job.status != JobStatus.DELETED))
            or 0,
            "resumes_processed": db.scalar(
                select(func.count(Application.id)).where(
                    Application.status == ApplicationStatus.COMPLETED
                )
            )
            or 0,
        }
    )


@router.get("/admin/users")
def admin_users(
    q: str = "", user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)
):
    stmt = select(User).where(User.role != Role.ADMIN, User.status != UserStatus.DELETED)
    if q:
        stmt = stmt.where(or_(User.full_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    users = db.scalars(stmt.order_by(User.created_at.desc())).all()
    return envelope([UserOut.model_validate(item).model_dump(mode="json") for item in users])


@router.patch("/admin/users/{user_id}/status")
def set_status(
    user_id: str,
    payload: UserStatusUpdate,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target or target.role == Role.ADMIN:
        raise HTTPException(404, "User not found")
    if payload.status not in {UserStatus.ACTIVE, UserStatus.SUSPENDED}:
        raise HTTPException(422, "Use delete endpoint for deletion")
    target.status = payload.status
    if payload.status == UserStatus.SUSPENDED:
        now = datetime.now(UTC)
        for session in db.scalars(
            select(RefreshSession).where(
                RefreshSession.user_id == target.id, RefreshSession.revoked_at.is_(None)
            )
        ).all():
            session.revoked_at = now
    audit(db, admin.id, f"user.{payload.status.value}", "user", target.id)
    db.commit()
    return envelope(UserOut.model_validate(target).model_dump(mode="json"), "User status updated")


@router.get("/admin/jobs")
def admin_jobs(admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    jobs = (
        db.scalars(
            select(Job)
            .options(joinedload(Job.employer), joinedload(Job.applications))
            .where(Job.status != JobStatus.DELETED)
            .order_by(Job.created_at.desc())
        )
        .unique()
        .all()
    )
    return envelope([job_dict(job) for job in jobs])


@router.delete("/admin/jobs/{job_id}")
def moderate_job(
    job_id: str, admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)
):
    job = db.get(Job, job_id)
    if not job or job.status == JobStatus.DELETED:
        raise HTTPException(404, "Job not found")
    job.status = JobStatus.DELETED
    audit(db, admin.id, "job.moderated", "job", job.id)
    db.commit()
    return envelope(message="Job removed")
