from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import CurrentUserResponse, LoginRequest, RegisterRequest, TokenResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=CurrentUserResponse, status_code=201)
async def register(payload: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Create a local portal user account and return the created profile."""
    return await AuthService.register(db, payload, request)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Authenticate a local portal user and return a bearer token."""
    return await AuthService.login(db, payload, request)


@router.get("/me", response_model=CurrentUserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the profile represented by the current bearer token."""
    return current_user
