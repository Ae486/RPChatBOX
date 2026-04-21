"""Custom role endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from models.custom_role import CustomRolePayload, CustomRoleSummary
from services.custom_role_store import CustomRoleStoreService
from services.database import get_session

router = APIRouter()


def _role_not_found(role_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"Custom role not found: {role_id}",
                "code": "custom_role_not_found",
            }
        },
    )


def _service(session: Session = Depends(get_session)) -> CustomRoleStoreService:
    return CustomRoleStoreService(session)


@router.get("/api/custom-roles")
async def list_custom_roles(service: CustomRoleStoreService = Depends(_service)):
    return {
        "object": "list",
        "data": [
            CustomRoleSummary.from_record(record).model_dump(mode="json")
            for record in service.list_roles()
        ],
    }


@router.post("/api/custom-roles", status_code=201)
async def create_custom_role(
    payload: CustomRolePayload,
    service: CustomRoleStoreService = Depends(_service),
):
    record = service.upsert_role(payload)
    return CustomRoleSummary.from_record(record).model_dump(mode="json")


@router.get("/api/custom-roles/{role_id}")
async def get_custom_role(
    role_id: str,
    service: CustomRoleStoreService = Depends(_service),
):
    record = service.get_role(role_id)
    if record is None:
        raise _role_not_found(role_id)
    return CustomRoleSummary.from_record(record).model_dump(mode="json")


@router.put("/api/custom-roles/{role_id}")
async def update_custom_role(
    role_id: str,
    payload: CustomRolePayload,
    service: CustomRoleStoreService = Depends(_service),
):
    record = service.get_role(role_id)
    if record is None:
        raise _role_not_found(role_id)
    updated = service.upsert_role(payload.model_copy(update={"id": role_id}))
    return CustomRoleSummary.from_record(updated).model_dump(mode="json")


@router.delete("/api/custom-roles/{role_id}")
async def delete_custom_role(
    role_id: str,
    service: CustomRoleStoreService = Depends(_service),
):
    deleted = service.delete_role(role_id)
    if not deleted:
        raise _role_not_found(role_id)
    return {"status": "ok", "deleted": role_id}
