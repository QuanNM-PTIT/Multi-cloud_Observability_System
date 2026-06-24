from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UuidPrimaryKeyMixin


class VmInstance(UuidPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "vm_instances"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    vm_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cloud_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    public_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    private_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    os_type: Mapped[str] = mapped_column(String(50), nullable=False)
    os_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    monitoring_status: Mapped[str] = mapped_column(String(50), nullable=False, default="NOT_INSTALLED", server_default=text("'NOT_INSTALLED'"))
    is_monitoring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="vm_instances")
    agent_status = relationship("VmAgentStatus", back_populates="vm", uselist=False)
