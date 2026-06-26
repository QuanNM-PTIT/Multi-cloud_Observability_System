from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.base import TimezoneAwareResponse


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_bcrypt_password_size(cls, value: str) -> str:
        """Ensure bcrypt-compatible passwords fail validation instead of causing a server error."""
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 bytes or fewer")
        return value


class LoginRequest(BaseModel):
    username_or_email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_bcrypt_password_size(cls, value: str) -> str:
        """Ensure bcrypt-compatible passwords fail validation instead of causing a server error."""
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 bytes or fewer")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(TimezoneAwareResponse):
    id: UUID
    username: str
    email: EmailStr
    full_name: str | None
    status: str
    grafana_user_id: str | None
