import hashlib
import math
import secrets
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
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db
from app.models import (
    Application,
    ApplicationStatus,
    AuditLog,
    CandidateTimeline,
    Job,
    JobStatus,
    RefreshSession,
    Resume,
    Role,
    ScoreOverride,
    User,
    UserStatus,
    PipelineStage,
    PasswordReset,
    Notification,
    OrganizationMembership,
)
from app.resume_processing import process_application
from app.schemas import (
    AdminCreate,
    AdminBootstrapRequest,
    AuthOut,
    JobCreate,
    JobOut,
    JobUpdate,
    LoginRequest,
    ProfileUpdate,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ScoreOverrideRequest,
    UserOut,
    UserStatusUpdate,
    VerifyEmailRequest,
)
from app.email_service import (
    consume_verification,
    email_provider_configured,
    issue_email_verification,
)
from app.security import (
    create_token,
    current_user,
    decode_token,
    hash_password,
    require_roles,
    verify_password,
)
from app.tenancy import create_workspace, ensure_membership, require_permission
from app.object_storage import avatar_media_type, avatar_storage, resume_storage
from app.background_jobs import queue_application_analysis, run_background_job
from app.logging_config import get_logger
from app.saas import enforce_limit, increment_usage
from app.notification_service import create_notification

router = APIRouter(prefix="/api/v1")
settings = get_settings()
logger = get_logger(__name__)


def dispatch_background(background: BackgroundTasks, job_id: str) -> None:
    if settings.inline_background_jobs:
        background.add_task(run_background_job, job_id)


def envelope(data=None, message: str = "Success") -> dict:
    return {"success": True, "message": message, "data": data}


def job_dict(job: Job, count: int | None = None) -> dict:
    data = JobOut.model_validate(job).model_dump(mode="json")
    if job.organization_id and job.organization:
        data["employer"]["company_name"] = job.organization.name
    data["application_count"] = count if count is not None else len(job.applications)
    return data


def insight_dict(application: Application) -> dict:
    return {
        "deterministic_score": application.deterministic_score,
        "ai_score": application.ai_score,
        "ai_status": application.ai_status,
        "ai_error": application.ai_error,
        "structured_profile": application.structured_profile or {},
        "evidence_matrix": application.evidence_matrix or [],
        "analysis_version": application.analysis_version,
        "parser_version": application.parser_version,
        "override_score": application.override_score,
        "override_reason": application.override_reason,
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
    organization_id = None
    if actor:
        actor_user = db.get(User, actor)
        organization_id = actor_user.active_organization_id if actor_user else None
    db.add(AuditLog(actor_id=actor, action=action, target_type=target_type, target_id=target_id, metadata_json={"organization_id": organization_id} if organization_id else {}))
    # Debug, not info: the endpoints that matter already log their own outcome in
    # domain terms, and every audited action would otherwise appear twice.
    logger.debug("Audit: %s by %s on %s %s", action, actor, target_type, target_id)


@router.post("/auth/register", status_code=201)   
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        logger.info("Registration rejected: %s is already in use", email)
        raise HTTPException(409, "An account with this email already exists")
    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        company_name=payload.company_name,
        email_verified=not settings.email_verification_enabled,
    )
    db.add(user)
    db.flush()
    if user.role == Role.EMPLOYER:
        create_workspace(db, user, payload.company_name)
    # With verification off no code is issued at all, so there is nothing to
    # send and nothing to consume: the account is active and login is the next
    # step. Keep the response keys stable so clients need no branching.
    if not settings.email_verification_enabled:
        audit(db, user.id, "auth.register", "user", user.id)
        db.commit()
        db.refresh(user)
        logger.info(
            "Registered %s %s with verification disabled; account is active", user.role.value, user.id
        )
        data = UserOut.model_validate(user).model_dump(mode="json")
        data["verification_required"] = False
        data["verification_email_sent"] = False
        return envelope(data, "Account created. You can log in now.")

    _, dev_code, delivered = issue_email_verification(db, user)
    audit(db, user.id, "auth.register", "user", user.id)
    db.commit()
    db.refresh(user)
    logger.info(
        "Registered %s %s pending verification (email_sent=%s)", user.role.value, user.id, delivered
    )
    data = UserOut.model_validate(user).model_dump(mode="json")
    data["verification_required"] = True
    data["verification_email_sent"] = delivered
    if settings.environment == "development" and not email_provider_configured():
        data["dev_verification_code"] = dev_code
    return envelope(
        data,
        "Account created. Check your email to verify it."
        if delivered
        else "Account created, but the verification email could not be sent. Request a new one.",
    )


