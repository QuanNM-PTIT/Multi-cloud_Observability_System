from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import tempfile
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_receiver_otp
from app.core.timezone import now_utc, to_app_timezone
from app.models.alert import AlertRule, AlertRuleChannel, NotificationChannel
from app.models.user import User
from app.models.vm import VmInstance
from app.schemas.alert import (
    AlertRuleCreateRequest,
    AlertRuleUpdateRequest,
    AlertmanagerWebhookPayload,
    AlertmanagerWebhookResponse,
    ReceiverCreateRequest,
    ReceiverUpdateRequest,
)
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

ALERT_METRIC_LABELS = {
    "cpu_usage_percent": "CPU usage",
    "memory_usage_percent": "Memory usage",
    "disk_usage_percent": "Disk usage",
}
DISCORD_COLOR_BRAND = 0xB9141F
DISCORD_COLOR_FIRING = 0xD92D20
DISCORD_COLOR_RESOLVED = 0x12B76A
DISCORD_COLOR_INFO = 0x667085


def _request_ip(request: Request) -> str | None:
    """Return the request IP address when FastAPI exposes it."""
    return request.client.host if request.client else None


def _receiver_response(channel: NotificationChannel) -> dict[str, Any]:
    """Convert a notification channel row into the public receiver API shape."""
    return {
        "id": channel.id,
        "receiver_name": channel.channel_name,
        "receiver_type": channel.channel_type,
        "webhook_url": channel.receiver,
        "enabled": channel.enabled,
        "alert_resend_interval_minutes": _receiver_resend_interval_minutes(channel),
        "verification_status": channel.verification_status,
        "verification_expires_at": channel.verification_expires_at,
        "verified_at": channel.verified_at,
        "last_verification_sent_at": channel.last_verification_sent_at,
        "last_verification_error": channel.last_verification_error,
        "created_at": channel.created_at,
        "updated_at": channel.updated_at,
    }


def _receiver_config(channel: NotificationChannel) -> dict[str, Any]:
    """Return receiver config JSON as a mutable dict."""
    return dict(channel.config_json or {})


def _receiver_resend_interval_minutes(channel: NotificationChannel) -> int:
    """Return a bounded receiver alert resend interval in minutes."""
    raw_value = _receiver_config(channel).get("alert_resend_interval_minutes", 15)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = 15
    return min(60, max(10, value))


