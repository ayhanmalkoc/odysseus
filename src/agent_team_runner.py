"""First-class Agent/Team runner with persistent run timeline."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from core.database import (
    AgentRun,
    AgentRunStep,
    AgentTeam,
    CrewMember,
    Session as DbSession,
    SessionLocal,
)
from src.llm_core import llm_call_async
from src.prompt_security import untrusted_context_message


@dataclass
class TeamRunResult:
    response: str
    metadata: dict[str, Any]


def get_session_target(session_id: str) -> tuple[str, str | None]:
    db = SessionLocal()
    try:
        row = db.query(DbSession).filter(DbSession.id == session_id).first()
        if not row:
            return "chat", None
        target_type = (getattr(row, "target_type", None) or "chat").strip().lower()
        target_id = (getattr(row, "target_id", None) or "").strip() or None
        return target_type, target_id
    finally:
        db.close()


def _agent_to_dict(agent: CrewMember | None) -> dict[str, Any] | None:
    if not agent:
        return None
    try:
        tools = json.loads(agent.enabled_tools) if agent.enabled_tools else []
    except Exception:
        tools = []
    return {
        "id": agent.id,
        "name": agent.name,
        "personality": agent.personality or "",
        "model": agent.model or "",
        "endpoint_url": agent.endpoint_url or "",
        "enabled_tools": tools,
    }


def _agent_endpoint(agent: dict[str, Any], fallback_url: str, fallback_model: str) -> tuple[str, str]:
    return agent.get("endpoint_url") or fallback_url, agent.get("model") or fallback_model


def _create_run(db, owner: str | None, session_id: str, target_type: str, target_id: str | None, user_message: str) -> AgentRun:
    run = AgentRun(
        id=f"run-{uuid.uuid4().hex[:12]}",
        owner=owner,
        session_id=session_id,
        target_type=target_type,
        target_id=target_id,
        status="running",
        input=user_message,
        meta_data=json.dumps({}),
    )
    db.add(run)
    db.flush()
    return run


def _add_step(db, run: AgentRun, order: int, step_type: str, title: str, content: str, *, agent_id: str | None = None, role: str | None = None, status: str = "completed", metadata: dict | None = None):
    db.add(AgentRunStep(
        id=f"step-{uuid.uuid4().hex[:12]}",
        run_id=run.id,
        sort_order=order,
        step_type=step_type,
        agent_id=agent_id,
        role=role,
        title=title,
        content=content,
        status=status,
        meta_data=json.dumps(metadata or {}),
    ))


def _load_team(db, owner: str | None, team_id: str) -> AgentTeam | None:
    q = db.query(AgentTeam).filter(AgentTeam.id == team_id, AgentTeam.is_active == True)  # noqa: E712
    if owner is not None:
        q = q.filter(AgentTeam.owner == owner)
    return q.first()


async def run_lead_routed_team(
    *,
    session_id: str,
    user_message: str,
    base_messages: list[dict[str, Any]],
    endpoint_url: str,
    model: str,
    headers: dict | None,
    temperature: float,
    max_tokens: int,
    owner: str | None,
    preset_manager=None,
    llm_call: Callable[..., Awaitable[str]] = llm_call_async,
) -> TeamRunResult | None:
    target_type, team_id = get_session_target(session_id)
    if target_type != "team" or not team_id:
        return None

    db = SessionLocal()
    try:
        team = _load_team(db, owner, team_id)
        if not team or (team.topology or "lead_routed") != "lead_routed":
            return None
        lead = _agent_to_dict(team.leader)
        if not lead:
            return None
        workers = []
        for member in team.members or []:
            if not member.enabled or member.agent_id == team.leader_agent_id:
                continue
            agent = _agent_to_dict(member.agent)
            if not agent:
                continue
            agent["role"] = member.role or "worker"
            agent["order"] = member.sort_order or 0
            workers.append(agent)
        workers.sort(key=lambda row: row.get("order") or 0)
        policy = team.run_policy or {}
        max_steps = int(policy.get("max_steps") or 8)
        workers = workers[: max(0, min(len(workers), max_steps - 2))]
        run = _create_run(db, owner, session_id, "team", team_id, user_message)
        db.commit()
        run_id = run.id
        team_name = team.name
        shared = team.shared_instructions or ""
    finally:
        db.close()

    roster = "\n".join(f"- {w['name']} ({w.get('role', 'worker')}): {w.get('personality', '')[:240]}" for w in workers) or "- No workers configured."
    lead_url, lead_model = _agent_endpoint(lead, endpoint_url, model)
    plan_messages = [
        {"role": "system", "content": (
            f"You are {lead['name']}, lead agent for team '{team_name}'. "
            f"Your persona: {lead.get('personality') or 'Coordinate the team clearly.'}\n"
            f"Shared team instructions: {shared}\n"
            "Create a compact delegation plan. Return concise bullet assignments only."
        )},
        {"role": "user", "content": f"User request:\n{user_message}\n\nAvailable workers:\n{roster}"},
    ]
    plan = await llm_call(lead_url, lead_model, plan_messages, headers=headers, temperature=temperature, max_tokens=min(max_tokens or 800, 1200))

    db = SessionLocal()
    try:
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run:
            _add_step(db, run, 1, "leader_plan", "Leader plan", plan, agent_id=lead["id"], role="leader")
            db.commit()
    finally:
        db.close()

    worker_results = []
    for idx, worker in enumerate(workers, start=2):
        worker_url, worker_model = _agent_endpoint(worker, endpoint_url, model)
        worker_messages = [
            {"role": "system", "content": (
                f"You are {worker['name']} acting as {worker.get('role', 'worker')}. "
                f"Persona: {worker.get('personality') or 'Be precise and concise.'}\n"
                f"Shared team instructions: {shared}\n"
                "Do only your assigned slice. Return findings, risks, and suggested answer fragments."
            )},
            untrusted_context_message("lead delegation plan", plan),
            {"role": "user", "content": user_message},
        ]
        output = await llm_call(worker_url, worker_model, worker_messages, headers=headers, temperature=temperature, max_tokens=max_tokens)
        worker_results.append({"agent_id": worker["id"], "name": worker["name"], "role": worker.get("role"), "output": output})
        db = SessionLocal()
        try:
            run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
            if run:
                _add_step(db, run, idx, "worker_result", worker["name"], output, agent_id=worker["id"], role=worker.get("role"))
                db.commit()
        finally:
            db.close()

    worker_summary = "\n\n".join(f"### {item['name']} ({item.get('role') or 'worker'})\n{item['output']}" for item in worker_results) or "No worker outputs."
    final_messages = list(base_messages) + [
        untrusted_context_message("lead delegation plan", plan),
        untrusted_context_message("worker outputs", worker_summary),
        {"role": "system", "content": (
            f"Now answer as lead agent {lead['name']}. Synthesize the team work into one final user-facing response. "
            "Do not expose raw internal chatter unless useful; mention key team findings briefly."
        )},
    ]
    final = await llm_call(lead_url, lead_model, final_messages, headers=headers, temperature=temperature, max_tokens=max_tokens)

    metadata = {
        "team_run": True,
        "run_id": run_id,
        "team_id": team_id,
        "team_name": team_name,
        "topology": "lead_routed",
        "lead": {"id": lead["id"], "name": lead["name"]},
        "plan": plan,
        "workers": worker_results,
    }
    db = SessionLocal()
    try:
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run:
            _add_step(db, run, len(worker_results) + 2, "final_synthesis", "Final synthesis", final, agent_id=lead["id"], role="leader")
            run.status = "completed"
            run.output = final
            run.meta_data = json.dumps(metadata)
            db.commit()
    finally:
        db.close()

    return TeamRunResult(response=final, metadata=metadata)