@router.post("/auth/verify-email")
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = consume_verification(db, email=str(payload.email) if payload.email else None, code=payload.code, token=payload.token)
    if not user:
        # consume_verification already logged which check rejected it.
        raise HTTPException(400, "Verification code or link is invalid or expired")
    user.last_login_at = datetime.now(UTC)
    auth = issue_tokens(user, db)
    audit(db, user.id, "auth.email_verified", "user", user.id)
    audit(db, user.id, "auth.auto_login_after_verification", "user", user.id)
    db.commit()
    logger.info("User %s verified their email and was logged in", user.id)
    return envelope(auth.model_dump(mode="json"), "Email verified and logged in")


@router.post("/auth/resend-verification")
def resend_verification(payload: ResendVerificationRequest, db: Session = Depends(get_db)):
    if not settings.email_verification_enabled:
        logger.info("Resend refused: email verification is disabled")
        raise HTTPException(400, "Email verification is disabled. Log in with your password.")
    user = db.scalar(select(User).where(User.email == str(payload.email).lower().strip()))
    dev_code = None
    if user and not user.email_verified:
        _, dev_code, _ = issue_email_verification(db, user)
        db.commit()
        logger.info("Reissued a verification code for user %s", user.id)
    else:
        # The response is deliberately identical either way so the endpoint does
        # not reveal whether an account exists. The log records the difference.
        logger.info("Resend requested for an unknown or already-verified address")
    data = {"dev_verification_code": dev_code} if settings.environment == "development" and not email_provider_configured() and dev_code else None
    return envelope(data, "If an unverified account exists, a new email has been sent")


@router.post("/auth/forgot-password")
def forgot_password(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower().strip()))
    if user and user.status == UserStatus.ACTIVE:
        issue_password_reset(db, user)
        audit(db, user.id, "auth.password_reset_requested", "user", user.id)
        db.commit()
    return envelope(message="If an active account uses this email, a password reset link has been sent")


@router.post("/auth/reset-password")
def reset_password(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == hashlib.sha256(payload.token.encode()).hexdigest(), PasswordReset.consumed_at.is_(None)).order_by(PasswordReset.created_at.desc()))
    if not reset or reset.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(400, "Password reset link is invalid or expired")
    user = db.get(User, reset.user_id)
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(400, "Password reset link is invalid or expired")
    user.password_hash = hash_password(payload.password)
    reset.consumed_at = datetime.now(UTC)
    db.query(RefreshSession).filter(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)).update({RefreshSession.revoked_at: datetime.now(UTC)})
    audit(db, user.id, "auth.password_reset_completed", "user", user.id)
    db.commit()
    return envelope(message="Password reset successfully. You can now sign in.")


@router.post("/admin/bootstrap", status_code=201)
def bootstrap_admin(payload: AdminBootstrapRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.role == Role.ADMIN).limit(1)):
        raise HTTPException(409, "An administrator already exists. Sign in to the Control Center to manage administrators.")
    configured_token = settings.admin_bootstrap_token
    if not configured_token or not secrets.compare_digest(payload.bootstrap_token, configured_token):
        raise HTTPException(403, "The bootstrap token is invalid")
    email = str(payload.email).lower().strip()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, full_name=payload.full_name.strip(), password_hash=hash_password(payload.password), role=Role.ADMIN, email_verified=True, status=UserStatus.ACTIVE)
    db.add(user); db.flush()
    audit(db, user.id, "admin.bootstrap_created", "user", user.id)
    db.commit()
    return envelope(UserOut.model_validate(user).model_dump(mode="json"), "First administrator created. Sign in to the Control Center.")


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
    email = payload.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(payload.password, user.password_hash):
        # Failed logins are the signal a credential-stuffing attempt shows up as,
        # so the address is recorded. The submitted password never is.
        logger.warning("Failed login for %s", email)
        raise HTTPException(401, "Invalid email or password")
    if user.status != UserStatus.ACTIVE:
        logger.warning("Login refused: account %s is %s", user.id, user.status.value)
        raise HTTPException(403, "Account is not active")
    # Accounts that registered while verification was on would otherwise be
    # stranded once it is turned off: no code can be issued to clear the flag.
    if settings.email_verification_enabled and not user.email_verified:
        logger.info("Login refused: user %s has not verified their email", user.id)
        raise HTTPException(403, "Email verification required")
    user.last_login_at = datetime.now(UTC)
    auth = issue_tokens(user, db)
    audit(db, user.id, "auth.login", "user", user.id)
    db.commit()
    logger.info("User %s (%s) logged in", user.id, user.role.value)
    return envelope(auth.model_dump(mode="json"), "Logged in")


