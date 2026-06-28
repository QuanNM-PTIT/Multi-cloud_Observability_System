from urllib.parse import parse_qs, urlparse

from app.services.grafana_service import build_grafana_panel_url, flatten_dashboard_panels, panel_key


def test_build_grafana_panel_url_encodes_vm_variables():
    """Verify Grafana d-solo URLs include encoded VM template variables."""
    url = build_grafana_panel_url(3, "vm-123", "ITIS Web")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.path == "/d-solo/masterptit-vm-observability/masterptit-vm-observability"
    assert query["panelId"] == ["3"]
    assert query["var-vm_id"] == ["vm-123"]
    assert query["var-host_name"] == ["ITIS Web"]
    assert query["from"] == ["now-6h"]
    assert query["to"] == ["now"]
    assert query["theme"] == ["dark"]
    assert query["hideLogo"] == ["true"]


def test_flatten_dashboard_panels_excludes_rows_and_keeps_nested_panels():
    """Verify dashboard panels can be read from Grafana row/nested JSON structures."""
    panels = flatten_dashboard_panels(
        [
            {"id": 1, "type": "timeseries", "title": "CPU"},
            {"id": 2, "type": "row", "title": "System", "panels": [{"id": 3, "type": "stat", "title": "Memory"}]},
            {"type": "text", "title": "No ID"},
        ]
    )

    assert [panel["id"] for panel in panels] == [1, 3]
    assert panel_key("CPU Usage", 1) == "cpu_usage_1"
