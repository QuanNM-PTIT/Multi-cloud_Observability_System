from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class GrafanaDashboardResponse(BaseModel):
    id: UUID
    vm_id: UUID | None
    dashboard_uid: str | None
    dashboard_url: str | None
    mapping_type: str
    status: str
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class GrafanaPanelResponse(BaseModel):
    id: UUID
    vm_id: UUID | None
    dashboard_uid: str
    panel_id: int
    panel_name: str
    panel_type: str
    iframe_url: str
    is_default: bool
    status: str

    model_config = {"from_attributes": True}
