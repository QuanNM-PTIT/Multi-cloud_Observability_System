import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKeyMixin


class GrafanaMapping(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "grafana_mappings"

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    vm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vm_instances.id", ondelete="CASCADE"), nullable=True, index=True)
    grafana_org_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grafana_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grafana_folder_uid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dashboard_uid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dashboard_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mapping_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE", server_default=text("'ACTIVE'"))


class GrafanaDashboardPanel(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "grafana_dashboard_panels"

    vm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vm_instances.id", ondelete="CASCADE"), nullable=True, index=True)
    dashboard_uid: Mapped[str] = mapped_column(String(100), nullable=False)
    panel_id: Mapped[int] = mapped_column(Integer, nullable=False)
    panel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    panel_type: Mapped[str] = mapped_column(String(50), nullable=False)
    iframe_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE", server_default=text("'ACTIVE'"))
