from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username_or_email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    id: UUID
    username: str
    email: EmailStr
    full_name: str | None
    status: str
    grafana_user_id: str | None

    model_config = {"from_attributes": True}
