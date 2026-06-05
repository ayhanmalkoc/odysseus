# Agent Teams PR Summary

## Summary

This branch adds an agent-team MVP that evolves existing Odysseus primitives instead of introducing a new heavy domain model immediately. It uses `CrewMember` for agent profiles, existing `group_presets` for team definitions, `Session` binding for team chats, and `ScheduledTask` binding for team automation.

## Implemented

- Agent profile CRUD backed by `CrewMember`.
- Validated team/group preset CRUD.
- Agents & Teams UI modal.
- New chat binding for single-agent and team chats.
- Lead-routed team chat execution.
- Team Activity panel in chat history and streaming.
- Scheduled task team target support.

## Testing

Validated with:

```bash
python3 -m py_compile core/database.py routes/agent_routes.py routes/preset_routes.py routes/session_routes.py routes/task_routes.py routes/chat_routes.py src/agent_team_runner.py src/task_scheduler.py app.py
node --check static/js/agents.js
node --check static/js/sessions.js
node --check static/js/chat.js
node --check static/js/chatRenderer.js
node --check static/js/tasks.js
/tmp/odysseus-test-venv/bin/python -m pytest tests/test_agent_routes.py tests/test_group_preset_routes.py tests/test_session_agent_binding.py tests/test_agent_team_runner.py tests/test_task_team_automation.py -q
```

## Review Notes

- This intentionally does not add full `AgentTeam`, `AgentRun`, or `AgentMessage` tables yet.
- `group_presets` remain the team config storage layer for a smaller, repo-aligned MVP.
- Team trace is stored in assistant message metadata and rendered as Team Activity.
- `lead_routed` is the only executed topology in this branch.

## Smoke Notes

- App import smoke passed with `AUTH_ENABLED=false ODYSSEUS_SKIP_ADMIN_PROMPT=1 ODYSSEUS_SKIP_RUN_HINT=1`.
- Existing SQLite DB migration for `sessions.group_preset_id` and `scheduled_tasks.group_preset_id` was verified.
- ChromaDB was reachable in the local environment during smoke; HTTP embedding API was unavailable and app fell back to local FastEmbed.

## Manual UI Checklist For Reviewer

- Open rail → Agents & Teams.
- Create one lead agent and one worker agent.
- Create a team preset with the lead and worker.
- Click Team chat and send a message.
- Confirm final answer appears and Team Activity shows lead plan + worker output.
- Open Tasks → create Prompt task → Target team → run now.
- Confirm task session receives team final answer and Team Activity metadata renders.
