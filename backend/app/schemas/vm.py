from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.base import TimezoneAwareResponse

CloudProvider = Literal["viettel-idc", "aws", "gcp", "azure", "digitalocean", "openstack", "private-cloud", "other"]
MonitoringStatus = Literal["NOT_INSTALLED", "PACKAGE_GENERATED", "DOWNLOADED", "INSTALLING", "RUNNING", "STOPPED", "ERROR", "NO_DATA"]


class VmCreateRequest(BaseModel):
    vm_name: str = Field(min_length=1, max_length=255)
    cloud_provider: CloudProvider
    public_ip: str | None = Field(default=None, max_length=50)
    private_ip: str | None = Field(default=None, max_length=50)
    os_type: str = Field(min_length=1, max_length=50)
    os_version: str | None = Field(default=None, max_length=100)
    environment: str | None = Field(default=None, max_length=50)
    description: str | None = None


class VmUpdateRequest(BaseModel):
    vm_name: str | None = Field(default=None, min_length=1, max_length=255)
    cloud_provider: CloudProvider | None = None
    public_ip: str | None = Field(default=None, max_length=50)
    private_ip: str | None = Field(default=None, max_length=50)
    os_type: str | None = Field(default=None, min_length=1, max_length=50)
    os_version: str | None = Field(default=None, max_length=100)
    environment: str | None = Field(default=None, max_length=50)
    description: str | None = None
    is_monitoring: bool | None = None
    monitoring_status: MonitoringStatus | None = None


class VmResponse(TimezoneAwareResponse):
    id: UUID
    vm_name: str
    cloud_provider: str
    public_ip: str | None
    private_ip: str | None
    os_type: str
    os_version: str | None
    environment: str | None
    description: str | None
    monitoring_status: str
    is_monitoring: bool
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class VmListResponse(TimezoneAwareResponse):
    items: list[VmResponse]
