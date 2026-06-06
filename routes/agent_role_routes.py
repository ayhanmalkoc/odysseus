"""Agent role catalog routes."""

import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.database import AgentRole, SessionLocal
from src.auth_helpers import require_user


class RolePayload(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=1000)
    is_active: Optional[bool] = None


class RoleCreate(RolePayload):
    name: str = Field(..., min_length=1, max_length=80)


def _to_dict(row: AgentRole) -> dict:
    return {"id": row.id, "owner": row.owner, "name": row.name, "description": row.description, "is_builtin": bool(row.is_builtin), "is_active": bool(row.is_active)}


def _get(db, owner: str, role_id: str) -> AgentRole:
    row = db.query(AgentRole).filter(AgentRole.id == role_id).filter((AgentRole.owner == owner) | (AgentRole.is_builtin == True)).first()  # noqa: E712
    if not row:
        raise HTTPException(404, "Role not found")
    return row


def setup_agent_role_routes() -> APIRouter:
    router = APIRouter(prefix="/api/agent-roles", tags=["agent-roles"])

    @router.get("")
    async def list_roles(request: Request, include_inactive: bool = False):
        owner = require_user(request)
        db = SessionLocal()
        try:
            q = db.query(AgentRole).filter((AgentRole.owner == owner) | (AgentRole.is_builtin == True))  # noqa: E712
            if not include_inactive:
                q = q.filter(AgentRole.is_active == True)  # noqa: E712
            return {"roles": [_to_dict(r) for r in q.order_by(AgentRole.is_builtin.desc(), AgentRole.name.asc()).all()]}
        finally:
            db.close()

    @router.post("")
    async def create_role(payload: RoleCreate, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            row = AgentRole(id=f"role-{uuid.uuid4().hex[:12]}", owner=owner, name=payload.name.strip(), description=payload.description, is_builtin=False, is_active=True if payload.is_active is None else payload.is_active)
            db.add(row); db.commit(); db.refresh(row)
            return {"role": _to_dict(row)}
        finally:
            db.close()

    @router.patch("/{role_id}")
    async def update_role(role_id: str, payload: RolePayload, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            row = _get(db, owner, role_id)
            if row.is_builtin:
                raise HTTPException(400, "Built-in roles cannot be edited")
            data = payload.model_dump(exclude_unset=True)
            if "name" in data and data["name"] is not None:
                row.name = data["name"].strip()
            for field in ("description", "is_active"):
                if field in data:
                    setattr(row, field, data[field])
            db.commit(); db.refresh(row)
            return {"role": _to_dict(row)}
        finally:
            db.close()

    @router.delete("/{role_id}")
    async def archive_role(role_id: str, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            row = _get(db, owner, role_id)
            if row.is_builtin:
                raise HTTPException(400, "Built-in roles cannot be archived")
            row.is_active = False
            db.commit()
            return {"success": True, "archived": True}
        finally:
            db.close()

    return router
