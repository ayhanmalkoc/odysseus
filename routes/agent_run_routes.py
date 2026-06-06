"""Agent/team run timeline routes."""

import json
from fastapi import APIRouter, HTTPException, Request

from core.database import AgentRun, SessionLocal
from src.auth_helpers import require_user


def _step_to_dict(step):
    try:
        meta = json.loads(step.meta_data) if step.meta_data else {}
    except Exception:
        meta = {}
    return {"id": step.id, "run_id": step.run_id, "sort_order": step.sort_order or 0, "step_type": step.step_type, "agent_id": step.agent_id, "role": step.role, "title": step.title, "content": step.content, "status": step.status, "metadata": meta, "created_at": step.created_at.isoformat() if step.created_at else None}


def _run_to_dict(run, include_steps=False):
    try:
        meta = json.loads(run.meta_data) if run.meta_data else {}
    except Exception:
        meta = {}
    data = {"id": run.id, "owner": run.owner, "session_id": run.session_id, "target_type": run.target_type, "target_id": run.target_id, "status": run.status, "input": run.input, "output": run.output, "metadata": meta, "created_at": run.created_at.isoformat() if run.created_at else None, "updated_at": run.updated_at.isoformat() if run.updated_at else None}
    if include_steps:
        data["steps"] = [_step_to_dict(s) for s in run.steps]
    return data


def setup_agent_run_routes() -> APIRouter:
    router = APIRouter(prefix="/api/agent-runs", tags=["agent-runs"])

    @router.get("")
    async def list_runs(request: Request, session_id: str = "", target_type: str = "", target_id: str = ""):
        owner = require_user(request)
        db = SessionLocal()
        try:
            q = db.query(AgentRun).filter(AgentRun.owner == owner)
            if session_id:
                q = q.filter(AgentRun.session_id == session_id)
            if target_type:
                q = q.filter(AgentRun.target_type == target_type)
            if target_id:
                q = q.filter(AgentRun.target_id == target_id)
            return {"runs": [_run_to_dict(r) for r in q.order_by(AgentRun.created_at.desc()).limit(100).all()]}
        finally:
            db.close()

    @router.get("/{run_id}")
    async def get_run(run_id: str, request: Request):
        owner = require_user(request)
        db = SessionLocal()
        try:
            run = db.query(AgentRun).filter(AgentRun.owner == owner, AgentRun.id == run_id).first()
            if not run:
                raise HTTPException(404, "Run not found")
            return {"run": _run_to_dict(run, include_steps=True)}
        finally:
            db.close()

    return router