@router.post("/auth/refresh")
def refresh(payload: dict, db: Session = Depends(get_db)):
    token = payload.get("refresh_token", "")
    decoded = decode_token(token, "refresh")
    session = db.get(RefreshSession, decoded["jti"])
    user = db.get(User, decoded["sub"])
    if not session or session.revoked_at or not user or user.status != UserStatus.ACTIVE:
        # A revoked session presented again can mean a stolen refresh token is
        # being replayed, which is why this is a warning and names the session.
        logger.warning(
            "Refresh rejected for session %s (revoked=%s, user_active=%s)",
            decoded["jti"],
            bool(session and session.revoked_at),
            bool(user and user.status == UserStatus.ACTIVE),
        )
        raise HTTPException(401, "Refresh session is invalid")
    session.revoked_at = datetime.now(UTC)
    auth = issue_tokens(user, db)
    db.commit()
    logger.info("Rotated refresh session for user %s", user.id)
    return envelope(auth.model_dump(mode="json"), "Token refreshed")


@router.post("/auth/logout")
def logout(payload: dict, db: Session = Depends(get_db)):
    decoded = decode_token(payload.get("refresh_token", ""), "refresh")
    session = db.get(RefreshSession, decoded["jti"])
    if session and not session.revoked_at:
        session.revoked_at = datetime.now(UTC)
        db.commit()
        logger.info("User %s logged out, session %s revoked", decoded["sub"], decoded["jti"])
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


