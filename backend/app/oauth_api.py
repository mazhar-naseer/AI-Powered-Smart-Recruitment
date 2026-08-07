import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import (
    AuditLog, OAuthLoginCode, OAuthState, RefreshSession, Role, SocialIdentity,
    User, UserStatus,
)
from app.schemas import AuthOut, UserOut
from app.security import create_token, hash_password
from app.tenancy import create_workspace
from app.logging_config import get_logger

router = APIRouter(prefix="/api/v1/auth/oauth")
settings = get_settings()
logger = get_logger(__name__)
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class OAuthExchange(BaseModel):
    code: str = Field(min_length=20, max_length=300)


def envelope(data=None, message="Success"):
    return {"success": True, "message": message, "data": data}


def google_configured() -> bool:
    return bool(settings.google_oauth_enabled and settings.google_client_id and settings.google_client_secret)


def safe_return_to(candidate: str | None) -> str:
    fallback = settings.frontend_url.rstrip("/")
    if not candidate:
        return fallback
    parsed = urlsplit(candidate)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    allowed = {item.rstrip("/") for item in settings.frontend_origins} | {fallback}
    if settings.environment == "development" and parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}:
        return origin
    return origin if origin in allowed else fallback


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def issue_tokens(user: User, db: Session) -> AuthOut:
    access, _ = create_token(user, "access", timedelta(minutes=settings.access_token_minutes))
    refresh, jti = create_token(user, "refresh", timedelta(days=settings.refresh_token_days))
    db.add(RefreshSession(id=jti, user_id=user.id, expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days)))
    return AuthOut(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user))


def callback_redirect(return_to: str, *, code: str | None = None, error: str | None = None) -> RedirectResponse:
    query = urlencode({"code": code} if code else {"error": error or "Google sign-in failed"})
    return RedirectResponse(f"{return_to.rstrip('/')}/oauth/callback?{query}", status_code=303)


def fetch_google_identity(code: str, verifier: str) -> dict:
    with httpx.Client(timeout=15) as client:
        token_response = client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        })
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise ValueError("Google did not return an access token")
        profile_response = client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        profile_response.raise_for_status()
        return profile_response.json()


@router.get("/providers")
def providers():
    return envelope({"google": {"enabled": google_configured()}})


@router.get("/google/start")
def google_start(
    role: str = Query(default="applicant", pattern="^(applicant|employer)$"),
    intent: str = Query(default="login", pattern="^(login|register)$"),
    return_to: str | None = None,
    db: Session = Depends(get_db),
):
    if not google_configured():
        logger.warning("Google sign-in requested but the provider is not configured")
        raise HTTPException(503, "Google sign-in is not configured")
    raw_state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    db.add(OAuthState(
        state_hash=digest(raw_state), provider="google", intent=intent,
        requested_role=role, code_verifier=verifier, return_to=safe_return_to(return_to),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    ))
    db.commit()
    logger.info("Starting Google OAuth (intent=%s, role=%s)", intent, role)
    query = urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": raw_state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    })
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{query}", status_code=302)


