from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agent-scripts", tags=["agent-scripts"])


def extract_bearer_token(authorization: str | None) -> str:
    """Extract a VM-side one-time script token from an Authorization header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing script token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing script token")
    return token


@router.get("/package/download")
async def download_agent_package_for_script(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Download a generated package when called by a valid VM-side install script."""
    package = await AgentService.get_package_for_script_download(db, extract_bearer_token(authorization))
    return FileResponse(
        path=Path(package.package_path),
        filename=package.package_name,
        media_type=AgentService.media_type_for_package(package.package_name),
    )


@router.post("/install/verify")
async def verify_agent_install(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Mark an agent installation as successful and consume the script token."""
    return await AgentService.verify_script_action(db, extract_bearer_token(authorization), "INSTALL", request)


@router.post("/uninstall/verify")
async def verify_agent_uninstall(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Mark an agent uninstall as successful and consume the script token."""
    return await AgentService.verify_script_action(db, extract_bearer_token(authorization), "UNINSTALL", request)
