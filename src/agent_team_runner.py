"""Lead-routed team run MVP on top of CrewMember + group_presets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from core.database import CrewMember, Session as DbSession, SessionLocal
from src.llm_core import llm_call_async
from src.prompt_security import untrusted_context_message


@dataclass
class TeamRunResult:
    response: str
    metadata: dict[str, Any]


def get_session_group_preset_id(session_id: str) -> str | None:
    db = SessionLocal()
    try:
        row = db.query(DbSession).filter(DbSession.id == session_id).first()
        return (getattr(row, "group_preset_id", None) or "").strip() or None
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


def _load_agent(agent_id: str, owner: str | None) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        query = db.query(CrewMember).filter(CrewMember.id == agent_id, CrewMember.is_active == True)  # noqa: E712
        if owner is not None:
            query = query.filter(CrewMember.owner == owner)
        return _agent_to_dict(query.first())
    finally:
        db.close()


def _find_group(preset_manager, group_id: str) -> dict[str, Any] | None:
    for group in preset_manager.get_group_presets():
        if group.get("id") == group_id:
            return group
    return None


def _resolve_members(group: dict[str, Any], owner: str | None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    lead = _load_agent(group.get("lead_crew_member_id") or "", owner)
    members = []
    seen = set()
    for item in group.get("members") or []:
        if item.get("enabled") is False:
            continue
        crew_id = (item.get("crew_member_id") or "").strip()
        if not crew_id or crew_id in seen or crew_id == (lead or {}).get("id"):
            continue
        agent = _load_agent(crew_id, owner)
        if not agent:
            continue
        agent["role"] = item.get("role") or "worker"
        agent["order"] = item.get("order") or 0
        members.append(agent)
        seen.add(crew_id)
    members.sort(key=lambda row: row.get("order") or 0)
    return lead, members


def _agent_endpoint(agent: dict[str, Any], fallback_url: str, fallback_model: str) -> tuple[str, str]:
    return agent.get("endpoint_url") or fallback_url, agent.get("model") or fallback_model


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
    preset_manager,
    llm_call: Callable[..., Awaitable[str]] = llm_call_async,
) -> TeamRunResult | None:
    group_id = get_session_group_preset_id(session_id)
    if not group_id:
        return None
    group = _find_group(preset_manager, group_id)
    if not group:
        return None
    if (group.get("topology") or "lead_routed") != "lead_routed":
        return None

    lead, workers = _resolve_members(group, owner)
    if not lead:
        return None

    max_steps = int(((group.get("run_config") or {}).get("max_steps") or 8))
    max_workers = max(0, min(len(workers), max_steps - 2))
    workers = workers[:max_workers]
    shared = group.get("shared_instructions") or ""
    roster = "\n".join(f"- {w['name']} ({w.get('role', 'worker')}): {w.get('personality', '')[:240]}" for w in workers) or "- No workers configured."

    lead_url, lead_model = _agent_endpoint(lead, endpoint_url, model)
    plan_messages = [
        {"role": "system", "content": (
            f"You are {lead['name']}, lead agent for team '{group.get('name')}'. "
            f"Your persona: {lead.get('personality') or 'Coordinate the team clearly.'}\n"
            f"Shared team instructions: {shared}\n"
            "Create a compact delegation plan. Return concise bullet assignments only."
        )},
        {"role": "user", "content": f"User request:\n{user_message}\n\nAvailable workers:\n{roster}"},
    ]
    plan = await llm_call(lead_url, lead_model, plan_messages, headers=headers, temperature=temperature, max_tokens=min(max_tokens or 800, 1200))

    worker_results = []
    for worker in workers:
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

    worker_summary = "\n\n".join(
        f"### {item['name']} ({item.get('role') or 'worker'})\n{item['output']}" for item in worker_results
    ) or "No worker outputs."
    final_messages = list(base_messages) + [
        untrusted_context_message("lead delegation plan", plan),
        untrusted_context_message("worker outputs", worker_summary),
        {"role": "system", "content": (
            f"Now answer as lead agent {lead['name']}. Synthesize the team work into one final user-facing response. "
            "Do not expose raw internal chatter unless useful; mention key team findings briefly."
        )},
    ]
    final = await llm_call(lead_url, lead_model, final_messages, headers=headers, temperature=temperature, max_tokens=max_tokens)
    return TeamRunResult(
        response=final,
        metadata={
            "team_run": True,
            "team_id": group_id,
            "team_name": group.get("name"),
            "topology": "lead_routed",
            "lead": {"id": lead["id"], "name": lead["name"]},
            "plan": plan,
            "workers": worker_results,
        },
    )
