from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AgentPackageResponse(BaseModel):
    vm_id: UUID
    package_id: UUID
    package_name: str
    download_url: str
    checksum: str | None
    file_size_bytes: int | None


class AgentStatusResponse(BaseModel):
    vm_id: UUID
    agent_status: str
    agent_version: str | None
    service_status: str | None
    last_seen_at: datetime | None
    last_heartbeat_at: datetime | None
    last_error_message: str | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class AgentTokenValidationResponse(BaseModel):
    valid: bool
    vm_id: UUID
