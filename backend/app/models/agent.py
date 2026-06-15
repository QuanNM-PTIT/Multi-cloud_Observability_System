from datetime import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin


class AgentToken(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_tokens"

    vm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vm_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    token_prefix: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE", server_default=text("'ACTIVE'"))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentPackage(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_packages"

    vm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vm_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    generated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    package_path: Mapped[str] = mapped_column(String(500), nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    os_type: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="GENERATED", server_default=text("'GENERATED'"))
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentInstallEvent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "agent_install_events"

    vm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vm_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    package_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_packages.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_status: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class VmAgentStatus(UuidPrimaryKeyMixin, Base):
    __tablename__ = "vm_agent_status"

    vm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vm_instances.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    agent_status: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN", server_default=text("'UNKNOWN'"))
    agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    service_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    vm = relationship("VmInstance", back_populates="agent_status")
