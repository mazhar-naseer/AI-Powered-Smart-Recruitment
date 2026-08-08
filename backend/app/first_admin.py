"""Seed the first administrator from the environment.

A fresh deployment has no administrator and no way to create one through the
API, since registration refuses the admin role (``schemas.RegisterRequest``).
``ADMIN_EMAIL`` / ``ADMIN_PASSWORD`` close that gap at startup. Once the first
administrator exists, further ones are created through
``POST /admin/users/admin``, which requires an authenticated administrator.

Seeding only ever *creates*. It never updates a password, promotes an existing
account, or runs at all once any administrator is present, so leaving the
variables set across restarts is harmless and an environment variable can never
silently take over an account that already exists.
"""

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.logging_config import get_logger
from app.models import AuditLog, Role, User, UserStatus
from app.schemas import AdminCreate
from app.security import hash_password

logger = get_logger(__name__)


class AdminSeedError(RuntimeError):
    """Raised when the seed variables are present but unusable."""


def ensure_first_admin(settings: Settings | None = None) -> User | None:
    """Create the first administrator if one is configured and none exists.

    Returns the created user, or ``None`` when seeding was not configured or was
    skipped. Raises :class:`AdminSeedError` on a malformed configuration so a
    typo fails the boot rather than leaving the deployment quietly locked out.
    """
    settings = settings or get_settings()
    email = (settings.admin_email or "").strip()
    password = settings.admin_password or ""

    if not email and not password:
        return None
    if not email or not password:
        raise AdminSeedError(
            "ADMIN_EMAIL and ADMIN_PASSWORD must both be set to seed the first "
            "administrator; only one of them is present"
        )

    # AdminCreate already encodes the rules the API enforces for an administrator
    # — address shape, name length, and password strength — so the seeded account
    # cannot be weaker than one created through /admin/users/admin.
    try:
        payload = AdminCreate(
            full_name=settings.admin_full_name, email=email, password=password
        )
    except ValidationError as exc:
        reasons = "; ".join(error["msg"] for error in exc.errors())
        raise AdminSeedError(f"ADMIN_* configuration is invalid: {reasons}") from exc

    normalized = str(payload.email).lower().strip()
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.role == Role.ADMIN).limit(1)):
            logger.info("Admin seed skipped: an administrator already exists")
            return None
        if db.scalar(select(User.id).where(User.email == normalized)):
            # Promoting on the strength of an environment variable would turn a
            # config change into a privilege grant, so this stops instead. The
            # deployment still has no administrator, hence a warning.
            logger.warning(
                "Admin seed skipped: %s is already registered as a non-admin "
                "account. Set ADMIN_EMAIL to a different address to seed one.",
                normalized,
            )
            return None

        user = User(
            email=normalized,
            full_name=payload.full_name.strip(),
            password_hash=hash_password(payload.password),
            role=Role.ADMIN,
            status=UserStatus.ACTIVE,
            email_verified=True,
        )
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            # Two workers booting at once both cleared the check above; the unique
            # index on email decides, so losing the race is expected, not a fault.
            db.rollback()
            logger.info("Admin seed skipped: another worker created it first")
            return None
        db.add(
            AuditLog(
                actor_id=user.id,
                action="admin.seeded_from_environment",
                target_type="user",
                target_id=user.id,
                metadata_json={},
            )
        )
        db.commit()
        db.refresh(user)
        # Creating an administrator is the highest-privilege event the system has,
        # so it is recorded at warning level as well as in the audit table.
        logger.warning("Seeded the first administrator %s from the environment", normalized)
        return user
