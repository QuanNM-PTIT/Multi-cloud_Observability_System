from datetime import timedelta
import hashlib
import hmac
from typing import Any

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.timezone import now_utc

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password before storing it in the database."""
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored password hash."""
    return password_context.verify(password, password_hash)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """Create a signed JWT access token for an authenticated user."""
    settings = get_settings()
    expires_at = now_utc() + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expires_at}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token or raise a 401 error."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def hash_agent_token(raw_token: str) -> str:
    """Hash an agent token with HMAC-SHA256 so raw tokens are never stored."""
    settings = get_settings()
    return hmac.new(settings.server_secret.encode(), raw_token.encode(), hashlib.sha256).hexdigest()


def hash_receiver_otp(receiver_id: str, otp: str) -> str:
    """Hash a receiver verification OTP so only a one-way value is stored."""
    settings = get_settings()
    payload = f"{receiver_id}:{otp}".encode()
    return hmac.new(settings.server_secret.encode(), payload, hashlib.sha256).hexdigest()
