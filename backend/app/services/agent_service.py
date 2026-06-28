from datetime import timedelta
from pathlib import Path
import hashlib
import os
import secrets
import shlex
import shutil
import tarfile
import tempfile
import uuid
import zipfile

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_agent_token
from app.core.timezone import now_utc
from app.models.agent import AgentInstallEvent, AgentPackage, AgentScriptToken, AgentToken, VmAgentStatus
from app.models.user import User
from app.models.vm import VmInstance
from app.schemas.agent import AgentPackageResponse, AgentScriptResponse
from app.services.audit_service import AuditService
from app.services.vm_service import VmService

SCRIPT_TOKEN_TTL_SECONDS = 15 * 60


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
    def is_windows_os(os_type: str) -> bool:
        """Return whether the VM OS should receive a PowerShell script."""
        return "windows" in os_type.lower()

    @staticmethod
    def public_api_base_url() -> str:
        """Build the public API base URL used by VM-side copy-paste scripts."""
        settings = get_settings()
        return f"{settings.public_portal_url.rstrip('/')}{settings.api_prefix}"

    @staticmethod
    def package_extension_for_os(os_type: str) -> str:
        """Return the archive extension that avoids extra install tools on the target OS."""
        return ".zip" if AgentService.is_windows_os(os_type) else ".tar.gz"

    @staticmethod
    def media_type_for_package(package_name: str) -> str:
        """Return a download media type based on the generated package extension."""
        return "application/zip" if package_name.endswith(".zip") else "application/gzip"

    @staticmethod
    def find_agent_source(os_type: str) -> Path | None:
        """Find the uploaded agent artifact that should be bundled for the target OS."""
        source_dir = get_settings().agent_source_dir
        candidates = (
            [
                "agent_windows.exe",
                "otelcol.exe",
                "otelcol-contrib.exe",
                "agent_windows.zip",
                "agent_windows.tar.gz",
                "agent_windows.tgz",
            ]
            if AgentService.is_windows_os(os_type)
            else [
                "agent_linux",
                "otelcol",
                "otelcol-contrib",
                "agent_linux.tar.gz",
                "agent_linux.tgz",
                "agent_linux.deb",
                "agent_linux.rpm",
            ]
        )
        for candidate in candidates:
            path = source_dir / candidate
            if path.is_file():
                return path
        return None

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
    resource_to_telemetry_conversion:
      enabled: true

service:
  pipelines:
    metrics:
      receivers: [hostmetrics]
      processors: [memory_limiter, resource, batch]
      exporters: [prometheusremotewrite]
"""

    @staticmethod
    def render_linux_package_install_script() -> str:
        """Render a Linux install script for the OpenTelemetry Collector package."""
        return """#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/masterptit-otel-agent"
SERVICE_FILE="/etc/systemd/system/masterptit-otel-agent.service"
BIN_PATH="${INSTALL_DIR}/otelcol"

sudo mkdir -p "${INSTALL_DIR}"
sudo cp config.yaml "${INSTALL_DIR}/config.yaml"

AGENT_ARCHIVE="$(find . -maxdepth 1 -type f \( -name '*.tar.gz' -o -name '*.tgz' \) | head -n 1)"
AGENT_DEB="$(find . -maxdepth 1 -type f -name '*.deb' | head -n 1)"
AGENT_RPM="$(find . -maxdepth 1 -type f -name '*.rpm' | head -n 1)"

if [ -f ./agent_linux ] || [ -f ./otelcol ] || [ -f ./otelcol-contrib ]; then
  AGENT_BIN="./agent_linux"
  [ -f ./otelcol ] && AGENT_BIN="./otelcol"
  [ -f ./otelcol-contrib ] && AGENT_BIN="./otelcol-contrib"
  sudo cp "${AGENT_BIN}" "${BIN_PATH}"
  sudo chmod 0755 "${BIN_PATH}"
elif [ -n "${AGENT_ARCHIVE}" ]; then
  EXTRACT_DIR="$(mktemp -d)"
  tar -xzf "${AGENT_ARCHIVE}" -C "${EXTRACT_DIR}"
  AGENT_BIN="$(find "${EXTRACT_DIR}" -type f \( -name otelcol -o -name otelcol-contrib -o -name agent_linux \) | head -n 1)"
  if [ -z "${AGENT_BIN}" ]; then
    echo "Linux agent archive does not contain otelcol, otelcol-contrib, or agent_linux."
    exit 1
  fi
  sudo cp "${AGENT_BIN}" "${BIN_PATH}"
  sudo chmod 0755 "${BIN_PATH}"
  rm -rf "${EXTRACT_DIR}"
