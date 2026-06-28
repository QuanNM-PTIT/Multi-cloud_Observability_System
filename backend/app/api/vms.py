from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.agent import AgentPackageResponse, AgentScriptResponse, AgentStatusResponse
from app.schemas.grafana import GrafanaDashboardResponse, GrafanaPanelResponse, VmDashboardPanelsResponse
from app.schemas.vm import VmCreateRequest, VmListResponse, VmResponse, VmUpdateRequest
from app.services.agent_service import AgentService
from app.services.grafana_service import GrafanaService
from app.services.vm_service import VmService

router = APIRouter(prefix="/vms", tags=["vms"])


@router.post("", response_model=VmResponse, status_code=201)
async def create_vm(
    payload: VmCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a monitored VM metadata record for the authenticated user."""
    return await VmService.create_vm(db, current_user, payload, request)


@router.get("", response_model=VmListResponse)
async def list_vms(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)) -> VmListResponse:
    """List monitored VM metadata records for the authenticated user."""
    items = await VmService.list_vms(db, current_user)
    return VmListResponse(items=items)


@router.get("/{vm_id}", response_model=VmResponse)
async def get_vm(vm_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Return one VM metadata record if it belongs to the authenticated user."""
    return await VmService.get_owned_vm(db, current_user, vm_id)


@router.put("/{vm_id}", response_model=VmResponse)
async def update_vm(
    vm_id: UUID,
    payload: VmUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update one VM metadata record owned by the authenticated user."""
    return await VmService.update_vm(db, current_user, vm_id, payload, request)


@router.delete("/{vm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vm(
    vm_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Soft delete one VM metadata record owned by the authenticated user."""
    await VmService.delete_vm(db, current_user, vm_id, request)


@router.post("/{vm_id}/agent-package", response_model=AgentPackageResponse)
async def generate_agent_package(
    vm_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentPackageResponse:
    """Generate a downloadable OpenTelemetry Collector agent package for one VM."""
    return await AgentService.generate_package(db, current_user, vm_id, request)


@router.post("/{vm_id}/agent-uninstall-script", response_model=AgentScriptResponse)
async def generate_agent_uninstall_script(
    vm_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentScriptResponse:
    """Generate a time-limited uninstall script for one VM."""
    return await AgentService.generate_uninstall_script(db, current_user, vm_id, request)


@router.get("/{vm_id}/agent-package/download")
async def download_agent_package(
    vm_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download the latest generated agent package for one VM and mark it downloaded."""
    package = await AgentService.get_latest_package(db, current_user, vm_id)
    await AgentService.mark_package_downloaded(db, current_user, package, request)
    return FileResponse(
        path=Path(package.package_path),
        filename=package.package_name,
        media_type=AgentService.media_type_for_package(package.package_name),
    )


@router.get("/{vm_id}/agent-status", response_model=AgentStatusResponse)
async def get_agent_status(
    vm_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the latest known OpenTelemetry agent status for one VM."""
    return await AgentService.get_agent_status(db, current_user, vm_id)


@router.get("/{vm_id}/dashboard", response_model=GrafanaDashboardResponse | None)
async def get_dashboard(
    vm_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the stored Grafana dashboard mapping for one VM."""
    return await GrafanaService.get_dashboard_mapping(db, current_user, vm_id)


@router.get("/{vm_id}/dashboard/panels", response_model=list[GrafanaPanelResponse])
async def list_dashboard_panels(
    vm_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list:
    """Return stored Grafana iframe panel mappings for one VM."""
    return await GrafanaService.list_dashboard_panels(db, current_user, vm_id)


@router.get("/{vm_id}/dashboard-panels", response_model=VmDashboardPanelsResponse)
async def get_vm_dashboard_panels(
    vm_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VmDashboardPanelsResponse:
    """Return generated Grafana d-solo iframe panels for one owned VM."""
    return await GrafanaService.get_vm_dashboard_panels(db, current_user, vm_id)