@router.post("/profiles/me/avatar")
async def upload_profile_avatar(
    avatar: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    content = await avatar.read()
    if not content or len(content) > 3 * 1024 * 1024:
        logger.info("Avatar upload rejected for user %s: %d bytes", user.id, len(content))
        raise HTTPException(413, "Profile photo must be smaller than 3 MB")
    signatures = {
        b"\xff\xd8\xff": (".jpg", "image/jpeg"),
        b"\x89PNG\r\n\x1a\n": (".png", "image/png"),
        b"RIFF": (".webp", "image/webp"),
    }
    detected = next((value for signature, value in signatures.items() if content.startswith(signature)), None)
    if detected and detected[0] == ".webp" and content[8:12] != b"WEBP":
        detected = None
    if not detected:
        # The type is decided by the magic bytes, not the client's content type,
        # so a rejection here means the file really is not an image.
        logger.info("Avatar upload rejected for user %s: unrecognised file signature", user.id)
        raise HTTPException(415, "Only JPG, PNG, or WEBP profile photos are accepted")
    suffix, _mime = detected
    previous_key = user.avatar_path
    try:
        user.avatar_path = avatar_storage.put(content, suffix)
    except OSError:
        # object_storage logged the path; this maps it to a response rather than
        # letting an unwritable volume surface as a bare 500.
        raise HTTPException(503, "Profile photo could not be stored. Please try again.") from None
    audit(db, user.id, "profile.avatar_updated", "user", user.id)
    db.commit()
    if previous_key:
        avatar_storage.delete(previous_key)
    logger.info("User %s updated their profile photo (%d bytes)", user.id, len(content))
    return envelope({"avatar_url": "/api/v1/profiles/me/avatar"}, "Profile photo updated")


@router.get("/profiles/me/avatar")
def profile_avatar(user: User = Depends(current_user)):
    if not user.avatar_path:
        raise HTTPException(404, "Profile photo not found")
    try:
        content = avatar_storage.read(user.avatar_path)
    except FileNotFoundError:
        # The row points at a key that is no longer behind it, so the record and
        # the store have drifted apart. Storage logged the key.
        logger.warning("User %s has an avatar row with no file behind it", user.id)
        raise HTTPException(404, "Profile photo not found") from None
    except OSError:
        # The object exists as far as the record knows; the store would not hand
        # it over. Storage logged the cause.
        raise HTTPException(503, "Profile photo is temporarily unavailable") from None
    mime = avatar_media_type(user.avatar_path)
    return Response(content, media_type=mime)


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
    membership = ensure_membership(db, user)
    stmt = (
        select(Job)
        .options(joinedload(Job.employer), joinedload(Job.applications))
        .where(Job.organization_id == membership.organization_id, Job.status != JobStatus.DELETED)
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
                Job.organization_id == membership.organization_id, Job.status != JobStatus.DELETED
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
    membership = ensure_membership(db, user)
    require_permission(db, user, "jobs.manage", membership.organization_id)
    enforce_limit(db, membership.organization_id, "active_jobs")
    job = Job(employer_id=user.id, organization_id=membership.organization_id, **payload.model_dump())
    db.add(job)
    audit(db, user.id, "job.created", "job", job.id)
    db.commit()
    db.refresh(job)
    job.employer = user
    return envelope(job_dict(job, 0), "Job created")


def owned_job(job_id: str, user: User, db: Session) -> Job:
    membership = ensure_membership(db, user)
    require_permission(db, user, "jobs.manage", membership.organization_id)
    job = db.scalar(
        select(Job)
        .options(joinedload(Job.employer), joinedload(Job.applications))
        .where(Job.id == job_id, Job.organization_id == membership.organization_id, Job.status != JobStatus.DELETED)
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
    if job.organization_id:
        enforce_limit(db, job.organization_id, "ai_analyses_monthly")
    if db.scalar(
        select(Application).where(Application.job_id == job_id, Application.applicant_id == user.id)
    ):
        raise HTTPException(409, "You have already applied to this job")
    content = await resume.read(settings.max_resume_size_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_resume_size_mb * 1024 * 1024:
        raise HTTPException(413, "Resume exceeds size limit")
    filename = Path(resume.filename or "").name
    suffix = Path(filename).suffix.lower()
    valid_pdf = suffix == ".pdf" and content.startswith(b"%PDF-")
    valid_docx = suffix == ".docx" and content.startswith(b"PK")
    if not (valid_pdf or valid_docx):
        # Checked against the magic bytes as well as the extension, so a rejection
        # means the content itself is wrong, not just the name.
        logger.info(
            "Application rejected for job %s: %r is not a valid PDF or DOCX", job_id, suffix
        )
        raise HTTPException(422, "A valid PDF or DOCX resume is required")
    mime_type = "application/pdf" if valid_pdf else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    try:
        key = resume_storage.put(content, suffix)
    except OSError:
        # Nothing has been written to the database yet, so failing here leaves no
        # orphaned row. object_storage logged the target directory.
        raise HTTPException(503, "Resume could not be stored. Please try again.") from None
    record = Resume(
        applicant_id=user.id,
        storage_key=key,
        original_filename=filename,
        mime_type=mime_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    default_stage = db.scalar(select(PipelineStage).where(PipelineStage.organization_id == job.organization_id, PipelineStage.is_default.is_(True)).order_by(PipelineStage.position)) if job.organization_id else None
    application = Application(id=str(uuid.uuid4()), job_id=job_id, applicant_id=user.id, organization_id=job.organization_id, stage_id=default_stage.id if default_stage else None, resume=record)
    db.add(application)
    # Persist the application before timeline and notification rows so PostgreSQL
    # can validate their foreign keys deterministically during the same transaction.
    db.flush()
    if job.organization_id:
        increment_usage(db, job.organization_id, "ai_analyses_monthly")
        increment_usage(db, job.organization_id, "storage_mb", max(1, math.ceil(len(content) / (1024 * 1024))))
        db.add(CandidateTimeline(organization_id=job.organization_id, application_id=application.id, actor_id=user.id, event_type="application_received", description=f"{user.full_name} applied for {job.title}."))
        for membership in db.scalars(select(OrganizationMembership).where(OrganizationMembership.organization_id == job.organization_id, OrganizationMembership.status == "active")).all():
            create_notification(db, user_id=membership.user_id, organization_id=job.organization_id, type_="new_candidate", title=f"New applicant for {job.title}", message=f"{user.full_name} submitted an application.", action_url=f"/employer/candidates/{application.id}", email_category="new_applications")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        resume_storage.delete(key)
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_application_job_applicant":
            # Two submissions raced past the duplicate check above; the unique
            # index is what actually decides, so this is expected, not a defect.
            logger.info(
                "Duplicate application from user %s to job %s caught by the unique index",
                user.id,
                job_id,
            )
            raise HTTPException(409, "You have already applied to this job") from exc
        logger.exception(
            "Application creation failed due to database integrity constraint %s", constraint
        )
        raise HTTPException(500, "Application could not be created. Please try again.") from exc
    db.refresh(application)
    queued = queue_application_analysis(db, application.id, job.organization_id)
    db.commit()
    dispatch_background(background, queued.id)
    logger.info(
        "Accepted application %s from user %s for job %s (%d bytes, %s), analysis job %s queued",
        application.id,
        user.id,
        job_id,
        len(content),
        suffix,
        queued.id,
    )
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
    queued = queue_application_analysis(db, application.id, application.organization_id)
    db.commit()
    dispatch_background(background, queued.id)
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
    queued = queue_application_analysis(db, application.id, application.organization_id, True)
    db.commit()
    dispatch_background(background, queued.id)
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
    membership = ensure_membership(db, user)
    if not app or app.job.organization_id != membership.organization_id:
        raise HTTPException(404, "Application not found")
    try:
        content = resume_storage.read(app.resume.storage_key)
    except FileNotFoundError as exc:
        logger.warning("Resume for application %s is missing from storage", app.id)
        raise HTTPException(404, "Resume file not found") from exc
    except OSError as exc:
        raise HTTPException(503, "Resume is temporarily unavailable") from exc
    audit(db, user.id, "resume.downloaded", "application", app.id)
    db.commit()
    # A recruiter reading a candidate's document is a privacy-relevant event, so
    # it is recorded in the log as well as the audit table.
    logger.info("User %s downloaded the resume for application %s", user.id, app.id)
    return Response(
        content,
        media_type=app.resume.mime_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{app.resume.original_filename}"'
            )
        },
    )


@router.post("/employer/applications/{application_id}/reanalyze", status_code=202)
def employer_reanalyze_application(
    application_id: str,
    background: BackgroundTasks,
    user: User = Depends(require_roles(Role.EMPLOYER)),
    db: Session = Depends(get_db),
):
    application = db.scalar(
        select(Application).options(joinedload(Application.job)).where(Application.id == application_id)
    )
    membership = ensure_membership(db, user)
    require_permission(db, user, "candidates.manage", membership.organization_id)
    if not application or application.job.organization_id != membership.organization_id:
        raise HTTPException(404, "Application not found")
    application.status = ApplicationStatus.PROCESSING
    application.processing_error = None
    audit(db, user.id, "application.reanalysis_requested", "application", application.id)
    db.commit()
    queued = queue_application_analysis(db, application.id, application.organization_id, True)
    db.commit()
    dispatch_background(background, queued.id)
    return envelope({"id": application.id, "status": "processing"}, "Advanced analysis restarted")


@router.post("/applications/{application_id}/override")
def override_application_score(
    application_id: str,
    payload: ScoreOverrideRequest,
    user: User = Depends(require_roles(Role.EMPLOYER, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    application = db.scalar(
        select(Application).options(joinedload(Application.job)).where(Application.id == application_id)
    )
    membership = ensure_membership(db, user) if user.role == Role.EMPLOYER else None
    if not application or (user.role == Role.EMPLOYER and application.job.organization_id != membership.organization_id):
        raise HTTPException(404, "Application not found")
    previous = application.override_score if application.override_score is not None else application.final_score
    application.override_score = payload.score
    application.override_reason = payload.reason.strip()
    application.overridden_by_id = user.id
    application.overridden_at = datetime.now(UTC)
    db.add(ScoreOverride(application_id=application.id, actor_id=user.id, previous_score=previous, override_score=payload.score, reason=payload.reason.strip()))
    audit(db, user.id, "application.score_overridden", "application", application.id)
    db.commit()
    return envelope({"override_score": application.override_score, "override_reason": application.override_reason}, "Human review score saved")


@router.get("/applications/{application_id}/overrides")
def application_override_history(
    application_id: str,
    user: User = Depends(require_roles(Role.EMPLOYER, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    application = db.scalar(select(Application).options(joinedload(Application.job)).where(Application.id == application_id))
    membership = ensure_membership(db, user) if user.role == Role.EMPLOYER else None
    if not application or (user.role == Role.EMPLOYER and application.job.organization_id != membership.organization_id):
        raise HTTPException(404, "Application not found")
    history = db.scalars(select(ScoreOverride).where(ScoreOverride.application_id == application_id).order_by(ScoreOverride.created_at.desc())).all()
    return envelope([{"id": item.id, "previous_score": item.previous_score, "override_score": item.override_score, "reason": item.reason, "actor_id": item.actor_id, "created_at": item.created_at.isoformat()} for item in history])


@router.get("/employer/dashboard")
def employer_dashboard(
    user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)
):
    membership = ensure_membership(db, user)
    jobs = db.scalars(
        select(Job).where(Job.organization_id == membership.organization_id, Job.status != JobStatus.DELETED)
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
    stmt = select(User).where(User.status != UserStatus.DELETED)
    if q:
        stmt = stmt.where(or_(User.full_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    users = db.scalars(stmt.order_by(User.created_at.desc())).all()
    return envelope([UserOut.model_validate(item).model_dump(mode="json") for item in users])


@router.post("/admin/users/admin", status_code=status.HTTP_201_CREATED)
def create_administrator(
    payload: AdminCreate,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    email = str(payload.email).lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    created = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=Role.ADMIN,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    db.add(created)
    db.flush()
    audit(db, admin.id, "admin.user_created", "user", created.id)
    db.commit()
    db.refresh(created)
    # Privilege escalation is the event most worth being able to reconstruct
    # later, so both the new and the granting administrator are named.
    logger.warning("Admin %s created a new administrator account %s", admin.id, created.id)
    return envelope(
        UserOut.model_validate(created).model_dump(mode="json"),
        "Administrator created successfully",
    )


@router.patch("/admin/users/{user_id}/status")
def set_status(
    user_id: str,
    payload: UserStatusUpdate,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.role == Role.ADMIN:
        raise HTTPException(403, "Administrator accounts, including your own, cannot be suspended, activated, or role-changed through user management")
    if payload.status not in {UserStatus.ACTIVE, UserStatus.SUSPENDED}:
        raise HTTPException(422, "Use delete endpoint for deletion")
    target.status = payload.status
    revoked = 0
    if payload.status == UserStatus.SUSPENDED:
        now = datetime.now(UTC)
        for session in db.scalars(
            select(RefreshSession).where(
                RefreshSession.user_id == target.id, RefreshSession.revoked_at.is_(None)
            )
        ).all():
            session.revoked_at = now
            revoked += 1
    audit(db, admin.id, f"user.{payload.status.value}", "user", target.id)
    db.commit()
    logger.info(
        "Admin %s set user %s to %s (%d sessions revoked)",
        admin.id,
        target.id,
        payload.status.value,
        revoked,
    )
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


@router.get("/admin/intelligence/monitoring")
def intelligence_monitoring(
    admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)
):
    applications = db.scalars(select(Application)).all()
    scored = [item for item in applications if item.final_score is not None]
    ai_completed = [item for item in scored if item.ai_score is not None]
    disagreements = [
        item for item in ai_completed
        if abs(float(item.deterministic_score or 0) - float(item.ai_score or 0)) >= settings.hybrid_disagreement_threshold
    ]
    buckets = [
        {"label": "0–39", "count": sum(float(item.final_score) < 40 for item in scored)},
        {"label": "40–59", "count": sum(40 <= float(item.final_score) < 60 for item in scored)},
        {"label": "60–79", "count": sum(60 <= float(item.final_score) < 80 for item in scored)},
        {"label": "80–100", "count": sum(float(item.final_score) >= 80 for item in scored)},
    ]
    overridden = [item for item in scored if item.override_score is not None]
    return envelope({
        "total_applications": len(applications),
        "scored_applications": len(scored),
        "average_final_score": round(sum(float(item.final_score) for item in scored) / len(scored), 2) if scored else 0,
        "gemini_completion_rate": round(len(ai_completed) / len(scored) * 100, 2) if scored else 0,
        "disagreement_rate": round(len(disagreements) / len(ai_completed) * 100, 2) if ai_completed else 0,
        "manual_review_count": len(disagreements),
        "override_rate": round(len(overridden) / len(scored) * 100, 2) if scored else 0,
        "score_distribution": buckets,
        "guardrails": {
            "maximum_gemini_weight_percent": round(settings.gemini_weight * 100, 2),
            "disagreement_threshold_points": settings.hybrid_disagreement_threshold,
            "protected_attributes_used": False,
        },
    })


@router.get("/admin/jobs/{job_id}/applications")
def admin_job_applications(
    job_id: str,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    job = db.scalar(select(Job).where(Job.id == job_id, Job.status != JobStatus.DELETED))
    if not job:
        raise HTTPException(404, "Job not found")
    applications = (
        db.scalars(
            select(Application)
            .options(joinedload(Application.applicant))
            .where(Application.job_id == job_id)
            .order_by(Application.final_score.desc().nullslast(), Application.created_at)
        )
        .unique()
        .all()
    )
    audit(db, admin.id, "admin.applications_viewed", "job", job.id)
    db.commit()
    return envelope(
        [
            {
                "id": application.id,
                "job_id": application.job_id,
                "status": application.status.value,
                "final_score": application.final_score,
                "matched_skills": application.matched_skills or [],
                **insight_dict(application),
                "processing_error": public_processing_error(application),
                "created_at": application.created_at.isoformat(),
                "applicant": UserOut.model_validate(application.applicant).model_dump(mode="json"),
            }
            for application in applications
        ]
    )


@router.get("/admin/applications/{application_id}/resume")
def admin_download_resume(
    application_id: str,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    application = db.scalar(
        select(Application)
        .options(joinedload(Application.resume))
        .where(Application.id == application_id)
    )
    if not application:
        raise HTTPException(404, "Application not found")
    try:
        content = resume_storage.read(application.resume.storage_key)
    except FileNotFoundError as exc:
        logger.warning("Resume for application %s is missing from storage", application.id)
        raise HTTPException(404, "Resume file not found") from exc
    except OSError as exc:
        raise HTTPException(503, "Resume is temporarily unavailable") from exc
    audit(db, admin.id, "admin.resume_downloaded", "application", application.id)
    db.commit()
    # An administrator can reach any workspace's documents, so this crosses a
    # tenant boundary and is worth a log line of its own.
    logger.info(
        "Admin %s downloaded the resume for application %s", admin.id, application.id
    )
    return Response(
        content,
        media_type=application.resume.mime_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{application.resume.original_filename}"'
            )
        },
    )


@router.post("/admin/applications/{application_id}/retry-ai", status_code=202)
def admin_retry_application_ai(
    application_id: str,
    background: BackgroundTasks,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(404, "Application not found")
    if application.status != ApplicationStatus.COMPLETED:
        raise HTTPException(409, "Resume processing must complete before AI can be retried")
    if not settings.gemini_enabled or not settings.gemini_api_key:
        logger.warning(
            "Admin %s asked to retry AI for application %s but Gemini is not configured",
            admin.id,
            application_id,
        )
        raise HTTPException(503, "Gemini analysis is not configured")
    application.ai_status = "processing"
    application.ai_error = None
    audit(db, admin.id, "admin.ai_analysis_restarted", "application", application.id)
    db.commit()
    queued = queue_application_analysis(db, application.id, application.organization_id, True)
    db.commit()
    dispatch_background(background, queued.id)
    return envelope(
        {"id": application.id, "ai_status": "processing"},
        "Gemini analysis restarted",
    )


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
