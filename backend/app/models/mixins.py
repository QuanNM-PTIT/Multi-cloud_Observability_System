from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UuidPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, onupdate=datetime.utcnow)


class SoftDeleteMixin:
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