@router.get("/google/callback")
def google_callback(
    state: str = "", code: str = "", error: str | None = None,
    db: Session = Depends(get_db),
):
    now = datetime.now(UTC)
    oauth_state = db.scalar(select(OAuthState).where(
        OAuthState.state_hash == digest(state), OAuthState.provider == "google",
        OAuthState.consumed_at.is_(None), OAuthState.expires_at > now,
    )) if state else None
    return_to = oauth_state.return_to if oauth_state else settings.frontend_url.rstrip("/")
    if not oauth_state:
        # Also the shape a replayed or forged callback takes, so this is worth a
        # warning rather than an info line.
        logger.warning("Google callback rejected: state is unknown, expired, or already consumed")
        return callback_redirect(return_to, error="Google sign-in session is invalid or expired. Please try again.")
    oauth_state.consumed_at = now
    db.commit()
    if error or not code:
        logger.info("Google callback returned no authorization code (error=%s)", error)
        return callback_redirect(return_to, error="Google sign-in was cancelled.")
    try:
        profile = fetch_google_identity(code, oauth_state.code_verifier)
        subject = str(profile.get("sub", ""))
        email = str(profile.get("email", "")).lower().strip()
        verified = profile.get("email_verified") in {True, "true"}
        if not subject or not email or not verified:
            raise ValueError("Google account does not expose a verified email")
        identity = db.scalar(select(SocialIdentity).where(SocialIdentity.provider == "google", SocialIdentity.provider_subject == subject))
        user = db.get(User, identity.user_id) if identity else db.scalar(select(User).where(User.email == email))
        if not user:
            if oauth_state.intent != "register":
                logger.info("Google login rejected: no SmartHire account uses %s", email)
                return callback_redirect(return_to, error="No SmartHire account uses this Google email. Choose a role and register first.")
            role = Role(oauth_state.requested_role)
            full_name = str(profile.get("name") or email.split("@", 1)[0])[:120]
            user = User(
                id=str(uuid.uuid4()), email=email, full_name=full_name, role=role,
                password_hash=hash_password(secrets.token_urlsafe(48)),
                email_verified=True, status=UserStatus.ACTIVE,
            )
            db.add(user);db.flush()
            logger.info("Created %s account %s from Google sign-in", role.value, user.id)
            if role == Role.EMPLOYER:
                create_workspace(db, user, f"{full_name}'s Company")
        if user.role == Role.ADMIN:
            logger.warning("Google sign-in refused for admin account %s", user.id)
            return callback_redirect(return_to, error="Administrators must use the secure Control Center login.")
        if user.status != UserStatus.ACTIVE:
            logger.warning("Google sign-in refused: account %s is %s", user.id, user.status.value)
            return callback_redirect(return_to, error="This SmartHire account is not active.")
        user.email_verified = True
        user.last_login_at = now
        if not identity:
            db.add(SocialIdentity(user_id=user.id, provider="google", provider_subject=subject, provider_email=email))
        raw_login_code = secrets.token_urlsafe(48)
        db.add(OAuthLoginCode(code_hash=digest(raw_login_code), user_id=user.id, expires_at=now + timedelta(minutes=2)))
        db.add(AuditLog(actor_id=user.id, action="auth.google_authenticated", target_type="user", target_id=user.id, metadata_json={"new_account": oauth_state.intent == "register"}))
        db.commit()
        logger.info("Google authentication succeeded for user %s", user.id)
        return callback_redirect(return_to, code=raw_login_code)
    except (httpx.HTTPError, ValueError):
        db.rollback()
        # The user only ever sees a generic message, so without this the reason a
        # sign-in fails — a rejected client secret, a redirect_uri mismatch, an
        # unverified Google email — is not recorded anywhere.
        logger.exception("Google sign-in could not be completed")
        return callback_redirect(return_to, error="Google could not verify this sign-in. Please try again.")


@router.post("/exchange")
def exchange(payload: OAuthExchange, db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    login_code = db.scalar(select(OAuthLoginCode).where(
        OAuthLoginCode.code_hash == digest(payload.code), OAuthLoginCode.consumed_at.is_(None),
        OAuthLoginCode.expires_at > now,
    ))
    if not login_code:
        logger.warning("Google login code exchange rejected: code is invalid, expired, or already used")
        raise HTTPException(400, "Google login code is invalid, expired, or already used")
    user = db.get(User, login_code.user_id)
    if not user or user.status != UserStatus.ACTIVE:
        logger.warning("Google login code exchange refused for user %s", login_code.user_id)
        raise HTTPException(403, "SmartHire account is not active")
    login_code.consumed_at = now
    auth = issue_tokens(user, db)
    db.add(AuditLog(actor_id=user.id, action="auth.google_login_completed", target_type="user", target_id=user.id))
    db.commit()
    logger.info("Issued tokens for Google sign-in of user %s", user.id)
    return envelope(auth.model_dump(mode="json"), "Signed in with Google")
