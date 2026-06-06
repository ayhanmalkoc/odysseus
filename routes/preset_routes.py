"""Preset routes — /api/presets GET, /api/presets/custom POST, user templates CRUD."""

import logging
import uuid
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field, ValidationError, field_validator

from src.request_models import PresetUpdateRequest
from core.middleware import require_admin

logger = logging.getLogger(__name__)



class GroupMemberRequest(BaseModel):
    crew_member_id: str = Field(..., min_length=1, max_length=160)
    role: str = Field("worker", min_length=1, max_length=80)
    order: int = Field(0, ge=0, le=1000)
    enabled: bool = True

class GroupRunConfigRequest(BaseModel):
    max_steps: int = Field(8, ge=1, le=64)
    parallel: bool = False
    show_activity: bool = True

class GroupPresetRequest(BaseModel):
    id: str = Field("", max_length=120)
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=1000)
    lead_crew_member_id: str = Field(..., min_length=1, max_length=160)
    members: List[GroupMemberRequest] = Field(default_factory=list)
    topology: str = Field("lead_routed", pattern="^(lead_routed|sequential_pipeline|broadcast_review)$")
    shared_instructions: str = Field("", max_length=10000)
    run_config: GroupRunConfigRequest = Field(default_factory=GroupRunConfigRequest)

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value):
        return (value or "").strip()

    @field_validator("lead_crew_member_id")
    @classmethod
    def normalize_lead(cls, value):
        return value.strip()


def _normalize_group(req: GroupPresetRequest) -> Dict[str, Any]:
    group = req.model_dump()
    if not group["id"]:
        group["id"] = f"group-{uuid.uuid4().hex[:8]}"
    seen = set()
    members = []
    for member in group.get("members") or []:
        crew_id = (member.get("crew_member_id") or "").strip()
        if not crew_id or crew_id in seen:
            continue
        seen.add(crew_id)
        member["crew_member_id"] = crew_id
        members.append(member)
    group["members"] = members
    return group

class UserTemplateRequest(BaseModel):
    id: str = ""
    name: str = Field(..., min_length=1, max_length=100)
    system_prompt: str = Field("", max_length=10000)
    temperature: float = Field(1.0, ge=0.0, le=2.0)
    max_tokens: int = Field(0, ge=0, le=65536)


