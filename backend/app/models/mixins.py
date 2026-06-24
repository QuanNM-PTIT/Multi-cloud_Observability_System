from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import now_utc


class UuidPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class SoftDeleteMixin:
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
