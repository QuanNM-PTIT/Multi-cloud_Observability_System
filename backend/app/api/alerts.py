from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.alert import (
    AlertRuleCreateRequest,
    AlertRuleListResponse,
    AlertRuleResponse,
    AlertRuleUpdateRequest,
    AlertmanagerWebhookPayload,
    AlertmanagerWebhookResponse,
    ReceiverCreateRequest,
    ReceiverListResponse,
    ReceiverResponse,
    ReceiverUpdateRequest,
    ReceiverVerifyRequest,
)
from app.services.alert_service import AlertDispatchService, AlertRuleService, ReceiverService

receivers_router = APIRouter(prefix="/alert-receivers", tags=["alert-receivers"])
rules_router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])
internal_router = APIRouter(prefix="/internal/alerts", tags=["internal-alerts"])


@receivers_router.get("", response_model=ReceiverListResponse)
async def list_receivers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReceiverListResponse:
    """List webhook alert receivers owned by the current user."""
    items = await ReceiverService.list_receivers(db, current_user)
    return ReceiverListResponse(items=items)


@receivers_router.post("", response_model=ReceiverResponse, status_code=201)
async def create_receiver(
    payload: ReceiverCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a webhook receiver and send an ownership verification OTP."""
    return await ReceiverService.create_receiver(db, current_user, payload, request)


@receivers_router.put("/{receiver_id}", response_model=ReceiverResponse)
async def update_receiver(
    receiver_id: UUID,
    payload: ReceiverUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a webhook receiver owned by the current user."""
    return await ReceiverService.update_receiver(db, current_user, receiver_id, payload, request)


@receivers_router.post("/{receiver_id}/resend-verification", response_model=ReceiverResponse)
async def resend_receiver_verification(
    receiver_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a fresh verification OTP to a webhook receiver."""
    return await ReceiverService.resend_verification(db, current_user, receiver_id, request)


@receivers_router.post("/{receiver_id}/verify", response_model=ReceiverResponse)
async def verify_receiver(
    receiver_id: UUID,
    payload: ReceiverVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify a webhook receiver using the OTP delivered to that webhook."""
    return await ReceiverService.verify_receiver(db, current_user, receiver_id, payload.otp, request)


@receivers_router.delete("/{receiver_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receiver(
    receiver_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Soft delete a webhook receiver owned by the current user."""
    await ReceiverService.delete_receiver(db, current_user, receiver_id, request)


@rules_router.get("", response_model=AlertRuleListResponse)
async def list_alert_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertRuleListResponse:
    """List alert rules owned by the current user."""
    items = await AlertRuleService.list_rules(db, current_user)
    return AlertRuleListResponse(items=items)


@rules_router.post("", response_model=AlertRuleResponse, status_code=201)
async def create_alert_rule(
    payload: AlertRuleCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an alert rule bound to one or more verified receivers."""
    return await AlertRuleService.create_rule(db, current_user, payload, request)


@rules_router.put("/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: UUID,
    payload: AlertRuleUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an alert rule owned by the current user."""
    return await AlertRuleService.update_rule(db, current_user, rule_id, payload, request)


@rules_router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Soft delete an alert rule owned by the current user."""
    await AlertRuleService.delete_rule(db, current_user, rule_id, request)


@internal_router.post("/alertmanager", response_model=AlertmanagerWebhookResponse)
async def receive_alertmanager_webhook(
    payload: AlertmanagerWebhookPayload,
    db: AsyncSession = Depends(get_db),
) -> AlertmanagerWebhookResponse:
    """Receive Alertmanager webhook payloads and dispatch alerts to verified receivers."""
    return await AlertDispatchService.handle_alertmanager_webhook(db, payload)
