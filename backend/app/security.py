import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Role, User, UserStatus

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_token(
    user: User, token_type: str, expires: timedelta, token_id: str | None = None
) -> tuple[str, str]:
    jti = token_id or str(uuid.uuid4())
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "role": user.role.value,
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": now + expires,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256"), jti


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        if payload.get("type") != expected_type:
            raise JWTError("Wrong token type")
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_token(credentials.credentials, "access")
    user = db.get(User, payload["sub"])
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=401, detail="Account is not active")
    return user


def require_roles(*roles: Role):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return dependency
