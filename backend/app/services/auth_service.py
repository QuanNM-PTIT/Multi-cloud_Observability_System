from fastapi import HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.core.timezone import now_utc
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.audit_service import AuditService


class AuthService:
    @staticmethod
    async def register(db: AsyncSession, payload: RegisterRequest, request: Request) -> User:
        """Register a new local portal account with a hashed password."""
        existing = await db.execute(
            select(User).where(or_(User.username == payload.username, User.email == payload.email), User.deleted.is_(False))
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists")

        user = User(
            username=payload.username,
            email=str(payload.email),
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
        )
        db.add(user)
        await db.flush()
        AuditService.add_log(
            db,
            action="REGISTER",
            user_id=user.id,
            target_type="users",
            target_id=user.id,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def login(db: AsyncSession, payload: LoginRequest, request: Request) -> TokenResponse:
        """Authenticate a local account and return a signed JWT access token."""
        result = await db.execute(
            select(User).where(
                or_(User.username == payload.username_or_email, User.email == payload.username_or_email),
                User.deleted.is_(False),
            )
        )
        user = result.scalar_one_or_none()
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username/email or password")
        if user.status != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is not active")

        user.last_login_at = now_utc()
        AuditService.add_log(
            db,
            action="LOGIN",
            user_id=user.id,
            target_type="users",
            target_id=user.id,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
        return TokenResponse(access_token=create_access_token(str(user.id), {"username": user.username}))
