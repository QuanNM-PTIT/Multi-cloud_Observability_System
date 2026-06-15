import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UuidPrimaryKeyMixin


class AlertRule(UuidPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "alert_rules"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    vm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vm_instances.id", ondelete="CASCADE"), nullable=True, index=True)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    metric_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    promql_expr: Mapped[str] = mapped_column(Text, nullable=False)
    condition_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))


class NotificationChannel(UuidPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "notification_channels"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False)
    receiver: Mapped[str] = mapped_column(String(500), nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))


class AlertRuleChannel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "alert_rule_channels"
    __table_args__ = (UniqueConstraint("alert_rule_id", "channel_id", name="uq_alert_rule_channel"),)

    alert_rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("notification_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
