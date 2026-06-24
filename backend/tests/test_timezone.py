from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.timezone import APP_TIMEZONE, to_app_timezone
from app.schemas.vm import VmResponse


def test_to_app_timezone_converts_utc_to_gmt7() -> None:
    """Verify UTC datetimes are converted to Asia/Ho_Chi_Minh without manual offsets."""
    source = datetime(2026, 7, 9, 8, 30, tzinfo=timezone.utc)

    converted = to_app_timezone(source)

    assert converted is not None
    assert converted.tzinfo == APP_TIMEZONE
    assert converted.isoformat().endswith("+07:00")
    assert converted.isoformat() == "2026-07-09T15:30:00+07:00"


def test_api_response_serializes_datetime_with_gmt7_offset() -> None:
    """Verify FastAPI responses serialize schema datetimes with the +07:00 offset."""
    app = FastAPI()

    @app.get("/vm", response_model=VmResponse)
    def get_vm() -> dict:
        """Return a VM response containing UTC and null datetime values."""
        return {
            "id": uuid4(),
            "vm_name": "web-server-01",
            "cloud_provider": "digitalocean",
            "public_ip": "203.0.113.10",
            "private_ip": None,
            "os_type": "linux",
            "os_version": "Ubuntu 24.04",
            "environment": "dev",
            "description": None,
            "monitoring_status": "RUNNING",
            "is_monitoring": True,
            "last_seen_at": None,
            "created_at": datetime(2026, 7, 9, 8, 30, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 7, 9, 8, 40, tzinfo=timezone.utc),
        }

    response = TestClient(app).get("/vm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["created_at"] == "2026-07-09T15:30:00+07:00"
    assert payload["updated_at"] == "2026-07-09T15:40:00+07:00"
