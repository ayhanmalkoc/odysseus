"""Agent persona template routes."""

import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.database import AgentPersona, SessionLocal
from src.auth_helpers import require_user


class PersonaPayload(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    system_prompt: Optional[str] = Field(default=None, max_length=30000)
    prompt_prefix: Optional[str] = Field(default=None, max_length=10000)
    prompt_suffix: Optional[str] = Field(default=None, max_length=10000)
    is_active: Optional[bool] = None


class PersonaCreate(PersonaPayload):
    name: str = Field(..., min_length=1, max_length=160)


def _to_dict(row: AgentPersona) -> dict:
    return {
        "id": row.id,
        "owner": row.owner,
        "name": row.name,
        "description": row.description,
        "system_prompt": row.system_prompt,
        "prompt_prefix": row.prompt_prefix,
        "prompt_suffix": row.prompt_suffix,
        "is_active": bool(row.is_active),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _get(db, owner: str, persona_id: str) -> AgentPersona:
    row = db.query(AgentPersona).filter(AgentPersona.owner == owner, AgentPersona.id == persona_id).first()
    if not row:
        raise HTTPException(404, "Persona not found")
    return row


def setup_agent_persona_routes() -> APIRouter:
    router = APIRouter(prefix="/api/agent-personas", tags=["agent-personas"])

    @router.get("")
    async def list_personas(request: Request, include_inactive: bool = False):
        owner = require_user(request)
        db = SessionLocal()
        try:
            q = db.query(AgentPersona).filter(AgentPersona.owner == owner)
            if not include_inactive:
                q = q.filter(AgentPersona.is_active == True)  # noqa: E712
            return {"personas": [_to_dict(r) for r in q.order_by(AgentPersona.name.asc()).all()]}
        finally:
            db.close()

    @router.post("")
    async def create_persona(payload: PersonaCreate, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            row = AgentPersona(id=f"persona-{uuid.uuid4().hex[:12]}", owner=owner, name=payload.name.strip(), description=payload.description, system_prompt=payload.system_prompt, prompt_prefix=payload.prompt_prefix, prompt_suffix=payload.prompt_suffix, is_active=True if payload.is_active is None else payload.is_active)
            db.add(row); db.commit(); db.refresh(row)
            return {"persona": _to_dict(row)}
        finally:
            db.close()

    @router.patch("/{persona_id}")
    async def update_persona(persona_id: str, payload: PersonaPayload, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            row = _get(db, owner, persona_id)
            data = payload.model_dump(exclude_unset=True)
            if "name" in data and data["name"] is not None:
                row.name = data["name"].strip()
            for field in ("description", "system_prompt", "prompt_prefix", "prompt_suffix", "is_active"):
                if field in data:
                    setattr(row, field, data[field])
            db.commit(); db.refresh(row)
            return {"persona": _to_dict(row)}
        finally:
            db.close()

    @router.delete("/{persona_id}")
    async def archive_persona(persona_id: str, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            row = _get(db, owner, persona_id)
            row.is_active = False
            db.commit()
            return {"success": True, "archived": True}
        finally:
            db.close()

    return router
