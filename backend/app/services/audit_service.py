import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditService:
    @staticmethod
    def add_log(
        db: AsyncSession,
        action: str,
        user_id: uuid.UUID | None = None,
        target_type: str | None = None,
        target_id: uuid.UUID | None = None,
        request_ip: str | None = None,
        user_agent: str | None = None,
        detail_json: dict | None = None,
    ) -> AuditLog:
        """Add an audit log row to the current transaction without committing it."""
        log = AuditLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            request_ip=request_ip,
            user_agent=user_agent,
            detail_json=detail_json,
        )
        db.add(log)
        return log