def _rule_response(rule: AlertRule, receiver_ids: list[UUID]) -> dict[str, Any]:
    """Convert an alert rule row into the public alert rule API shape."""
    return {
        "id": rule.id,
        "vm_id": rule.vm_id,
        "rule_name": rule.rule_name,
        "rule_code": rule.rule_code,
        "metric_name": rule.metric_name,
        "promql_expr": rule.promql_expr,
        "condition_text": rule.condition_text,
        "duration": rule.duration,
        "severity": rule.severity,
        "enabled": rule.enabled,
        "receiver_ids": receiver_ids,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _yaml_quote(value: object) -> str:
    """Quote a scalar for the generated vmalert YAML file."""
    return json.dumps(str(value))


def _is_discord_webhook(url: str) -> bool:
    """Return whether a webhook URL belongs to Discord's webhook API."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host in {"discord.com", "www.discord.com", "discordapp.com", "www.discordapp.com"} and parsed.path.startswith("/api/webhooks/")


def _discord_text(value: object, limit: int = 1024) -> str:
    """Convert a value into a Discord-safe field string."""
    text = str(value if value is not None and value != "" else "N/A")
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _discord_field(name: str, value: object, inline: bool = True) -> dict[str, Any]:
    """Build one Discord embed field with length limits applied."""
    return {"name": _discord_text(name, 256), "value": _discord_text(value, 1024), "inline": inline}


def _discord_payload(embed: dict[str, Any]) -> dict[str, Any]:
    """Wrap one embed in the Discord webhook payload structure."""
    return {
        "username": "Observability Portal",
        "allowed_mentions": {"parse": []},
        "embeds": [embed],
    }


def _format_discord_datetime(value: object) -> str:
    """Format an Alertmanager timestamp in the application timezone for Discord fields."""
    if not value:
        return "N/A"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    local_value = to_app_timezone(parsed)
    if not local_value:
        return str(value)
    return f"{local_value:%Y-%m-%d %H:%M:%S} GMT+7"


def _title_case_status(value: object) -> str:
    """Return a human-friendly title-cased status or severity value."""
    text = str(value or "unknown").replace("_", " ").strip()
    return text[:1].upper() + text[1:].lower() if text else "Unknown"


class ReceiverService:
    @staticmethod
    async def list_receivers(db: AsyncSession, user: User) -> list[dict[str, Any]]:
        """List webhook receivers owned by the current user."""
        result = await db.execute(
            select(NotificationChannel)
            .where(
                NotificationChannel.user_id == user.id,
                NotificationChannel.channel_type == "WEBHOOK",
                NotificationChannel.deleted.is_(False),
            )
            .order_by(NotificationChannel.created_at.desc())
        )
        return [_receiver_response(channel) for channel in result.scalars().all()]

    @staticmethod
    async def get_owned_receiver(db: AsyncSession, user: User, receiver_id: UUID) -> NotificationChannel:
        """Load a webhook receiver by id and ensure it belongs to the current user."""
        result = await db.execute(
            select(NotificationChannel).where(
                NotificationChannel.id == receiver_id,
                NotificationChannel.user_id == user.id,
                NotificationChannel.channel_type == "WEBHOOK",
                NotificationChannel.deleted.is_(False),
            )
        )
        receiver = result.scalar_one_or_none()
        if not receiver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found")
        return receiver

    @staticmethod
    async def create_receiver(db: AsyncSession, user: User, payload: ReceiverCreateRequest, request: Request) -> dict[str, Any]:
        """Create a webhook receiver and send its ownership verification OTP."""
        receiver = NotificationChannel(
            user_id=user.id,
            channel_name=payload.receiver_name.strip(),
            channel_type="WEBHOOK",
            receiver=str(payload.webhook_url),
            config_json={"alert_resend_interval_minutes": payload.alert_resend_interval_minutes},
            enabled=payload.enabled,
            verification_status="PENDING",
        )
        db.add(receiver)
        await db.flush()
        AuditService.add_log(
            db,
            action="CREATE_ALERT_RECEIVER",
            user_id=user.id,
            target_type="notification_channels",
            target_id=receiver.id,
            request_ip=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
        await db.refresh(receiver)
        await ReceiverService._send_verification_otp(db, receiver)
        AuditService.add_log(
            db,
            action="SEND_ALERT_RECEIVER_OTP",
            user_id=user.id,
            target_type="notification_channels",
            target_id=receiver.id,
            request_ip=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail_json={"verification_status": receiver.verification_status},
        )
        await db.commit()
        await db.refresh(receiver)
        return _receiver_response(receiver)

    @staticmethod
    async def update_receiver(
        db: AsyncSession,
        user: User,
        receiver_id: UUID,
        payload: ReceiverUpdateRequest,
        request: Request,
    ) -> dict[str, Any]:
        """Update a webhook receiver and require re-verification when its URL changes."""
        receiver = await ReceiverService.get_owned_receiver(db, user, receiver_id)
        update_data = payload.model_dump(exclude_unset=True)
        needs_verification = False

        if "receiver_name" in update_data and update_data["receiver_name"] is not None:
            receiver.channel_name = update_data["receiver_name"].strip()
        if "enabled" in update_data and update_data["enabled"] is not None:
            receiver.enabled = update_data["enabled"]
        if "alert_resend_interval_minutes" in update_data and update_data["alert_resend_interval_minutes"] is not None:
            config = _receiver_config(receiver)
            config["alert_resend_interval_minutes"] = update_data["alert_resend_interval_minutes"]
            receiver.config_json = config
        if "webhook_url" in update_data and update_data["webhook_url"] is not None:
            next_url = str(update_data["webhook_url"])
            if next_url != receiver.receiver:
                receiver.receiver = next_url
                receiver.verification_status = "PENDING"
                receiver.verified_at = None
                receiver.verification_code_hash = None
                receiver.verification_expires_at = None
                receiver.last_verification_error = None
                needs_verification = True

        AuditService.add_log(
            db,
            action="UPDATE_ALERT_RECEIVER",
            user_id=user.id,
            target_type="notification_channels",
            target_id=receiver.id,
            request_ip=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail_json={"updated_fields": sorted(update_data.keys())},
        )
        await db.commit()
        await db.refresh(receiver)

        if needs_verification:
            await ReceiverService._send_verification_otp(db, receiver)
            await db.commit()
            await db.refresh(receiver)
        return _receiver_response(receiver)

    @staticmethod
    async def resend_verification(db: AsyncSession, user: User, receiver_id: UUID, request: Request) -> dict[str, Any]:
        """Send a fresh ownership verification OTP to an existing webhook receiver."""
        receiver = await ReceiverService.get_owned_receiver(db, user, receiver_id)
        await ReceiverService._send_verification_otp(db, receiver)
        AuditService.add_log(
            db,
            action="RESEND_ALERT_RECEIVER_OTP",
            user_id=user.id,
            target_type="notification_channels",
            target_id=receiver.id,
            request_ip=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail_json={"verification_status": receiver.verification_status},
        )
        await db.commit()
        await db.refresh(receiver)
        return _receiver_response(receiver)

    @staticmethod
    async def verify_receiver(db: AsyncSession, user: User, receiver_id: UUID, otp: str, request: Request) -> dict[str, Any]:
        """Verify a webhook receiver using the time-limited OTP sent to that webhook."""
        receiver = await ReceiverService.get_owned_receiver(db, user, receiver_id)
        if not receiver.verification_code_hash or not receiver.verification_expires_at:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Receiver has no active verification OTP")
        if receiver.verification_expires_at <= now_utc():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification OTP has expired")

        expected_hash = hash_receiver_otp(str(receiver.id), otp)
        if not hmac.compare_digest(receiver.verification_code_hash, expected_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification OTP")

        receiver.verification_status = "VERIFIED"
        receiver.verified_at = now_utc()
        receiver.verification_code_hash = None
        receiver.verification_expires_at = None
        receiver.last_verification_error = None
        AuditService.add_log(
            db,
            action="VERIFY_ALERT_RECEIVER",
            user_id=user.id,
            target_type="notification_channels",
            target_id=receiver.id,
            request_ip=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
        await db.refresh(receiver)
        return _receiver_response(receiver)

    @staticmethod
    async def delete_receiver(db: AsyncSession, user: User, receiver_id: UUID, request: Request) -> None:
        """Soft delete a webhook receiver owned by the current user."""
        receiver = await ReceiverService.get_owned_receiver(db, user, receiver_id)
        receiver.deleted = True
        receiver.enabled = False
        AuditService.add_log(
            db,
            action="DELETE_ALERT_RECEIVER",
            user_id=user.id,
            target_type="notification_channels",
            target_id=receiver.id,
            request_ip=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()

    @staticmethod
    async def _send_verification_otp(db: AsyncSession, receiver: NotificationChannel) -> None:
        """Generate and deliver a new receiver verification OTP to the webhook URL."""
        settings = get_settings()
        otp = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = now_utc() + timedelta(minutes=settings.receiver_otp_expire_minutes)
        receiver.verification_status = "PENDING"
        receiver.verification_code_hash = hash_receiver_otp(str(receiver.id), otp)
        receiver.verification_expires_at = expires_at
        receiver.last_verification_sent_at = now_utc()
        receiver.last_verification_error = None

        webhook_payload = ReceiverService._build_verification_payload(receiver, otp, expires_at)
        try:
            async with httpx.AsyncClient(timeout=settings.receiver_webhook_timeout_seconds, follow_redirects=False) as client:
                response = await client.post(receiver.receiver, json=webhook_payload)
            if response.status_code < 200 or response.status_code >= 300:
                receiver.verification_status = "FAILED"
                receiver.last_verification_error = f"Webhook returned HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            receiver.verification_status = "FAILED"
            receiver.last_verification_error = str(exc)
        db.add(receiver)

    @staticmethod
    def _build_verification_payload(receiver: NotificationChannel, otp: str, expires_at) -> dict[str, Any]:
        """Build a verification payload, using Discord embeds for Discord webhooks."""
        if not _is_discord_webhook(receiver.receiver):
            return {
                "type": "OBSERVABILITY_RECEIVER_VERIFICATION",
                "receiver_id": str(receiver.id),
                "otp": otp,
                "expires_at": expires_at.isoformat(),
            }

        return _discord_payload(
            {
                "title": "Webhook Receiver Verification",
                "description": "Use this one-time code in the Observability Portal to verify ownership of this Discord webhook receiver.",
                "color": DISCORD_COLOR_BRAND,
                "timestamp": now_utc().isoformat(),
                "fields": [
                    _discord_field("Verification code", f"`{otp}`", False),
                    _discord_field("Receiver", receiver.channel_name),
                    _discord_field("Receiver ID", str(receiver.id)),
                    _discord_field("Expires at", expires_at.isoformat(), False),
                ],
                "footer": {"text": "MasterPTIT Observability Portal"},
            }
        )


class AlertRuleService:
    @staticmethod
    def _generate_rule_code() -> str:
        """Generate an opaque vmalert alert identifier that users do not control."""
        return f"PortalAlert_{secrets.token_hex(8)}"

    @staticmethod
    def _metric_selector(metric_name: str, labels: dict[str, str | None]) -> str:
        """Render a PromQL metric selector from a metric name and optional labels."""
        active_labels = [(key, value) for key, value in labels.items() if value]
        if not active_labels:
            return metric_name
        label_text = ",".join(f'{key}="{value}"' for key, value in active_labels)
        return f"{metric_name}{{{label_text}}}"

    @staticmethod
    def _build_promql(metric_name: str, operator: str, threshold: float, duration_minutes: int, vm_id: UUID | None) -> str:
        """Build the PromQL expression stored for an alert rule from structured inputs."""
        vm_label = str(vm_id) if vm_id else None
        window = f"{duration_minutes}m"
        threshold_text = f"{threshold:g}"
        if metric_name == "cpu_usage_percent":
            idle_selector = AlertRuleService._metric_selector("system_cpu_time_seconds_total", {"state": "idle", "vm_id": vm_label})
            metric_expr = f"100 * (1 - avg by (vm_id) (rate({idle_selector}[{window}])))"
        elif metric_name == "memory_usage_percent":
            used_selector = AlertRuleService._metric_selector("system_memory_usage_bytes", {"state": "used", "vm_id": vm_label})
            total_selector = AlertRuleService._metric_selector("system_memory_usage_bytes", {"vm_id": vm_label})
            metric_expr = f"100 * sum by (vm_id) ({used_selector}) / sum by (vm_id) ({total_selector})"
        elif metric_name == "disk_usage_percent":
            used_selector = AlertRuleService._metric_selector("system_filesystem_usage_bytes", {"state": "used", "vm_id": vm_label})
            total_selector = AlertRuleService._metric_selector("system_filesystem_usage_bytes", {"vm_id": vm_label})
            metric_expr = f"100 * sum by (vm_id) ({used_selector}) / sum by (vm_id) ({total_selector})"
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported alert metric")
        return f"({metric_expr}) {operator} {threshold_text}"

    @staticmethod
    def _build_condition_text(metric_name: str, operator: str, threshold: float, duration_minutes: int) -> str:
        """Build a readable condition summary from structured alert inputs."""
        metric_label = ALERT_METRIC_LABELS.get(metric_name, metric_name)
        return f"{metric_label} {operator} {threshold:g}% for {duration_minutes}m"

    @staticmethod
    async def list_rules(db: AsyncSession, user: User) -> list[dict[str, Any]]:
        """List alert rules owned by the current user with their receiver bindings."""
        result = await db.execute(
            select(AlertRule)
            .where(AlertRule.user_id == user.id, AlertRule.deleted.is_(False))
            .order_by(AlertRule.created_at.desc())
        )
        rules = list(result.scalars().all())
        receiver_map = await AlertRuleService._receiver_ids_by_rule(db, [rule.id for rule in rules])
        return [_rule_response(rule, receiver_map.get(rule.id, [])) for rule in rules]

    @staticmethod
    async def get_owned_rule(db: AsyncSession, user: User, rule_id: UUID) -> AlertRule:
        """Load an alert rule by id and ensure it belongs to the current user."""
        result = await db.execute(
            select(AlertRule).where(AlertRule.id == rule_id, AlertRule.user_id == user.id, AlertRule.deleted.is_(False))
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
        return rule

    @staticmethod
    async def create_rule(db: AsyncSession, user: User, payload: AlertRuleCreateRequest, request: Request) -> dict[str, Any]:
        """Create an alert rule and bind it to verified webhook receivers."""
        await AlertRuleService._ensure_owned_vm(db, user, payload.vm_id)
        await AlertRuleService._ensure_verified_receivers(db, user, payload.receiver_ids)
        promql_expr = AlertRuleService._build_promql(
            payload.metric_name,
            payload.comparison_operator,
            payload.threshold,
            payload.duration_minutes,
            payload.vm_id,
        )
        condition_text = AlertRuleService._build_condition_text(
            payload.metric_name,
            payload.comparison_operator,
            payload.threshold,
            payload.duration_minutes,
        )
        rule = AlertRule(
            user_id=user.id,
            vm_id=payload.vm_id,
            rule_name=payload.rule_name.strip(),
            rule_code=AlertRuleService._generate_rule_code(),
            metric_name=payload.metric_name,
            promql_expr=promql_expr,
            condition_text=condition_text,
            duration=f"{payload.duration_minutes}m",
            severity=payload.severity,
            enabled=payload.enabled,
        )
        db.add(rule)
        await db.flush()
        for receiver_id in payload.receiver_ids:
            db.add(AlertRuleChannel(alert_rule_id=rule.id, channel_id=receiver_id))
        AuditService.add_log(
            db,
            action="CREATE_ALERT_RULE",
            user_id=user.id,
            target_type="alert_rules",
            target_id=rule.id,
            request_ip=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail_json={"receiver_ids": [str(receiver_id) for receiver_id in payload.receiver_ids]},
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alert rule code already exists") from exc
        await db.refresh(rule)
        await AlertRuleService.sync_vmalert_rules(db)
        return _rule_response(rule, payload.receiver_ids)

    @staticmethod
    async def update_rule(
        db: AsyncSession,
        user: User,
        rule_id: UUID,
        payload: AlertRuleUpdateRequest,
        request: Request,
    ) -> dict[str, Any]:
        """Update an alert rule and optionally replace its verified receiver bindings."""
        rule = await AlertRuleService.get_owned_rule(db, user, rule_id)
        update_data = payload.model_dump(exclude_unset=True)
        receiver_ids = update_data.pop("receiver_ids", None)
        comparison_operator = update_data.pop("comparison_operator", None)
        threshold = update_data.pop("threshold", None)
        duration_minutes = update_data.pop("duration_minutes", None)

        if "vm_id" in update_data:
            await AlertRuleService._ensure_owned_vm(db, user, update_data["vm_id"])
        if receiver_ids is not None:
            await AlertRuleService._ensure_verified_receivers(db, user, receiver_ids)

        next_vm_id = update_data.get("vm_id", rule.vm_id)
        next_metric_name = update_data.get("metric_name", rule.metric_name)
        next_duration_minutes = duration_minutes if duration_minutes is not None else AlertRuleService._parse_duration_minutes(rule.duration)
        next_operator = comparison_operator
        next_threshold = threshold
        if next_operator is None or next_threshold is None:
            parsed_operator, parsed_threshold = AlertRuleService._parse_condition(rule.condition_text)
            next_operator = next_operator or parsed_operator
            next_threshold = next_threshold if next_threshold is not None else parsed_threshold
        should_rebuild_promql = any(
            value is not None for value in [comparison_operator, threshold, duration_minutes]
        ) or "metric_name" in update_data or "vm_id" in update_data

        for field, value in update_data.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(rule, field, value)
        if should_rebuild_promql:
            rule.metric_name = next_metric_name
            rule.promql_expr = AlertRuleService._build_promql(
                str(next_metric_name),
                str(next_operator),
                float(next_threshold),
                int(next_duration_minutes),
                next_vm_id,
            )
            rule.condition_text = AlertRuleService._build_condition_text(
                str(next_metric_name),
                str(next_operator),
                float(next_threshold),
                int(next_duration_minutes),
            )
            rule.duration = f"{int(next_duration_minutes)}m"

        if receiver_ids is not None:
            await db.execute(delete(AlertRuleChannel).where(AlertRuleChannel.alert_rule_id == rule.id))
            for receiver_id in receiver_ids:
                db.add(AlertRuleChannel(alert_rule_id=rule.id, channel_id=receiver_id))

        AuditService.add_log(
            db,
            action="UPDATE_ALERT_RULE",
            user_id=user.id,
            target_type="alert_rules",
            target_id=rule.id,
            request_ip=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail_json={"updated_fields": sorted(update_data.keys()) + (["receiver_ids"] if receiver_ids is not None else [])},
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alert rule code already exists") from exc
        await db.refresh(rule)
        await AlertRuleService.sync_vmalert_rules(db)
        active_receiver_ids = receiver_ids if receiver_ids is not None else (await AlertRuleService._receiver_ids_by_rule(db, [rule.id])).get(rule.id, [])
        return _rule_response(rule, active_receiver_ids)

    @staticmethod
    def _parse_condition(condition_text: str | None) -> tuple[str, float]:
        """Read operator and threshold from a generated condition string for partial updates."""
        if not condition_text:
            return ">=", 80
        parts = condition_text.split()
        for index, part in enumerate(parts):
            if part in {">", ">=", "<=", "<"} and index + 1 < len(parts):
                try:
                    return part, float(parts[index + 1].rstrip("%"))
                except ValueError:
                    return ">=", 80
        return ">=", 80

    @staticmethod
    def _parse_duration_minutes(duration: str | None) -> int:
        """Read minute duration from stored alert rule duration text."""
        if not duration or not duration.endswith("m"):
            return 5
        try:
            return int(duration.rstrip("m"))
        except ValueError:
            return 5

    @staticmethod
    async def delete_rule(db: AsyncSession, user: User, rule_id: UUID, request: Request) -> None:
        """Soft delete an alert rule and remove it from generated vmalert rules."""
        rule = await AlertRuleService.get_owned_rule(db, user, rule_id)
        rule.deleted = True
        rule.enabled = False
        await db.execute(delete(AlertRuleChannel).where(AlertRuleChannel.alert_rule_id == rule.id))
        AuditService.add_log(
            db,
            action="DELETE_ALERT_RULE",
            user_id=user.id,
            target_type="alert_rules",
            target_id=rule.id,
            request_ip=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
        await AlertRuleService.sync_vmalert_rules(db)

    @staticmethod
    async def _receiver_ids_by_rule(db: AsyncSession, rule_ids: list[UUID]) -> dict[UUID, list[UUID]]:
        """Return receiver id bindings grouped by alert rule id."""
        if not rule_ids:
            return {}
        result = await db.execute(
            select(AlertRuleChannel.alert_rule_id, AlertRuleChannel.channel_id).where(AlertRuleChannel.alert_rule_id.in_(rule_ids))
        )
        grouped: dict[UUID, list[UUID]] = defaultdict(list)
        for rule_id, receiver_id in result.all():
            grouped[rule_id].append(receiver_id)
        return grouped

    @staticmethod
    async def _ensure_owned_vm(db: AsyncSession, user: User, vm_id: UUID | None) -> None:
        """Validate that an optional VM id belongs to the current user."""
        if vm_id is None:
            return
        result = await db.execute(
            select(VmInstance.id).where(VmInstance.id == vm_id, VmInstance.user_id == user.id, VmInstance.deleted.is_(False))
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VM not found")

    @staticmethod
    async def _ensure_verified_receivers(db: AsyncSession, user: User, receiver_ids: list[UUID]) -> None:
        """Validate that requested receivers exist, are enabled, and are verified."""
        result = await db.execute(
            select(NotificationChannel).where(
                NotificationChannel.id.in_(receiver_ids),
                NotificationChannel.user_id == user.id,
                NotificationChannel.channel_type == "WEBHOOK",
                NotificationChannel.deleted.is_(False),
            )
        )
        receivers = list(result.scalars().all())
        receiver_by_id = {receiver.id: receiver for receiver in receivers}
        missing = [receiver_id for receiver_id in receiver_ids if receiver_id not in receiver_by_id]
        if missing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more receivers were not found")
        invalid = [
            receiver.channel_name
            for receiver in receivers
            if not receiver.enabled or receiver.verification_status != "VERIFIED"
        ]
        if invalid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All receivers must be enabled and verified")

    @staticmethod
    async def sync_vmalert_rules(db: AsyncSession) -> None:
        """Write enabled DB alert rules to a vmalert-compatible rule file."""
        result = await db.execute(
            select(AlertRule)
            .where(AlertRule.deleted.is_(False), AlertRule.enabled.is_(True))
            .order_by(AlertRule.created_at.asc())
        )
        rules = list(result.scalars().all())
        content = AlertRuleService._render_vmalert_rules(rules)
        try:
            path = AlertRuleService._resolve_vmalert_rules_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_name = ""
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
                    tmp_name = handle.name
                    handle.write(content)
                os.replace(tmp_name, path)
            finally:
                if tmp_name and os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            await AlertRuleService._reload_vmalert()
        except OSError as exc:
            logger.warning("Could not write vmalert rule file: %s", exc)

    @staticmethod
    def _render_vmalert_rules(rules: list[AlertRule]) -> str:
        """Render alert rules as a small YAML document accepted by vmalert."""
        if not rules:
            return "groups: []\n"

        lines = ["groups:", "  - name: portal-alert-rules", "    interval: 30s", "    rules:"]
        for rule in rules:
            lines.extend(
                [
                    f"      - alert: {_yaml_quote(rule.rule_code)}",
                    f"        expr: {_yaml_quote(rule.promql_expr)}",
                    f"        for: {_yaml_quote(rule.duration)}",
                    "        labels:",
                    f"          severity: {_yaml_quote(rule.severity)}",
                    f"          user_id: {_yaml_quote(rule.user_id)}",
                    f"          rule_id: {_yaml_quote(rule.id)}",
                    f"          rule_code: {_yaml_quote(rule.rule_code)}",
                    "        annotations:",
                    f"          summary: {_yaml_quote(rule.rule_name)}",
                    f"          description: {_yaml_quote(rule.condition_text or rule.rule_name)}",
                ]
            )
            if rule.vm_id:
                insert_at = len(lines) - 3
                lines.insert(insert_at, f"          vm_id: {_yaml_quote(rule.vm_id)}")
            if rule.metric_name:
                lines.append(f"          metric_name: {_yaml_quote(rule.metric_name)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _resolve_vmalert_rules_file() -> Path:
        """Resolve the configured vmalert rule file path for local and container runs."""
        configured = get_settings().vmalert_rules_file
        if configured.is_absolute():
            return configured
        repo_root = Path(__file__).resolve().parents[3]
        candidates = [Path.cwd() / configured, Path.cwd().parent / configured, repo_root / configured]
        for candidate in candidates:
            if candidate.parent.exists():
                return candidate
        return candidates[0]

    @staticmethod
    async def _reload_vmalert() -> None:
        """Best-effort reload hook after updating the generated vmalert rule file."""
        reload_url = get_settings().vmalert_reload_url
        if not reload_url:
            return
        try:
            async with httpx.AsyncClient(timeout=2.0, follow_redirects=False) as client:
                response = await client.post(reload_url)
            if response.status_code < 200 or response.status_code >= 300:
                logger.warning("vmalert reload returned HTTP %s", response.status_code)
        except httpx.HTTPError as exc:
            logger.warning("Could not reload vmalert: %s", exc)


class AlertDispatchService:
    @staticmethod
    async def handle_alertmanager_webhook(db: AsyncSession, payload: AlertmanagerWebhookPayload) -> AlertmanagerWebhookResponse:
        """Dispatch Alertmanager alerts to verified receivers bound to the alert rule."""
        rule_cache: dict[UUID, tuple[AlertRule, list[NotificationChannel], VmInstance | None] | None] = {}
        dispatch_tasks = []
        skipped = 0

        for alert in payload.alerts:
            labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
            raw_rule_id = labels.get("rule_id")
            if not raw_rule_id:
                skipped += 1
                continue
            try:
                rule_id = UUID(str(raw_rule_id))
            except ValueError:
                skipped += 1
                continue

            if rule_id not in rule_cache:
                rule_cache[rule_id] = await AlertDispatchService._load_rule_with_receivers(db, rule_id)
            rule_bundle = rule_cache[rule_id]
            if not rule_bundle:
                skipped += 1
                continue

            rule, receivers, vm = rule_bundle
            if not receivers:
                skipped += 1
                continue
            for receiver in receivers:
                if not AlertDispatchService._mark_receiver_alert_due(receiver, rule, alert):
                    skipped += 1
                    continue
                dispatch_tasks.append(AlertDispatchService._dispatch_to_receiver(payload, alert, rule, receiver, vm))

        results = await asyncio.gather(*dispatch_tasks, return_exceptions=True) if dispatch_tasks else []
        failed = sum(1 for result in results if result is not True)
        dispatched = len(results) - failed
        AuditService.add_log(
            db,
            action="RECEIVE_ALERTMANAGER_WEBHOOK",
            detail_json={
                "received": len(payload.alerts),
                "dispatched": dispatched,
                "failed": failed,
                "skipped": skipped,
            },
        )
        await db.commit()
        return AlertmanagerWebhookResponse(received=len(payload.alerts), dispatched=dispatched, failed=failed, skipped=skipped)

    @staticmethod
    async def _load_rule_with_receivers(db: AsyncSession, rule_id: UUID) -> tuple[AlertRule, list[NotificationChannel], VmInstance | None] | None:
        """Load one enabled alert rule, its VM, and its verified webhook receivers."""
        rule_result = await db.execute(
            select(AlertRule).where(AlertRule.id == rule_id, AlertRule.deleted.is_(False), AlertRule.enabled.is_(True))
        )
        rule = rule_result.scalar_one_or_none()
        if not rule:
            return None
        receiver_result = await db.execute(
            select(NotificationChannel)
            .join(AlertRuleChannel, AlertRuleChannel.channel_id == NotificationChannel.id)
            .where(
                AlertRuleChannel.alert_rule_id == rule.id,
                NotificationChannel.deleted.is_(False),
                NotificationChannel.enabled.is_(True),
                NotificationChannel.channel_type == "WEBHOOK",
                NotificationChannel.verification_status == "VERIFIED",
            )
        )
        vm = None
        if rule.vm_id:
            vm_result = await db.execute(select(VmInstance).where(VmInstance.id == rule.vm_id, VmInstance.deleted.is_(False)))
            vm = vm_result.scalar_one_or_none()
        return rule, list(receiver_result.scalars().all()), vm

    @staticmethod
    def _mark_receiver_alert_due(receiver: NotificationChannel, rule: AlertRule, alert: dict[str, Any]) -> bool:
        """Return whether an alert should be sent and record the send time for firing repeats."""
        alert_status = str(alert.get("status") or "firing").lower()
        if alert_status == "resolved":
            return True

        now = now_utc()
        interval = timedelta(minutes=_receiver_resend_interval_minutes(receiver))
        config = _receiver_config(receiver)
        last_sent_map = dict(config.get("last_alert_sent_at") or {})
        last_sent_key = f"{rule.id}:{alert_status}"
        raw_last_sent_at = last_sent_map.get(last_sent_key)
        if raw_last_sent_at:
            try:
                last_sent_at = datetime.fromisoformat(str(raw_last_sent_at))
            except ValueError:
                last_sent_at = None
            if last_sent_at and now - last_sent_at < interval:
                return False

        last_sent_map[last_sent_key] = now.isoformat()
        config["last_alert_sent_at"] = last_sent_map
        receiver.config_json = config
        return True

    @staticmethod
    async def _dispatch_to_receiver(
        source_payload: AlertmanagerWebhookPayload,
        alert: dict[str, Any],
        rule: AlertRule,
        receiver: NotificationChannel,
        vm: VmInstance | None,
    ) -> bool:
        """Forward one alert to one verified webhook receiver."""
        settings = get_settings()
        outgoing_payload = AlertDispatchService._build_receiver_payload(source_payload, alert, rule, receiver, vm)
        headers = {
            "User-Agent": "MasterPTIT-Observability-Portal/alert-dispatch",
            "X-Observability-Event": "alert",
            "X-Observability-Rule-ID": str(rule.id),
        }
        try:
            async with httpx.AsyncClient(timeout=settings.alert_dispatch_timeout_seconds, follow_redirects=False) as client:
                response = await client.post(receiver.receiver, json=outgoing_payload, headers=headers)
            if response.status_code < 200 or response.status_code >= 300:
                logger.warning("Alert receiver %s returned HTTP %s", receiver.id, response.status_code)
                return False
            return True
        except httpx.HTTPError as exc:
            logger.warning("Could not dispatch alert to receiver %s: %s", receiver.id, exc)
            return False

    @staticmethod
    def _build_receiver_payload(
        source_payload: AlertmanagerWebhookPayload,
        alert: dict[str, Any],
        rule: AlertRule,
        receiver: NotificationChannel,
        vm: VmInstance | None = None,
    ) -> dict[str, Any]:
        """Build the outbound alert payload for a receiver."""
        generic_payload = {
            "type": "OBSERVABILITY_ALERT",
            "status": alert.get("status") or source_payload.status,
            "received_at": now_utc().isoformat(),
            "rule": {
                "id": str(rule.id),
                "name": rule.rule_name,
                "code": rule.rule_code,
                "severity": rule.severity,
                "vm_id": str(rule.vm_id) if rule.vm_id else None,
                "vm_name": vm.vm_name if vm else None,
                "public_ip": vm.public_ip if vm else None,
            },
            "alert": alert,
            "group_labels": source_payload.groupLabels,
            "common_labels": source_payload.commonLabels,
            "common_annotations": source_payload.commonAnnotations,
            "external_url": source_payload.externalURL,
        }
        if not _is_discord_webhook(receiver.receiver):
            return generic_payload
        return AlertDispatchService._build_discord_alert_payload(source_payload, alert, rule, vm)

    @staticmethod
    def _build_discord_alert_payload(
        source_payload: AlertmanagerWebhookPayload,
        alert: dict[str, Any],
        rule: AlertRule,
        vm: VmInstance | None = None,
    ) -> dict[str, Any]:
        """Build a polished Discord embed for an Alertmanager alert."""
        labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
        annotations = alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
        alert_status = str(alert.get("status") or source_payload.status or "unknown").lower()
        is_resolved = alert_status == "resolved"
        severity = _title_case_status(labels.get("severity") or rule.severity or "unknown")
        vm_name = vm.vm_name if vm else "All VMs"
        public_ip = vm.public_ip if vm and vm.public_ip else "N/A"
        summary = annotations.get("summary") or rule.rule_name
        description = annotations.get("description") or rule.condition_text or "No description"

        fields = [
            _discord_field("Status", "Resolved" if is_resolved else "Firing"),
            _discord_field("Severity", severity),
            _discord_field("VM", vm_name),
            _discord_field("Public IP", public_ip),
            _discord_field("Rule", rule.rule_name),
            _discord_field("Condition", rule.condition_text or "N/A", False),
        ]
        if alert.get("startsAt"):
            fields.append(_discord_field("Started at", _format_discord_datetime(alert["startsAt"])))
        if alert.get("endsAt") and is_resolved:
            fields.append(_discord_field("Resolved at", _format_discord_datetime(alert["endsAt"])))

        title_prefix = "Resolved" if is_resolved else "Firing"
        return _discord_payload(
            {
                "title": f"{title_prefix}: {rule.rule_name}",
                "description": _discord_text(f"**{summary}**\n{description}", 4096),
                "color": DISCORD_COLOR_RESOLVED if is_resolved else DISCORD_COLOR_FIRING,
                "timestamp": now_utc().isoformat(),
                "fields": fields,
                "footer": {"text": "MasterPTIT Observability Portal"},
            }
        )
