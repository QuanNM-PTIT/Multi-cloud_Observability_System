import uuid

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import VmAgentStatus
from app.models.user import User
from app.models.vm import VmInstance
from app.schemas.vm import VmCreateRequest, VmUpdateRequest
from app.services.audit_service import AuditService


class VmService:
    @staticmethod
    async def create_vm(db: AsyncSession, user: User, payload: VmCreateRequest, request: Request) -> VmInstance:
        """Create a VM metadata record owned by the current portal user."""
        vm = VmInstance(user_id=user.id, **payload.model_dump())
        db.add(vm)
        await db.flush()
        db.add(VmAgentStatus(vm_id=vm.id))
        AuditService.add_log(
            db,
            action="CREATE_VM",
            user_id=user.id,
            target_type="vm_instances",
            target_id=vm.id,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="VM name already exists for this provider") from exc
        await db.refresh(vm)
        return vm

    @staticmethod
    async def list_vms(db: AsyncSession, user: User) -> list[VmInstance]:
        """List all non-deleted VM records owned by the current user."""
        result = await db.execute(
            select(VmInstance)
            .where(VmInstance.user_id == user.id, VmInstance.deleted.is_(False))
            .order_by(VmInstance.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_owned_vm(db: AsyncSession, user: User, vm_id: uuid.UUID) -> VmInstance:
        """Load a VM by id and ensure it belongs to the current user."""
        result = await db.execute(
            select(VmInstance).where(VmInstance.id == vm_id, VmInstance.user_id == user.id, VmInstance.deleted.is_(False))
        )
        vm = result.scalar_one_or_none()
        if not vm:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VM not found")
        return vm

    @staticmethod
    async def update_vm(db: AsyncSession, user: User, vm_id: uuid.UUID, payload: VmUpdateRequest, request: Request) -> VmInstance:
        """Update mutable VM metadata fields for a VM owned by the current user."""
        vm = await VmService.get_owned_vm(db, user, vm_id)
        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(vm, field, value)
        AuditService.add_log(
            db,
            action="UPDATE_VM",
            user_id=user.id,
            target_type="vm_instances",
            target_id=vm.id,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            detail_json={"updated_fields": sorted(update_data.keys())},
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="VM name already exists for this provider") from exc
        await db.refresh(vm)
        return vm

    @staticmethod
    async def delete_vm(db: AsyncSession, user: User, vm_id: uuid.UUID, request: Request) -> None:
        """Soft delete a VM record while keeping audit and historical rows intact."""
        vm = await VmService.get_owned_vm(db, user, vm_id)
        vm.deleted = True
        vm.is_monitoring = False
        AuditService.add_log(
            db,
            action="DELETE_VM",
            user_id=user.id,
            target_type="vm_instances",
            target_id=vm.id,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
