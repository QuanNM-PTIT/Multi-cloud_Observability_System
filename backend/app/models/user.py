from datetime import datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UuidPrimaryKeyMixin


class User(UuidPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    grafana_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE", server_default=text("'ACTIVE'"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    vm_instances = relationship("VmInstance", back_populates="user")
