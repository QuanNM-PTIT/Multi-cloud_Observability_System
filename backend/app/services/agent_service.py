from datetime import datetime
from pathlib import Path
import hashlib
import secrets
import tempfile
import uuid
import zipfile

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_agent_token
from app.models.agent import AgentInstallEvent, AgentPackage, AgentToken, VmAgentStatus
from app.models.user import User
from app.models.vm import VmInstance
from app.schemas.agent import AgentPackageResponse
from app.services.audit_service import AuditService
from app.services.vm_service import VmService


class AgentService:
    @staticmethod
    def generate_raw_token() -> str:
        """Generate a one-time raw agent token with a readable debugging prefix."""
        prefix = secrets.token_hex(4)
        secret = secrets.token_urlsafe(32)
        return f"agt_{prefix}.{secret}"

    @staticmethod
    def token_prefix(raw_token: str) -> str:
        """Extract the display-safe token prefix stored for debugging."""
        return raw_token.split(".", 1)[0]

    @staticmethod
    def calculate_file_sha256(path: Path) -> str:
        """Calculate a SHA-256 checksum for a generated package file."""
        digest = hashlib.sha256()
        with path.open("rb") as package_file:
            for chunk in iter(lambda: package_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def render_config_yaml(vm: VmInstance, user: User, raw_token: str) -> str:
        """Render the OpenTelemetry Collector config for one VM agent package."""
        settings = get_settings()
        environment = vm.environment or "default"
        return f"""receivers:
  hostmetrics:
    collection_interval: 30s
    scrapers:
      cpu:
      memory:
      disk:
      filesystem:
      network:
      load:

processors:
  memory_limiter:
    check_interval: 5s
    limit_mib: 256
  resource:
    attributes:
      - key: user.id
        value: "{user.id}"
        action: upsert
      - key: user.name
        value: "{user.username}"
        action: upsert
      - key: vm.id
        value: "{vm.id}"
        action: upsert
      - key: host.name
        value: "{vm.vm_name}"
        action: upsert
      - key: cloud.provider
        value: "{vm.cloud_provider}"
        action: upsert
      - key: deployment.environment
        value: "{environment}"
        action: upsert
  batch:

exporters:
  prometheusremotewrite:
    endpoint: "{settings.public_ingest_url}"
    headers:
      Authorization: "Bearer {raw_token}"

service:
  pipelines:
    metrics:
      receivers: [hostmetrics]
      processors: [memory_limiter, resource, batch]
      exporters: [prometheusremotewrite]
"""

    @staticmethod
    def render_install_script() -> str:
        """Render a Linux install script for the OpenTelemetry Collector package."""
        return """#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/masterptit-otel-agent"
SERVICE_FILE="/etc/systemd/system/masterptit-otel-agent.service"

sudo mkdir -p "${INSTALL_DIR}"
sudo cp config.yaml "${INSTALL_DIR}/config.yaml"

if ! command -v otelcol-contrib >/dev/null 2>&1; then
  echo "Please install otelcol-contrib before running this script."
  exit 1
fi

sudo tee "${SERVICE_FILE}" >/dev/null <<'UNIT'
[Unit]
Description=MasterPTIT OpenTelemetry Collector Agent
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/otelcol-contrib --config=/opt/masterptit-otel-agent/config.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now masterptit-otel-agent
sudo systemctl status masterptit-otel-agent --no-pager
"""

    @staticmethod
    def render_uninstall_script() -> str:
        """Render a Linux uninstall script for the OpenTelemetry Collector service."""
        return """#!/usr/bin/env bash
set -euo pipefail

sudo systemctl disable --now masterptit-otel-agent || true
sudo rm -f /etc/systemd/system/masterptit-otel-agent.service
sudo rm -rf /opt/masterptit-otel-agent
sudo systemctl daemon-reload
"""

    @staticmethod
    def render_readme(vm: VmInstance) -> str:
        """Render operator instructions included inside the generated agent package."""
        return f"""# MasterPTIT VM Agent Package

VM ID: {vm.id}
VM Name: {vm.vm_name}
Cloud Provider: {vm.cloud_provider}

## Install

1. Copy this zip file to the target Linux VM.
2. Extract the package.
3. Install `otelcol-contrib` if it is not already installed.
4. Run `chmod +x install.sh uninstall.sh`.
5. Run `sudo ./install.sh`.

## Uninstall

Run `sudo ./uninstall.sh`.
"""

    @staticmethod
    def write_package_archive(package_path: Path, vm: VmInstance, user: User, raw_token: str) -> tuple[str, int]:
        """Write the package files to a zip archive and return checksum metadata."""
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            files = {
                "config.yaml": AgentService.render_config_yaml(vm, user, raw_token),
                "install.sh": AgentService.render_install_script(),
                "uninstall.sh": AgentService.render_uninstall_script(),
                "README.md": AgentService.render_readme(vm),
            }
            manifest_lines: list[str] = []
            for file_name, content in files.items():
                file_path = temp_dir / file_name
                file_path.write_text(content, encoding="utf-8")
                manifest_lines.append(f"{hashlib.sha256(content.encode()).hexdigest()}  {file_name}")
            (temp_dir / "checksum.txt").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

            with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file_path in sorted(temp_dir.iterdir()):
                    archive.write(file_path, arcname=file_path.name)

        checksum = AgentService.calculate_file_sha256(package_path)
        return checksum, package_path.stat().st_size

    @staticmethod
    async def generate_package(db: AsyncSession, user: User, vm_id: uuid.UUID, request: Request) -> AgentPackageResponse:
        """Generate a new agent package and revoke any previous active token for the VM."""
        vm = await VmService.get_owned_vm(db, user, vm_id)
        settings = get_settings()
        package_dir = settings.agent_package_dir
        package_dir.mkdir(parents=True, exist_ok=True)

        active_tokens = await db.execute(
            select(AgentToken).where(AgentToken.vm_id == vm.id, AgentToken.status == "ACTIVE")
        )
        for token in active_tokens.scalars().all():
            token.status = "REVOKED"
            token.revoked_at = datetime.utcnow()
        await db.flush()

        raw_token = AgentService.generate_raw_token()
        token = AgentToken(
            vm_id=vm.id,
            token_hash=hash_agent_token(raw_token),
            token_prefix=AgentService.token_prefix(raw_token),
        )
        db.add(token)

        package_name = f"agent-package-{vm.id}.zip"
        package_path = package_dir / package_name
        checksum, file_size = AgentService.write_package_archive(package_path, vm, user, raw_token)

        package = AgentPackage(
            vm_id=vm.id,
            generated_by=user.id,
            package_name=package_name,
            package_path=str(package_path),
            checksum=checksum,
            file_size_bytes=file_size,
            os_type=vm.os_type,
            agent_version="otelcol-contrib",
        )
        db.add(package)
        await db.flush()
        vm.monitoring_status = "PACKAGE_GENERATED"
        db.add(AgentInstallEvent(vm_id=vm.id, package_id=package.id, event_type="PACKAGE_GENERATED", event_status="SUCCESS"))
        AuditService.add_log(
            db,
            action="GENERATE_AGENT_PACKAGE",
            user_id=user.id,
            target_type="agent_packages",
            target_id=package.id,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            detail_json={"vm_id": str(vm.id), "token_prefix": token.token_prefix},
        )
        await db.commit()
        await db.refresh(package)
        return AgentPackageResponse(
            vm_id=vm.id,
            package_id=package.id,
            package_name=package.package_name,
            download_url=f"/api/vms/{vm.id}/agent-package/download",
            checksum=package.checksum,
            file_size_bytes=package.file_size_bytes,
        )

    @staticmethod
    async def get_latest_package(db: AsyncSession, user: User, vm_id: uuid.UUID) -> AgentPackage:
        """Return the latest generated package for an owned VM."""
        vm = await VmService.get_owned_vm(db, user, vm_id)
        result = await db.execute(
            select(AgentPackage)
            .where(AgentPackage.vm_id == vm.id, AgentPackage.status.in_(["GENERATED", "DOWNLOADED"]))
            .order_by(AgentPackage.created_at.desc())
        )
        package = result.scalars().first()
        if not package:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent package not found")
        if not Path(package.package_path).exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent package file is missing")
        return package

    @staticmethod
    async def mark_package_downloaded(db: AsyncSession, user: User, package: AgentPackage, request: Request) -> None:
        """Mark a package as downloaded and update the VM monitoring lifecycle state."""
        vm = await VmService.get_owned_vm(db, user, package.vm_id)
        package.status = "DOWNLOADED"
        package.downloaded_at = datetime.utcnow()
        vm.monitoring_status = "DOWNLOADED"
        db.add(
            AgentInstallEvent(
                vm_id=vm.id,
                package_id=package.id,
                event_type="PACKAGE_DOWNLOADED",
                event_status="SUCCESS",
                source_ip=request.client.host if request.client else None,
            )
        )
        AuditService.add_log(
            db,
            action="DOWNLOAD_AGENT_PACKAGE",
            user_id=user.id,
            target_type="agent_packages",
            target_id=package.id,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()

    @staticmethod
    async def get_agent_status(db: AsyncSession, user: User, vm_id: uuid.UUID) -> VmAgentStatus:
        """Return the latest known agent status row for an owned VM."""
        vm = await VmService.get_owned_vm(db, user, vm_id)
        result = await db.execute(select(VmAgentStatus).where(VmAgentStatus.vm_id == vm.id))
        agent_status = result.scalar_one_or_none()
        if not agent_status:
            agent_status = VmAgentStatus(vm_id=vm.id)
            db.add(agent_status)
            await db.commit()
            await db.refresh(agent_status)
        return agent_status

    @staticmethod
    async def validate_raw_token(db: AsyncSession, raw_token: str) -> AgentToken:
        """Validate a raw agent bearer token and update heartbeat metadata."""
        token_hash = hash_agent_token(raw_token)
        result = await db.execute(select(AgentToken).where(AgentToken.token_hash == token_hash, AgentToken.status == "ACTIVE"))
        token = result.scalar_one_or_none()
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")
        now = datetime.utcnow()
        if token.expired_at and token.expired_at <= now:
            token.status = "EXPIRED"
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Agent token expired")

        vm_result = await db.execute(select(VmInstance).where(VmInstance.id == token.vm_id, VmInstance.deleted.is_(False)))
        vm = vm_result.scalar_one_or_none()
        if not vm:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="VM is not active")

        status_result = await db.execute(select(VmAgentStatus).where(VmAgentStatus.vm_id == vm.id))
        agent_status = status_result.scalar_one_or_none()
        if not agent_status:
            agent_status = VmAgentStatus(vm_id=vm.id)
            db.add(agent_status)

        token.last_used_at = now
        vm.last_seen_at = now
        vm.monitoring_status = "RUNNING"
        vm.is_monitoring = True
        agent_status.agent_status = "RUNNING"
        agent_status.last_seen_at = now
        agent_status.last_heartbeat_at = now
        agent_status.updated_at = now
        await db.commit()
        return token
