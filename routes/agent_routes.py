"""Agent routes backed by existing CrewMember records."""

import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from core.database import CrewMember, SessionLocal
from src.auth_helpers import require_user


class AgentPayload(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    avatar: Optional[str] = Field(default=None, max_length=500)
    user_name: Optional[str] = Field(default=None, max_length=120)
    personality: Optional[str] = Field(default=None, max_length=20000)
    model: Optional[str] = Field(default=None, max_length=500)
    endpoint_url: Optional[str] = Field(default=None, max_length=1000)
    greeting: Optional[str] = Field(default=None, max_length=5000)
    enabled_tools: Optional[list[str]] = None
    timezone: Optional[str] = Field(default=None, max_length=120)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None

    @field_validator("enabled_tools")
    @classmethod
    def validate_tools(cls, value):
        if value is None:
            return value
        cleaned = []
        for item in value:
            tool = str(item).strip()
            if tool and tool not in cleaned:
                cleaned.append(tool)
        return cleaned


class AgentCreate(AgentPayload):
    name: str = Field(..., min_length=1, max_length=120)


def _owner_filter(query, owner: str):
    return query.filter(CrewMember.owner == owner)


def _tools_to_json(tools: Optional[list[str]]) -> Optional[str]:
    if tools is None:
        return None
    return json.dumps(tools)


def _agent_to_dict(agent: CrewMember) -> dict[str, Any]:
    try:
        tools = json.loads(agent.enabled_tools) if agent.enabled_tools else []
    except Exception:
        tools = []
    return {
        "id": agent.id,
        "owner": agent.owner,
        "name": agent.name,
        "avatar": agent.avatar,
        "user_name": agent.user_name,
        "personality": agent.personality,
        "model": agent.model,
        "endpoint_url": agent.endpoint_url,
        "greeting": agent.greeting,
        "enabled_tools": tools,
        "session_id": agent.session_id,
        "is_active": bool(agent.is_active),
        "sort_order": agent.sort_order or 0,
        "is_default_assistant": bool(agent.is_default_assistant),
        "timezone": agent.timezone,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


def _get_agent(db, owner: str, agent_id: str) -> CrewMember:
    agent = _owner_filter(db.query(CrewMember), owner).filter(CrewMember.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


def setup_agent_routes() -> APIRouter:
    router = APIRouter(prefix="/api/agents", tags=["agents"])

    @router.get("")
    async def list_agents(request: Request, include_inactive: bool = False):
        owner = require_user(request)
        db = SessionLocal()
        try:
            query = _owner_filter(db.query(CrewMember), owner)
            if not include_inactive:
                query = query.filter(CrewMember.is_active == True)  # noqa: E712
            rows = query.order_by(CrewMember.sort_order.asc(), CrewMember.created_at.asc()).all()
            return {"agents": [_agent_to_dict(row) for row in rows]}
        finally:
            db.close()

    @router.post("")
    async def create_agent(payload: AgentCreate, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            agent = CrewMember(
                id=f"crew-{uuid.uuid4().hex[:12]}",
                owner=owner,
                name=payload.name.strip(),
                avatar=payload.avatar,
                user_name=payload.user_name,
                personality=payload.personality,
                model=payload.model,
                endpoint_url=payload.endpoint_url,
                greeting=payload.greeting,
                enabled_tools=_tools_to_json(payload.enabled_tools),
                is_active=True if payload.is_active is None else payload.is_active,
                sort_order=payload.sort_order or 0,
                is_default_assistant=False,
                timezone=payload.timezone,
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            return {"agent": _agent_to_dict(agent)}
        finally:
            db.close()

    @router.get("/{agent_id}")
    async def get_agent(agent_id: str, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            return {"agent": _agent_to_dict(_get_agent(db, owner, agent_id))}
        finally:
            db.close()

    @router.patch("/{agent_id}")
    async def update_agent(agent_id: str, payload: AgentPayload, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            agent = _get_agent(db, owner, agent_id)
            data = payload.model_dump(exclude_unset=True)
            if "name" in data and data["name"] is not None:
                agent.name = data["name"].strip()
            for field in ("avatar", "user_name", "personality", "model", "endpoint_url", "greeting", "timezone"):
                if field in data:
                    setattr(agent, field, data[field])
            if "enabled_tools" in data:
                agent.enabled_tools = _tools_to_json(data["enabled_tools"])
            if "is_active" in data:
                agent.is_active = data["is_active"]
            if "sort_order" in data:
                agent.sort_order = data["sort_order"] or 0
            db.commit()
            db.refresh(agent)
            return {"agent": _agent_to_dict(agent)}
        finally:
            db.close()

    @router.delete("/{agent_id}")
    async def delete_agent(agent_id: str, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            agent = _get_agent(db, owner, agent_id)
            if agent.is_default_assistant:
                raise HTTPException(400, "Default assistant cannot be deleted")
            agent.is_active = False
            db.commit()
            return {"success": True, "archived": True}
        finally:
            db.close()

    @router.post("/{agent_id}/clone")
    async def clone_agent(agent_id: str, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            source = _get_agent(db, owner, agent_id)
            clone = CrewMember(
                id=f"crew-{uuid.uuid4().hex[:12]}",
                owner=owner,
                name=f"{source.name} Copy",
                avatar=source.avatar,
                user_name=source.user_name,
                personality=source.personality,
                model=source.model,
                endpoint_url=source.endpoint_url,
                greeting=source.greeting,
                enabled_tools=source.enabled_tools,
                is_active=True,
                sort_order=(source.sort_order or 0) + 1,
                is_default_assistant=False,
                timezone=source.timezone,
            )
            db.add(clone)
            db.commit()
            db.refresh(clone)
            return {"agent": _agent_to_dict(clone)}
        finally:
            db.close()

    return router
