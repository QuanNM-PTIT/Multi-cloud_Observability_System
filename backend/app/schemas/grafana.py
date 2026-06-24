from datetime import datetime
from uuid import UUID

from app.schemas.base import TimezoneAwareResponse


class GrafanaDashboardResponse(TimezoneAwareResponse):
    id: UUID
    vm_id: UUID | None
    dashboard_uid: str | None
    dashboard_url: str | None
    mapping_type: str
    status: str
    created_at: datetime
    updated_at: datetime | None


class GrafanaPanelResponse(TimezoneAwareResponse):
    id: UUID
    vm_id: UUID | None
    dashboard_uid: str
    panel_id: int
    panel_name: str
    panel_type: str
    iframe_url: str
    is_default: bool
    status: str
