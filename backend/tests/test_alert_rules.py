from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.alert import AlertmanagerWebhookPayload
from app.services.alert_service import AlertDispatchService, AlertRuleService, ReceiverService, _is_discord_webhook


def test_render_vmalert_rules_includes_backend_routing_labels() -> None:
    """Verify generated vmalert rules carry labels used by backend dispatch routing."""
    rule_id = uuid4()
    vm_id = uuid4()
    user_id = uuid4()
    rule = SimpleNamespace(
        id=rule_id,
        user_id=user_id,
        vm_id=vm_id,
        rule_name="High CPU",
        rule_code="HighCpu",
        metric_name="cpu",
        promql_expr='avg(rate(cpu_seconds_total{vm_id="abc"}[5m])) > 0.8',
        condition_text="CPU over threshold",
        duration="5m",
        severity="warning",
    )

    rendered = AlertRuleService._render_vmalert_rules([rule])

    assert 'alert: "HighCpu"' in rendered
    assert f'rule_id: "{rule_id}"' in rendered
    assert f'user_id: "{user_id}"' in rendered
    assert f'vm_id: "{vm_id}"' in rendered
    assert rendered.index("        labels:") < rendered.index(f'          vm_id: "{vm_id}"')
    assert rendered.index(f'          vm_id: "{vm_id}"') < rendered.index("        annotations:")


def test_render_vmalert_rules_empty_group_when_no_enabled_rules() -> None:
    """Verify an empty rule set still renders a valid YAML document."""
    assert AlertRuleService._render_vmalert_rules([]) == "groups: []\n"


def test_discord_webhook_detection_accepts_discord_api_urls() -> None:
    """Verify Discord webhook URLs are detected before dispatch payload formatting."""
    assert _is_discord_webhook("https://discord.com/api/webhooks/123/token")
    assert _is_discord_webhook("https://discordapp.com/api/webhooks/123/token")
    assert not _is_discord_webhook("https://example.com/api/webhooks/123/token")


def test_receiver_verification_uses_discord_embed_payload_for_discord_webhooks() -> None:
    """Verify Discord receiver verification is sent as a polished embed payload."""
    receiver = SimpleNamespace(
        id=uuid4(),
        channel_name="Ops Discord",
        receiver="https://discord.com/api/webhooks/123/token",
    )

    payload = ReceiverService._build_verification_payload(
        receiver,
        "123456",
        datetime(2026, 7, 1, 8, 30, tzinfo=timezone.utc),
    )

    assert payload["username"] == "Observability Portal"
    assert payload["allowed_mentions"] == {"parse": []}
    assert payload["embeds"][0]["title"] == "Webhook Receiver Verification"
    assert payload["embeds"][0]["fields"][0]["value"] == "`123456`"


def test_alert_dispatch_uses_discord_embed_payload_for_discord_webhooks() -> None:
    """Verify alert notifications to Discord are sent as embeds with rule context."""
    rule = SimpleNamespace(
        id=uuid4(),
        vm_id=uuid4(),
        rule_name="High CPU",
        rule_code="PortalAlert_123",
        severity="critical",
        condition_text="CPU usage >= 80% for 5m",
    )
    receiver = SimpleNamespace(receiver="https://discord.com/api/webhooks/123/token")
    vm = SimpleNamespace(vm_name="master-node", public_ip="203.0.113.10")
    source_payload = AlertmanagerWebhookPayload(
        status="firing",
        alerts=[
            {
                "status": "firing",
                "labels": {"severity": "critical", "vm_id": str(rule.vm_id)},
                "annotations": {"summary": "CPU is high", "description": "CPU crossed the configured threshold."},
                "startsAt": "2026-07-01T08:30:00Z",
                "generatorURL": "http://vmalert:8880/alert?group_id=1",
            }
        ],
    )

    payload = AlertDispatchService._build_receiver_payload(source_payload, source_payload.alerts[0], rule, receiver, vm)

    embed = payload["embeds"][0]
    assert embed["title"] == "Firing: High CPU"
    assert embed["color"] > 0
    assert any(field["name"] == "Severity" and field["value"] == "Critical" for field in embed["fields"])
    assert any(field["name"] == "VM" and field["value"] == "master-node" for field in embed["fields"])
    assert any(field["name"] == "Public IP" and field["value"] == "203.0.113.10" for field in embed["fields"])
    assert any(field["name"] == "Started at" and field["value"] == "2026-07-01 15:30:00 GMT+7" for field in embed["fields"])
    assert any(field["name"] == "Condition" and "CPU usage" in field["value"] for field in embed["fields"])
    assert not any(field["name"] == "Rule code" for field in embed["fields"])
    assert not any(field["name"] == "Source" for field in embed["fields"])
