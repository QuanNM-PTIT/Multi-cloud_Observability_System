from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.schemas.base import TimezoneAwareResponse

AlertSeverity = Literal["info", "warning", "critical"]
ReceiverVerificationStatus = Literal["PENDING", "VERIFIED", "FAILED"]
AlertMetricName = Literal["cpu_usage_percent", "memory_usage_percent", "disk_usage_percent"]
AlertComparisonOperator = Literal[">", ">=", "<=", "<"]


class ReceiverCreateRequest(BaseModel):
    receiver_name: str = Field(min_length=1, max_length=255)
    webhook_url: HttpUrl
    enabled: bool = True
    alert_resend_interval_minutes: int = Field(default=15, ge=10, le=60)


class ReceiverUpdateRequest(BaseModel):
    receiver_name: str | None = Field(default=None, min_length=1, max_length=255)
    webhook_url: HttpUrl | None = None
    enabled: bool | None = None
    alert_resend_interval_minutes: int | None = Field(default=None, ge=10, le=60)


class ReceiverVerifyRequest(BaseModel):
    otp: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class ReceiverResponse(TimezoneAwareResponse):
    id: UUID
    receiver_name: str
    receiver_type: str
    webhook_url: str
    enabled: bool
    alert_resend_interval_minutes: int
    verification_status: ReceiverVerificationStatus
    verification_expires_at: datetime | None
    verified_at: datetime | None
    last_verification_sent_at: datetime | None
    last_verification_error: str | None
    created_at: datetime
    updated_at: datetime | None


class ReceiverListResponse(TimezoneAwareResponse):
    items: list[ReceiverResponse]


class AlertRuleCreateRequest(BaseModel):
    rule_name: str = Field(min_length=1, max_length=255)
    vm_id: UUID | None = None
    metric_name: AlertMetricName
    comparison_operator: AlertComparisonOperator = ">="
    threshold: float = Field(ge=0, le=100)
    duration_minutes: int = Field(default=5, ge=2, le=60)
    severity: AlertSeverity
    enabled: bool = True
    receiver_ids: list[UUID] = Field(min_length=1)

    @field_validator("receiver_ids")
    @classmethod
    def validate_unique_receivers(cls, value: list[UUID]) -> list[UUID]:
        """Reject duplicate receiver bindings in a single rule request."""
        if len(set(value)) != len(value):
            raise ValueError("Receiver ids must be unique")
        return value


class AlertRuleUpdateRequest(BaseModel):
    rule_name: str | None = Field(default=None, min_length=1, max_length=255)
    vm_id: UUID | None = None
    metric_name: AlertMetricName | None = None
    comparison_operator: AlertComparisonOperator | None = None
    threshold: float | None = Field(default=None, ge=0, le=100)
    duration_minutes: int | None = Field(default=None, ge=2, le=60)
    severity: AlertSeverity | None = None
    enabled: bool | None = None
    receiver_ids: list[UUID] | None = Field(default=None, min_length=1)

    @field_validator("receiver_ids")
    @classmethod
    def validate_unique_receivers(cls, value: list[UUID] | None) -> list[UUID] | None:
        """Reject duplicate receiver bindings in a single rule request."""
        if value is not None and len(set(value)) != len(value):
            raise ValueError("Receiver ids must be unique")
        return value


class AlertRuleResponse(TimezoneAwareResponse):
    id: UUID
    vm_id: UUID | None
    rule_name: str
    rule_code: str
    metric_name: str | None
    promql_expr: str
    condition_text: str | None
    duration: str
    severity: AlertSeverity
    enabled: bool
    receiver_ids: list[UUID]
    created_at: datetime
    updated_at: datetime | None


class AlertRuleListResponse(TimezoneAwareResponse):
    items: list[AlertRuleResponse]


class AlertmanagerWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    receiver: str | None = None
    status: str | None = None
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    groupLabels: dict[str, Any] = Field(default_factory=dict)
    commonLabels: dict[str, Any] = Field(default_factory=dict)
    commonAnnotations: dict[str, Any] = Field(default_factory=dict)
    externalURL: str | None = None
    version: str | None = None
    groupKey: str | None = None
    truncatedAlerts: int | None = None


class AlertmanagerWebhookResponse(BaseModel):
    received: int
    dispatched: int
    failed: int
    skipped: int