elif [ -n "${AGENT_DEB}" ]; then
  sudo dpkg -i "${AGENT_DEB}"
  SYSTEM_BIN="$(command -v otelcol || command -v otelcol-contrib || true)"
  if [ -z "${SYSTEM_BIN}" ]; then
    echo "Installed DEB but could not find otelcol or otelcol-contrib."
    exit 1
  fi
  sudo cp "${SYSTEM_BIN}" "${BIN_PATH}"
elif [ -n "${AGENT_RPM}" ]; then
  if command -v rpm >/dev/null 2>&1; then
    sudo rpm -Uvh --replacepkgs "${AGENT_RPM}"
    SYSTEM_BIN="$(command -v otelcol || command -v otelcol-contrib || true)"
    if [ -z "${SYSTEM_BIN}" ]; then
      echo "Installed RPM but could not find otelcol or otelcol-contrib."
      exit 1
    fi
    sudo cp "${SYSTEM_BIN}" "${BIN_PATH}"
  else
    echo "The bundled Linux agent is an RPM package. This VM cannot install RPM files without rpm tooling. Use a .deb or raw Linux binary for Ubuntu."
    exit 1
  fi
else
  echo "No bundled Linux agent was found in the package."
  exit 1
fi

sudo tee "${SERVICE_FILE}" >/dev/null <<'UNIT'
[Unit]
Description=MasterPTIT OpenTelemetry Collector Agent
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/opt/masterptit-otel-agent/otelcol --config=/opt/masterptit-otel-agent/config.yaml
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
    def render_linux_package_uninstall_script() -> str:
        """Render a Linux uninstall script for the OpenTelemetry Collector service."""
        return """#!/usr/bin/env bash
set -euo pipefail

sudo systemctl disable --now masterptit-otel-agent || true
sudo rm -f /etc/systemd/system/masterptit-otel-agent.service
sudo rm -rf /opt/masterptit-otel-agent
sudo systemctl daemon-reload
"""

    @staticmethod
    def render_windows_package_install_script() -> str:
        """Render a Windows PowerShell install script for the OpenTelemetry Collector package."""
        return """$ErrorActionPreference = "Stop"

$InstallDir = "C:\\ProgramData\\MasterPTIT\\otel-agent"
$ConfigPath = Join-Path $InstallDir "config.yaml"
$CollectorPath = Join-Path $InstallDir "otelcol.exe"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Force ".\\config.yaml" $ConfigPath

$BundledExe = Get-ChildItem -Path "." -Filter "*.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $BundledExe) {
    $BundledArchive = Get-ChildItem -Path "." -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name.EndsWith(".zip") -or $_.Name.EndsWith(".tar.gz") -or $_.Name.EndsWith(".tgz") } |
        Select-Object -First 1
    if (-not $BundledArchive) {
        throw "No bundled Windows agent executable or archive was found in the package."
    }
    $ExtractDir = Join-Path $env:TEMP ("masterptit-agent-bin-" + [Guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
    if ($BundledArchive.Name.EndsWith(".zip")) {
        Expand-Archive -Force -Path $BundledArchive.FullName -DestinationPath $ExtractDir
    } else {
        tar -xzf $BundledArchive.FullName -C $ExtractDir
    }
    $BundledExe = Get-ChildItem -Path $ExtractDir -Filter "*.exe" -File -Recurse | Select-Object -First 1
    if (-not $BundledExe) {
        throw "Bundled Windows agent archive does not contain an .exe file."
    }
}
Copy-Item -Force $BundledExe.FullName $CollectorPath

$Service = Get-Service -Name "masterptit-otel-agent" -ErrorAction SilentlyContinue
if ($Service) {
    Stop-Service -Name "masterptit-otel-agent" -ErrorAction SilentlyContinue
    sc.exe delete "masterptit-otel-agent" | Out-Null
}

sc.exe create "masterptit-otel-agent" binPath= "`"$CollectorPath`" --config=`"$ConfigPath`"" start= auto | Out-Null
Start-Service -Name "masterptit-otel-agent"
Get-Service -Name "masterptit-otel-agent"
"""

    @staticmethod
    def render_windows_package_uninstall_script() -> str:
        """Render a Windows PowerShell uninstall script for the OpenTelemetry Collector service."""
        return """$ErrorActionPreference = "Stop"

$Service = Get-Service -Name "masterptit-otel-agent" -ErrorAction SilentlyContinue
if ($Service) {
    Stop-Service -Name "masterptit-otel-agent" -ErrorAction SilentlyContinue
    sc.exe delete "masterptit-otel-agent" | Out-Null
}

Remove-Item -Recurse -Force "C:\\ProgramData\\MasterPTIT\\otel-agent" -ErrorAction SilentlyContinue
"""

    @staticmethod
    def render_readme(vm: VmInstance) -> str:
        """Render operator instructions included inside the generated agent package."""
        return f"""# MasterPTIT VM Agent Package

VM ID: {vm.id}
VM Name: {vm.vm_name}
Cloud Provider: {vm.cloud_provider}

## Install

1. Copy this package file to the target VM.
2. Extract the package.
3. Run `chmod +x install.sh uninstall.sh`.
4. Run `sudo ./install.sh`.

## Uninstall

Run `sudo ./uninstall.sh`.
"""

    @staticmethod
    def write_package_archive(package_path: Path, vm: VmInstance, user: User, raw_token: str) -> tuple[str, int]:
        """Write package files to an OS-appropriate archive and return checksum metadata."""
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            files = {
                "config.yaml": AgentService.render_config_yaml(vm, user, raw_token),
                "README.md": AgentService.render_readme(vm),
            }
            if AgentService.is_windows_os(vm.os_type):
                files["install.ps1"] = AgentService.render_windows_package_install_script()
                files["uninstall.ps1"] = AgentService.render_windows_package_uninstall_script()
            else:
                files["install.sh"] = AgentService.render_linux_package_install_script()
                files["uninstall.sh"] = AgentService.render_linux_package_uninstall_script()
            manifest_lines: list[str] = []
            for file_name, content in files.items():
                file_path = temp_dir / file_name
                file_path.write_text(content, encoding="utf-8")
                manifest_lines.append(f"{hashlib.sha256(content.encode()).hexdigest()}  {file_name}")
            agent_source = AgentService.find_agent_source(vm.os_type)
            if agent_source:
                agent_target = temp_dir / agent_source.name
                shutil.copy2(agent_source, agent_target)
                manifest_lines.append(f"{AgentService.calculate_file_sha256(agent_target)}  {agent_target.name}")
            (temp_dir / "checksum.txt").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

            if package_path.name.endswith(".zip"):
                with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for file_path in sorted(temp_dir.iterdir()):
                        archive.write(file_path, arcname=file_path.name)
            else:
                with tarfile.open(package_path, "w:gz") as archive:
                    for file_path in sorted(temp_dir.iterdir()):
                        archive.add(file_path, arcname=file_path.name)

        checksum = AgentService.calculate_file_sha256(package_path)
        return checksum, package_path.stat().st_size

    @staticmethod
    def render_linux_install_bootstrap_script(raw_script_token: str) -> str:
        """Render a one-line Linux installer command that downloads the package and verifies success."""
        api_base_url = AgentService.public_api_base_url()
        script = (
            "set -euo pipefail; "
            f"API_BASE_URL={shlex.quote(api_base_url)}; "
            f"SCRIPT_TOKEN={shlex.quote(raw_script_token)}; "
            'WORK_DIR="$(mktemp -d)"; '
            'PACKAGE_FILE="${WORK_DIR}/agent-package.tar.gz"; '
            'cleanup(){ rm -rf "${WORK_DIR}"; }; '
            "trap cleanup EXIT; "
            'command -v curl >/dev/null 2>&1 || { echo "curl is required"; exit 1; }; '
            'command -v tar >/dev/null 2>&1 || { echo "tar is required"; exit 1; }; '
            'curl -fsSL -H "Authorization: Bearer ${SCRIPT_TOKEN}" "${API_BASE_URL}/agent-scripts/package/download" -o "${PACKAGE_FILE}"; '
            'mkdir -p "${WORK_DIR}/package"; '
            'tar -xzf "${PACKAGE_FILE}" -C "${WORK_DIR}/package"; '
            'cd "${WORK_DIR}/package"; '
            "chmod +x install.sh uninstall.sh; "
            "sudo ./install.sh; "
            'curl -fsS -X POST -H "Authorization: Bearer ${SCRIPT_TOKEN}" "${API_BASE_URL}/agent-scripts/install/verify" >/dev/null; '
            'echo "MasterPTIT observability agent installed successfully."'
        )
        return f"bash -lc {shlex.quote(script)}"

    @staticmethod
    def render_windows_install_bootstrap_script(raw_script_token: str) -> str:
        """Render a one-line PowerShell installer command that downloads the package and verifies success."""
        api_base_url = AgentService.public_api_base_url()
        script = (
            "$ErrorActionPreference='Stop'; "
            f"$ApiBaseUrl='{api_base_url}'; "
            f"$ScriptToken='{raw_script_token}'; "
            "$WorkDir=Join-Path $env:TEMP ('masterptit-agent-' + [Guid]::NewGuid().ToString()); "
            "$PackageFile=Join-Path $WorkDir 'agent-package.zip'; "
            "New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null; "
            "try { "
            "Invoke-WebRequest -Headers @{ Authorization = ('Bearer ' + $ScriptToken) } -Uri ($ApiBaseUrl + '/agent-scripts/package/download') -OutFile $PackageFile; "
            "Expand-Archive -Force -Path $PackageFile -DestinationPath (Join-Path $WorkDir 'package'); "
            "Set-Location (Join-Path $WorkDir 'package'); "
            ".\\install.ps1; "
            "Invoke-RestMethod -Method Post -Headers @{ Authorization = ('Bearer ' + $ScriptToken) } -Uri ($ApiBaseUrl + '/agent-scripts/install/verify') | Out-Null; "
            "Write-Host 'MasterPTIT observability agent installed successfully.' "
            "} finally { "
            "Remove-Item -Recurse -Force $WorkDir -ErrorAction SilentlyContinue "
            "}"
        )
        return f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{script}"'

    @staticmethod
    def render_linux_uninstall_bootstrap_script(raw_script_token: str) -> str:
        """Render a one-line Linux uninstaller command that verifies success."""
        api_base_url = AgentService.public_api_base_url()
        script = (
            "set -euo pipefail; "
            f"API_BASE_URL={shlex.quote(api_base_url)}; "
            f"SCRIPT_TOKEN={shlex.quote(raw_script_token)}; "
            "sudo systemctl disable --now masterptit-otel-agent || true; "
            "sudo rm -f /etc/systemd/system/masterptit-otel-agent.service; "
            "sudo rm -rf /opt/masterptit-otel-agent; "
            "sudo systemctl daemon-reload; "
            'curl -fsS -X POST -H "Authorization: Bearer ${SCRIPT_TOKEN}" "${API_BASE_URL}/agent-scripts/uninstall/verify" >/dev/null; '
            'echo "MasterPTIT observability agent uninstalled successfully."'
        )
        return f"bash -lc {shlex.quote(script)}"

    @staticmethod
    def render_windows_uninstall_bootstrap_script(raw_script_token: str) -> str:
        """Render a one-line PowerShell uninstaller command that verifies success."""
        api_base_url = AgentService.public_api_base_url()
        script = (
            "$ErrorActionPreference='Stop'; "
            f"$ApiBaseUrl='{api_base_url}'; "
            f"$ScriptToken='{raw_script_token}'; "
            "$Service=Get-Service -Name 'masterptit-otel-agent' -ErrorAction SilentlyContinue; "
            "if ($Service) { Stop-Service -Name 'masterptit-otel-agent' -ErrorAction SilentlyContinue; sc.exe delete 'masterptit-otel-agent' | Out-Null }; "
            "Remove-Item -Recurse -Force 'C:\\ProgramData\\MasterPTIT\\otel-agent' -ErrorAction SilentlyContinue; "
            "Invoke-RestMethod -Method Post -Headers @{ Authorization = ('Bearer ' + $ScriptToken) } -Uri ($ApiBaseUrl + '/agent-scripts/uninstall/verify') | Out-Null; "
            "Write-Host 'MasterPTIT observability agent uninstalled successfully.'"
        )
        return f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{script}"'

    @staticmethod
    async def create_script_token(
        db: AsyncSession,
        vm: VmInstance,
        action: str,
        package: AgentPackage | None = None,
    ) -> tuple[AgentScriptToken, str]:
        """Create a one-time script token after revoking older active tokens for the same VM action."""
        active_tokens = await db.execute(
            select(AgentScriptToken).where(
                AgentScriptToken.vm_id == vm.id,
                AgentScriptToken.action == action,
                AgentScriptToken.status == "ACTIVE",
            )
        )
        for token in active_tokens.scalars().all():
            token.status = "REVOKED"
            token.revoked_at = now_utc()
        await db.flush()

        raw_token = AgentService.generate_raw_token().replace("agt_", "scr_", 1)
        expires_at = now_utc() + timedelta(seconds=SCRIPT_TOKEN_TTL_SECONDS)
        token = AgentScriptToken(
            vm_id=vm.id,
            package_id=package.id if package else None,
            token_hash=hash_agent_token(raw_token),
            token_prefix=AgentService.token_prefix(raw_token),
            action=action,
            os_type=vm.os_type,
            expired_at=expires_at,
        )
        db.add(token)
        await db.flush()
        return token, raw_token

    @staticmethod
    def render_bootstrap_script(action: str, os_type: str, raw_script_token: str) -> str:
        """Render the VM-side copy-paste script for install or uninstall."""
        is_windows = AgentService.is_windows_os(os_type)
        if action == "INSTALL":
            return (
                AgentService.render_windows_install_bootstrap_script(raw_script_token)
                if is_windows
                else AgentService.render_linux_install_bootstrap_script(raw_script_token)
            )
        return (
            AgentService.render_windows_uninstall_bootstrap_script(raw_script_token)
            if is_windows
            else AgentService.render_linux_uninstall_bootstrap_script(raw_script_token)
        )

    @staticmethod
    async def generate_package(db: AsyncSession, user: User, vm_id: uuid.UUID, request: Request) -> AgentPackageResponse:
        """Generate an agent package and return a 15-minute VM-side install script."""
        vm = await VmService.get_owned_vm(db, user, vm_id)
        settings = get_settings()
        package_dir = settings.agent_package_dir
        package_dir.mkdir(parents=True, exist_ok=True)

        active_tokens = await db.execute(
            select(AgentToken).where(AgentToken.vm_id == vm.id, AgentToken.status == "ACTIVE")
        )
        for token in active_tokens.scalars().all():
            token.status = "REVOKED"
            token.revoked_at = now_utc()
        await db.flush()

        raw_token = AgentService.generate_raw_token()
        token = AgentToken(
            vm_id=vm.id,
            token_hash=hash_agent_token(raw_token),
            token_prefix=AgentService.token_prefix(raw_token),
        )
        db.add(token)

        package_name = f"agent-package-{vm.id}{AgentService.package_extension_for_os(vm.os_type)}"
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
        script_token, raw_script_token = await AgentService.create_script_token(db, vm, "INSTALL", package)
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
            detail_json={"vm_id": str(vm.id), "agent_token_prefix": token.token_prefix, "script_token_prefix": script_token.token_prefix},
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
            action="INSTALL",
            script=AgentService.render_bootstrap_script("INSTALL", vm.os_type, raw_script_token),
            script_token_expires_at=script_token.expired_at,
            expires_in_seconds=SCRIPT_TOKEN_TTL_SECONDS,
        )

    @staticmethod
    async def generate_uninstall_script(db: AsyncSession, user: User, vm_id: uuid.UUID, request: Request) -> AgentScriptResponse:
        """Generate a 15-minute VM-side uninstall script for an owned VM."""
        vm = await VmService.get_owned_vm(db, user, vm_id)
        if vm.monitoring_status in {"NOT_INSTALLED", "PACKAGE_GENERATED"} and not vm.is_monitoring:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent is not installed for this VM")

        script_token, raw_script_token = await AgentService.create_script_token(db, vm, "UNINSTALL")
        AuditService.add_log(
            db,
            action="GENERATE_AGENT_UNINSTALL_SCRIPT",
            user_id=user.id,
            target_type="vm_instances",
            target_id=vm.id,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            detail_json={"script_token_prefix": script_token.token_prefix},
        )
        await db.commit()
        return AgentScriptResponse(
            vm_id=vm.id,
            action="UNINSTALL",
            script=AgentService.render_bootstrap_script("UNINSTALL", vm.os_type, raw_script_token),
            script_token_expires_at=script_token.expired_at,
            expires_in_seconds=SCRIPT_TOKEN_TTL_SECONDS,
        )

    @staticmethod
    async def get_active_script_token(db: AsyncSession, raw_token: str, action: str | None = None) -> AgentScriptToken:
        """Validate a one-time script token and return the matching active row."""
        token_hash = hash_agent_token(raw_token)
        query = select(AgentScriptToken).where(AgentScriptToken.token_hash == token_hash, AgentScriptToken.status == "ACTIVE")
        if action:
            query = query.where(AgentScriptToken.action == action)
        result = await db.execute(query)
        token = result.scalar_one_or_none()
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive script token")
        now = now_utc()
        if token.expired_at <= now:
            token.status = "EXPIRED"
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Script token expired")
        token.last_used_at = now
        await db.flush()
        return token

    @staticmethod
    async def get_package_for_script_download(db: AsyncSession, raw_token: str) -> AgentPackage:
        """Return the package referenced by a valid install script token."""
        token = await AgentService.get_active_script_token(db, raw_token, "INSTALL")
        if not token.package_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script token has no package")
        result = await db.execute(select(AgentPackage).where(AgentPackage.id == token.package_id))
        package = result.scalar_one_or_none()
        if not package or package.status not in {"GENERATED", "DOWNLOADED"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent package not found")
        if not Path(package.package_path).exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent package file is missing")
        if package.status == "GENERATED":
            package.status = "DOWNLOADED"
            package.downloaded_at = now_utc()
            db.add(
                AgentInstallEvent(
                    vm_id=package.vm_id,
                    package_id=package.id,
                    event_type="PACKAGE_DOWNLOADED",
                    event_status="SUCCESS",
                )
            )
        await db.commit()
        return package

    @staticmethod
    async def verify_script_action(db: AsyncSession, raw_token: str, action: str, request: Request) -> dict[str, str]:
        """Verify install or uninstall success from a VM-side script and consume the script token."""
        script_token = await AgentService.get_active_script_token(db, raw_token, action)
        result = await db.execute(select(VmInstance).where(VmInstance.id == script_token.vm_id, VmInstance.deleted.is_(False)))
        vm = result.scalar_one_or_none()
        if not vm:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VM not found")
        status_result = await db.execute(select(VmAgentStatus).where(VmAgentStatus.vm_id == vm.id))
        agent_status = status_result.scalar_one_or_none()
        if not agent_status:
            agent_status = VmAgentStatus(vm_id=vm.id)
            db.add(agent_status)

        now = now_utc()
        script_token.status = "USED"
        script_token.used_at = now
        script_token.last_used_at = now

        package_id = script_token.package_id
        if action == "INSTALL":
            vm.monitoring_status = "RUNNING"
            vm.is_monitoring = True
            vm.last_seen_at = now
            agent_status.agent_status = "RUNNING"
            agent_status.service_status = "active"
            agent_status.last_seen_at = now
            agent_status.last_heartbeat_at = now
            agent_status.updated_at = now
            event_type = "INSTALLED"
            audit_action = "VERIFY_AGENT_INSTALLED"
        else:
            vm.monitoring_status = "NOT_INSTALLED"
            vm.is_monitoring = False
            agent_status.agent_status = "UNINSTALLED"
            agent_status.service_status = "inactive"
            agent_status.updated_at = now
            event_type = "UNINSTALLED"
            audit_action = "VERIFY_AGENT_UNINSTALLED"
            active_tokens = await db.execute(select(AgentToken).where(AgentToken.vm_id == vm.id, AgentToken.status == "ACTIVE"))
            for token in active_tokens.scalars().all():
                token.status = "REVOKED"
                token.revoked_at = now

        if package_id:
            package_result = await db.execute(select(AgentPackage).where(AgentPackage.id == package_id))
            package = package_result.scalar_one_or_none()
            if package:
                package.status = "REVOKED"
                package.expired_at = now
                try:
                    os.remove(package.package_path)
                except FileNotFoundError:
                    pass

        db.add(
            AgentInstallEvent(
                vm_id=vm.id,
                package_id=package_id,
                event_type=event_type,
                event_status="SUCCESS",
                source_ip=request.client.host if request.client else None,
            )
        )
        AuditService.add_log(
            db,
            action=audit_action,
            user_id=vm.user_id,
            target_type="vm_instances",
            target_id=vm.id,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            detail_json={"script_token_prefix": script_token.token_prefix},
        )
        await db.commit()
        return {"status": "ok", "action": action}

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
        package.downloaded_at = now_utc()
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
        now = now_utc()
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