def setup_preset_routes(preset_manager) -> APIRouter:
    router = APIRouter(tags=["presets"])

    @router.get("/api/presets")
    async def get_presets() -> Dict[str, Any]:
        return preset_manager.presets

    @router.post("/api/presets/custom")
    async def update_custom_preset(preset_update: PresetUpdateRequest, _admin: None = Depends(require_admin)) -> Dict[str, Any]:
        try:
            success = preset_manager.update_custom(
                preset_update.temperature,
                preset_update.max_tokens,
                preset_update.system_prompt,
                preset_update.name,
                preset_update.enabled,
                preset_update.inject_prefix,
                preset_update.inject_suffix,
            )
            if success:
                return {"success": True, "message": "Custom preset updated"}
            return {"success": False, "message": "Failed to save preset"}
        except Exception as e:
            logger.error(f"Preset update error: {e}")
            raise HTTPException(500, "Failed to update custom preset")

    @router.get("/api/presets/templates")
    async def get_user_templates() -> List[Dict]:
        return preset_manager.get_user_templates()

    @router.post("/api/presets/templates")
    async def save_user_template(req: UserTemplateRequest, _admin: None = Depends(require_admin)) -> Dict[str, Any]:
        template = req.model_dump()
        if not template["id"]:
            template["id"] = f"user-{uuid.uuid4().hex[:8]}"
        success = preset_manager.save_user_template(template)
        if success:
            return {"success": True, "template": template}
        return {"success": False, "message": "Failed to save template"}

    @router.delete("/api/presets/templates/{template_id}")
    async def delete_user_template(template_id: str, _admin: None = Depends(require_admin)) -> Dict[str, Any]:
        success = preset_manager.delete_user_template(template_id)
        if success:
            return {"success": True}
        return {"success": False, "message": "Failed to delete template"}

    @router.post("/api/presets/expand")
    async def expand_character_prompt(request: Request) -> Dict[str, Any]:
        """Use AI to expand a rough character description into a full system prompt."""
        from src.ai_interaction import _resolve_model
        from src.llm_core import llm_call_async

        data = await request.json()
        draft = (data.get("prompt") or "").strip()
        name = (data.get("name") or "").strip()

        if not draft and not name:
            return {"success": False, "message": "Nothing to expand"}

        user_input = ""
        if name:
            user_input += f"Character name: {name}\n"
        if draft:
            user_input += f"Notes: {draft}\n"

        messages = [
            {"role": "system", "content": (
                "You are an expert at writing character system prompts for AI assistants. "
                "The user will give you a character name and/or rough notes. "
                "Write a concise, effective system prompt (3-6 sentences) that captures the character's personality, "
                "speaking style, knowledge areas, and behavioral guidelines. "
                "Output ONLY the system prompt text — no quotes, no preamble, no explanation."
            )},
            {"role": "user", "content": user_input},
        ]

        try:
            model_spec = data.get("model") or ""
            url, model, headers = _resolve_model(model_spec)
            result = await llm_call_async(url, model, messages, temperature=0.8, max_tokens=500, headers=headers)
            return {"success": True, "prompt": result.strip()}
        except Exception as e:
            logger.error(f"Expand prompt failed: {e}")
            return {"success": False, "message": str(e)}

    # ── Group presets ──
    @router.get("/api/presets/groups")
    async def get_group_presets():
        raise HTTPException(410, "Legacy group presets were removed. Use /api/agent-teams.")

    @router.post("/api/presets/groups")
    async def create_or_replace_group_presets(request: Request, _admin: None = Depends(require_admin)):
        raise HTTPException(410, "Legacy group presets were removed. Use /api/agent-teams.")
        """Create one group preset, or replace all presets for legacy callers passing {groups: [...]}."""
        data = await request.json()
        try:
            if isinstance(data, dict) and isinstance(data.get("groups"), list):
                groups = [_normalize_group(GroupPresetRequest(**group)) for group in data.get("groups", [])]
                preset_manager.save_group_presets(groups)
                return {"ok": True, "groups": groups}
            group = _normalize_group(GroupPresetRequest(**data))
        except ValidationError as exc:
            raise HTTPException(422, exc.errors()) from exc
        groups = preset_manager.get_group_presets()
        if any(existing.get("id") == group["id"] for existing in groups):
            raise HTTPException(409, "Group preset already exists")
        groups.append(group)
        preset_manager.save_group_presets(groups)
        return {"ok": True, "group": group}

    @router.get("/api/presets/groups/{group_id}")
    async def get_group_preset(group_id: str):
        raise HTTPException(410, "Legacy group presets were removed. Use /api/agent-teams.")

    @router.patch("/api/presets/groups/{group_id}")
    async def update_group_preset(group_id: str, req: GroupPresetRequest, _admin: None = Depends(require_admin)):
        raise HTTPException(410, "Legacy group presets were removed. Use /api/agent-teams.")
        group = _normalize_group(req)
        group["id"] = group_id
        groups = preset_manager.get_group_presets()
        for idx, existing in enumerate(groups):
            if existing.get("id") == group_id:
                groups[idx] = group
                preset_manager.save_group_presets(groups)
                return {"ok": True, "group": group}
        raise HTTPException(404, "Group preset not found")

    @router.delete("/api/presets/groups/{group_id}")
    async def delete_group_preset(group_id: str, _admin: None = Depends(require_admin)):
        raise HTTPException(410, "Legacy group presets were removed. Use /api/agent-teams.")
        groups = preset_manager.get_group_presets()
        next_groups = [group for group in groups if group.get("id") != group_id]
        if len(next_groups) == len(groups):
            raise HTTPException(404, "Group preset not found")
        preset_manager.save_group_presets(next_groups)
        return {"ok": True}

    return router
