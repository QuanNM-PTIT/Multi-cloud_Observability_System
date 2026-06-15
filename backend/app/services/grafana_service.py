import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.grafana import GrafanaDashboardPanel, GrafanaMapping
from app.models.user import User
from app.services.vm_service import VmService


class GrafanaService:
    @staticmethod
    async def get_dashboard_mapping(db: AsyncSession, user: User, vm_id: uuid.UUID) -> GrafanaMapping | None:
        """Return the active Grafana dashboard mapping for an owned VM."""
        vm = await VmService.get_owned_vm(db, user, vm_id)
        result = await db.execute(
            select(GrafanaMapping)
            .where(GrafanaMapping.vm_id == vm.id, GrafanaMapping.status == "ACTIVE")
            .order_by(GrafanaMapping.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def list_dashboard_panels(db: AsyncSession, user: User, vm_id: uuid.UUID) -> list[GrafanaDashboardPanel]:
        """List active Grafana panel iframe mappings for an owned VM."""
        vm = await VmService.get_owned_vm(db, user, vm_id)
        result = await db.execute(
            select(GrafanaDashboardPanel)
            .where(GrafanaDashboardPanel.vm_id == vm.id, GrafanaDashboardPanel.status == "ACTIVE")
            .order_by(GrafanaDashboardPanel.is_default.desc(), GrafanaDashboardPanel.panel_id.asc())
        )
        return list(result.scalars().all())
