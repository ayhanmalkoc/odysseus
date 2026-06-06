"""Agent team routes backed by first-class agent_teams tables."""

import json
import uuid
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from core.database import AgentTeam, AgentTeamMember, CrewMember, SessionLocal
from routes.agent_routes import _agent_to_dict
from src.auth_helpers import require_user


class TeamMemberPayload(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=160)
    role: str = Field(default="worker", max_length=80)
    sort_order: int = 0
    enabled: bool = True


class TeamPayload(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=4000)
    leader_agent_id: Optional[str] = Field(default=None, min_length=1, max_length=160)
    topology: Optional[str] = Field(default="lead_routed", max_length=80)
    shared_instructions: Optional[str] = Field(default=None, max_length=30000)
    run_policy: Optional[dict[str, Any]] = None
    members: Optional[list[TeamMemberPayload]] = None
    is_active: Optional[bool] = None
    status: Optional[str] = Field(default=None, max_length=40)

    @field_validator("topology")
    @classmethod
    def validate_topology(cls, value):
        allowed = {"lead_routed", "sequential", "parallel_review", "debate"}
        if value and value not in allowed:
            raise ValueError("Invalid team topology")
        return value


class TeamCreate(TeamPayload):
    name: str = Field(..., min_length=1, max_length=160)
    leader_agent_id: str = Field(..., min_length=1, max_length=160)


def _owned_agent(db, owner: str, agent_id: str) -> CrewMember:
    row = db.query(CrewMember).filter(CrewMember.owner == owner, CrewMember.id == agent_id, CrewMember.is_active == True).first()  # noqa: E712
    if not row:
        raise HTTPException(400, f"Agent not found: {agent_id}")
    return row


def _team_to_dict(team: AgentTeam) -> dict[str, Any]:
    return {
        "id": team.id,
        "owner": team.owner,
        "name": team.name,
        "description": team.description,
        "leader_agent_id": team.leader_agent_id,
        "leader": _agent_to_dict(team.leader) if team.leader else None,
        "topology": team.topology,
        "shared_instructions": team.shared_instructions,
        "run_policy": team.run_policy or {},
        "status": team.status,
        "is_active": bool(team.is_active),
        "members": [
            {
                "id": m.id,
                "agent_id": m.agent_id,
                "agent": _agent_to_dict(m.agent) if m.agent else None,
                "role": m.role,
                "sort_order": m.sort_order or 0,
                "enabled": bool(m.enabled),
            }
            for m in (team.members or [])
        ],
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "updated_at": team.updated_at.isoformat() if team.updated_at else None,
    }


def _get_team(db, owner: str, team_id: str) -> AgentTeam:
    row = db.query(AgentTeam).filter(AgentTeam.owner == owner, AgentTeam.id == team_id).first()
    if not row:
        raise HTTPException(404, "Team not found")
    return row


def _replace_members(db, owner: str, team: AgentTeam, members: list[TeamMemberPayload] | None):
    if members is None:
        return
    for item in list(team.members or []):
        db.delete(item)
    seen = {team.leader_agent_id}
    for idx, item in enumerate(members):
        if item.agent_id in seen:
            continue
        _owned_agent(db, owner, item.agent_id)
        seen.add(item.agent_id)
        db.add(AgentTeamMember(id=f"member-{uuid.uuid4().hex[:12]}", team_id=team.id, agent_id=item.agent_id, role=(item.role or "worker").strip() or "worker", sort_order=item.sort_order if item.sort_order is not None else idx, enabled=item.enabled))


def setup_agent_team_routes() -> APIRouter:
    router = APIRouter(prefix="/api/agent-teams", tags=["agent-teams"])

    @router.get("")
    async def list_teams(request: Request, include_inactive: bool = False):
        owner = require_user(request)
        db = SessionLocal()
        try:
            q = db.query(AgentTeam).filter(AgentTeam.owner == owner)
            if not include_inactive:
                q = q.filter(AgentTeam.is_active == True)  # noqa: E712
            return {"teams": [_team_to_dict(t) for t in q.order_by(AgentTeam.name.asc()).all()]}
        finally:
            db.close()

    @router.post("")
    async def create_team(payload: TeamCreate, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            _owned_agent(db, owner, payload.leader_agent_id)
            team = AgentTeam(id=f"team-{uuid.uuid4().hex[:12]}", owner=owner, name=payload.name.strip(), description=payload.description, leader_agent_id=payload.leader_agent_id, topology=payload.topology or "lead_routed", shared_instructions=payload.shared_instructions, run_policy=payload.run_policy or {}, status=payload.status or "active", is_active=True if payload.is_active is None else payload.is_active)
            db.add(team); db.flush()
            _replace_members(db, owner, team, payload.members or [])
            db.commit(); db.refresh(team)
            return {"team": _team_to_dict(team)}
        finally:
            db.close()

    @router.get("/{team_id}")
    async def get_team(team_id: str, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            return {"team": _team_to_dict(_get_team(db, owner, team_id))}
        finally:
            db.close()

    @router.patch("/{team_id}")
    async def update_team(team_id: str, payload: TeamPayload, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            team = _get_team(db, owner, team_id)
            data = payload.model_dump(exclude_unset=True)
            if "name" in data and data["name"] is not None:
                team.name = data["name"].strip()
            if "leader_agent_id" in data and data["leader_agent_id"]:
                _owned_agent(db, owner, data["leader_agent_id"])
                team.leader_agent_id = data["leader_agent_id"]
            for field in ("description", "topology", "shared_instructions", "run_policy", "status", "is_active"):
                if field in data:
                    setattr(team, field, data[field])
            _replace_members(db, owner, team, payload.members)
            db.commit(); db.refresh(team)
            return {"team": _team_to_dict(team)}
        finally:
            db.close()

    @router.delete("/{team_id}")
    async def archive_team(team_id: str, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            team = _get_team(db, owner, team_id)
            team.is_active = False
            team.status = "archived"
            db.commit()
            return {"success": True, "archived": True}
        finally:
            db.close()

    @router.post("/{team_id}/clone")
    async def clone_team(team_id: str, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            src = _get_team(db, owner, team_id)
            clone = AgentTeam(id=f"team-{uuid.uuid4().hex[:12]}", owner=owner, name=f"{src.name} Copy", description=src.description, leader_agent_id=src.leader_agent_id, topology=src.topology, shared_instructions=src.shared_instructions, run_policy=src.run_policy or {}, status="active", is_active=True)
            db.add(clone); db.flush()
            for m in src.members or []:
                db.add(AgentTeamMember(id=f"member-{uuid.uuid4().hex[:12]}", team_id=clone.id, agent_id=m.agent_id, role=m.role, sort_order=m.sort_order or 0, enabled=bool(m.enabled)))
            db.commit(); db.refresh(clone)
            return {"team": _team_to_dict(clone)}
        finally:
            db.close()

    @router.post("/{team_id}/dry-run")
    async def dry_run_team(team_id: str, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            team = _get_team(db, owner, team_id)
            return {"ok": True, "team": _team_to_dict(team), "message": "Team is configured."}
        finally:
            db.close()

    return router
