import uuid
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.grafana import GrafanaDashboardPanel, GrafanaMapping
from app.models.user import User
from app.schemas.grafana import GrafanaEmbedPanelResponse, VmDashboardPanelsResponse
from app.services.vm_service import VmService

DASHBOARD_UID = "masterptit-vm-observability"
DASHBOARD_SLUG = "masterptit-vm-observability"
GRAFANA_ORG_ID = 1


def build_grafana_panel_url(
    panel_id: int,
    vm_id: uuid.UUID | str,
    host_name: str,
    from_time: str = "now-6h",
    to_time: str = "now",
    theme: str = "dark",
) -> str:
    """Build an encoded Grafana d-solo iframe URL for one VM panel."""
    settings = get_settings()
    query = urlencode(
        {
            "orgId": GRAFANA_ORG_ID,
            "panelId": panel_id,
            "var-vm_id": str(vm_id),
            "var-host_name": host_name,
            "from": from_time,
            "to": to_time,
            "theme": theme,
            "hideLogo": "true",
        }
    )
    base_url = settings.public_grafana_url.rstrip("/")
    return f"{base_url}/d-solo/{DASHBOARD_UID}/{DASHBOARD_SLUG}?{query}"


def panel_key(title: str, panel_id: int) -> str:
    """Create a stable frontend key from a Grafana panel title and ID."""
    normalized = "".join(character.lower() if character.isalnum() else "_" for character in title).strip("_")
    return f"{normalized or 'panel'}_{panel_id}"


def panel_height(panel: dict) -> int:
    """Convert Grafana grid height into a practical iframe pixel height."""
    grid_height = panel.get("gridPos", {}).get("h")
    if isinstance(grid_height, int):
        return min(max(grid_height * 32, 220), 520)
    return 300


def flatten_dashboard_panels(panels: list[dict]) -> list[dict]:
    """Flatten Grafana panel definitions including nested row panels."""
    flattened: list[dict] = []
    for panel in panels:
        nested_panels = panel.get("panels")
        if isinstance(nested_panels, list):
            flattened.extend(flatten_dashboard_panels(nested_panels))
        panel_id = panel.get("id")
        panel_type = panel.get("type")
        if isinstance(panel_id, int) and panel_type != "row":
            flattened.append(panel)
    return flattened


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

    @staticmethod
    async def fetch_dashboard_spec() -> dict:
        """Load the Grafana dashboard JSON from Grafana's Dashboard HTTP API."""
        settings = get_settings()
        dashboard_url = f"{settings.grafana_internal_url.rstrip('/')}/api/dashboards/uid/{DASHBOARD_UID}"
        auth = (settings.grafana_admin_user, settings.grafana_admin_password)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(dashboard_url, auth=auth)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Grafana dashboard API returned {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not connect to Grafana dashboard API",
            ) from exc
        payload = response.json()
        dashboard = payload.get("dashboard")
        if not isinstance(dashboard, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Grafana dashboard response is invalid")
        return dashboard

    @staticmethod
    async def get_vm_dashboard_panels(db: AsyncSession, user: User, vm_id: uuid.UUID) -> VmDashboardPanelsResponse:
        """Build Grafana embed panel URLs from the live dashboard JSON for one owned VM."""
        vm = await VmService.get_owned_vm(db, user, vm_id)
        dashboard = await GrafanaService.fetch_dashboard_spec()
        dashboard_uid = dashboard.get("uid") if isinstance(dashboard.get("uid"), str) else DASHBOARD_UID
        panels = flatten_dashboard_panels(dashboard.get("panels", []))
        panels = [
            GrafanaEmbedPanelResponse(
                key=panel_key(str(panel.get("title") or f"Panel {panel['id']}"), panel["id"]),
                title=str(panel.get("title") or f"Panel {panel['id']}"),
                panel_id=panel["id"],
                iframe_url=build_grafana_panel_url(panel["id"], vm.id, vm.vm_name),
                height=panel_height(panel),
            )
            for panel in panels
        ]
        return VmDashboardPanelsResponse(
            vm_id=vm.id,
            host_name=vm.vm_name,
            dashboard_uid=dashboard_uid,
            panels=panels,
        )
