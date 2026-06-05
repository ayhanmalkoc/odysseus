# Odysseus Multi-Agent Teams Analysis

## Executive Summary

Odysseus already has the first layer of multi-agent support: `CrewMember` stores agent personas, model/endpoint overrides, tool permissions, and a linked chat session; `ScheduledTask` can bind execution to a `crew_member_id`; the agent loop can use tools; `send_to_session` enables cross-session messaging. This is enough for a personal assistant and scheduled persona-driven tasks, but not enough for a debt-free, fully managed multi-agent team system.

The debt-free path is to promote the existing implicit “crew member + task + session” concept into explicit domain objects:

- `AgentTeam`: a named team/workspace owned by a user.
- `Agent`: a managed agent profile, likely evolved from or mapped to `CrewMember`.
- `AgentTeamMember`: membership, role, ordering, permissions, status.
- `AgentConversation`: team-scoped communication room/thread.
- `AgentMessage`: durable inter-agent/user/system messages.
- `AgentRun`: a run/orchestration instance for team execution.
- `AgentRunStep`: auditable step/tool/message activity.

This keeps the current assistant feature working while adding a clean bounded context for teams, CRUD, UI management, and agent-to-agent communication.

## Current State

### Existing Capabilities

- `CrewMember` exists in `core/database.py` and stores persona-like agent fields: owner, name, avatar, user_name, personality, model, endpoint_url, enabled_tools, session_id, is_active, sort_order, is_default_assistant, timezone.
- `ScheduledTask` has `crew_member_id`, `session_id`, `model`, `endpoint_url`, `max_steps`, trigger/schedule fields, and task run support.
- `routes/assistant_routes.py` treats the personal assistant as a specially flagged `CrewMember` and exposes assistant settings, check-ins, run-now, and time zone endpoints.
- `src/task_scheduler.py` loads the `CrewMember` for a task and applies persona/model/endpoint/tool filters during LLM task execution.
- `send_to_session` exists as a tool and is described as cross-chat communication/orchestration across sessions.

### Gaps

- No explicit team model.
- No first-class general CRUD API for agents/teams/team memberships.
- No durable inter-agent message model distinct from ordinary chat messages.
- No team run/orchestration model with audit trail.
- No UI dedicated to managing teams, members, roles, routing, run history, communication topology.
- Current `CrewMember` is overloaded: personal assistant, pseudo-agent profile, scheduled-task persona.
- `ScheduledTask.crew_member_id` is a plain nullable string, not a real foreign key.
- `send_to_session` is useful but too generic to be the primary agent-to-agent protocol.

## Target Product Behavior

### Agent Management

Users should be able to create, list, update, archive, clone, and delete agents. Each agent should support:

- identity: name, avatar, description
- instructions: system prompt/personality, role prompt, constraints
- model routing: endpoint, model, temperature/top-p/etc. if supported elsewhere
- tools: allowed tools, denied tools, per-tool config
- memory: shared, private, disabled, scoped recall rules
- status: active, paused, archived
- safety limits: max steps, max tokens, execution timeout, tool budget

### Team Management

Users should be able to create multiple teams. Each team should support:

- name, description, owner
- members with roles: lead, worker, reviewer, researcher, writer, critic, custom
- topology: lead-routed, broadcast, round-robin, graph/manual edges
- communication policy: direct messages allowed, broadcast allowed, user approval gates
- shared memory policy
- default run settings
- templates for common teams

### Agent Communication

Agents should communicate through a durable team conversation/message layer, not by ad-hoc session writes only.

Required message types:

- user_to_team
- user_to_agent
- agent_to_user
- agent_to_agent
- agent_to_team
- system_event
- tool_result
- run_summary

Every message should include sender, recipient scope, team, conversation, run, parent message, metadata, visibility, and timestamps.

### Team Runs

A team run should represent one coordinated job:

- user gives a task to a team
- orchestrator creates an `AgentRun`
- lead/planner decomposes work
- assigned agents execute steps
- agents exchange messages through `AgentMessage`
- optional reviewer validates
- final response is delivered to user/session/task output
- full trace is visible in UI

## Debt-Free Architecture

### Bounded Context

Add a new `agents` bounded context instead of expanding assistant/task routes indefinitely:

- `core/database.py`: persistent models only, or move new models to a dedicated model module if the project accepts it later.
- `src/agents/service.py`: domain service for team/agent CRUD and orchestration.
- `src/agents/schemas.py`: Pydantic request/response models.
- `src/agents/orchestrator.py`: team run state machine.
- `src/agents/message_bus.py`: durable message writes/reads and routing rules.
- `routes/agent_routes.py`: REST API.
- `static/js/agents.js`: UI module.

Avoid adding team logic to `assistant_routes.py`; keep assistant as a special UI over a default agent/member if desired.

### Data Model Proposal

#### `agent_profiles`

Successor to/generalization of `CrewMember`.

- id
- owner
- name
- avatar
- description
- system_prompt
- model
- endpoint_url
- enabled_tools_json
- memory_policy_json
- execution_limits_json
- is_active
- archived_at
- created_at / updated_at

Migration path: keep `crew_members`, add new tables, optionally backfill default assistant into `agent_profiles`. Do not delete `CrewMember` initially.

#### `agent_teams`

- id
- owner
- name
- description
- default_topology
- shared_memory_policy_json
- default_run_config_json
- is_active
- archived_at
- created_at / updated_at

#### `agent_team_members`

- id
- team_id FK
- agent_id FK
- role
- sort_order
- permissions_json
- routing_config_json
- is_active
- created_at / updated_at

Unique constraint: `(team_id, agent_id)`.

#### `agent_conversations`

- id
- team_id FK
- owner
- title
- source_type: manual, scheduled_task, chat_session, webhook
- source_id
- status
- created_at / updated_at

#### `agent_messages`

- id
- conversation_id FK
- team_id FK
- run_id nullable FK
- sender_type: user, agent, system, tool
- sender_agent_id nullable FK
- recipient_type: user, agent, team, system
- recipient_agent_id nullable FK
- parent_message_id nullable FK
- message_type
- content
- metadata_json
- visibility
- created_at

Indexes: conversation/time, team/time, run/time, sender/time, recipient/time.

#### `agent_runs`

- id
- team_id FK
- conversation_id FK
- owner
- objective
- status: queued, running, waiting_for_user, completed, failed, cancelled
- topology
- config_json
- started_at / completed_at
- created_at / updated_at

#### `agent_run_steps`

- id
- run_id FK
- agent_id nullable FK
- step_type: plan, message, tool_call, tool_result, decision, final
- status
- input_json
- output_json
- error
- started_at / completed_at
- created_at

### Relationship To Existing Models

- `CrewMember` remains for backward compatibility with personal assistant.
- Add optional bridge fields later:
  - `crew_members.agent_profile_id`
  - `scheduled_tasks.agent_team_id`
  - `scheduled_tasks.agent_profile_id` or use current `crew_member_id` bridge first.
- Existing `Session`/`ChatMessage` remain user-facing chat history.
- Team internal messages live in `agent_messages`; final summaries can be copied to `ChatMessage`.
- Existing `send_to_session` remains a tool; new `send_agent_message` / `broadcast_team_message` should write to `agent_messages`.

## API Design

Prefix: `/api/agents` for profiles and `/api/agent-teams` for teams.

### Agent Profiles

- `GET /api/agents` list agents
- `POST /api/agents` create agent
- `GET /api/agents/{agent_id}` get agent
- `PATCH /api/agents/{agent_id}` update agent
- `DELETE /api/agents/{agent_id}` archive/delete agent
- `POST /api/agents/{agent_id}/clone` clone agent

### Teams

- `GET /api/agent-teams` list teams
- `POST /api/agent-teams` create team
- `GET /api/agent-teams/{team_id}` get team with members
- `PATCH /api/agent-teams/{team_id}` update team
- `DELETE /api/agent-teams/{team_id}` archive/delete team

### Team Members

- `POST /api/agent-teams/{team_id}/members` add member
- `PATCH /api/agent-teams/{team_id}/members/{member_id}` update role/order/permissions
- `DELETE /api/agent-teams/{team_id}/members/{member_id}` remove member
- `POST /api/agent-teams/{team_id}/members/reorder` reorder members

### Conversations And Messages

- `GET /api/agent-teams/{team_id}/conversations`
- `POST /api/agent-teams/{team_id}/conversations`
- `GET /api/agent-conversations/{conversation_id}/messages`
- `POST /api/agent-conversations/{conversation_id}/messages`

### Runs

- `POST /api/agent-teams/{team_id}/runs` start run
- `GET /api/agent-runs/{run_id}` run status
- `GET /api/agent-runs/{run_id}/steps` run trace
- `POST /api/agent-runs/{run_id}/cancel`
- `POST /api/agent-runs/{run_id}/resume`

## Backend Orchestration

### Minimal State Machine

1. Create run.
2. Write user objective to `agent_messages`.
3. Select team topology.
4. Planner/lead produces plan.
5. Assign steps to agents.
6. Execute each agent through existing agent loop with scoped prompt and allowed tools.
7. Persist every inter-agent message/tool result as `agent_messages` and `agent_run_steps`.
8. Synthesize final answer.
9. Deliver final answer to user session/task target.

### Topologies

Start with three explicit modes:

- lead_routed: one lead agent plans/delegates/synthesizes.
- broadcast_review: all selected agents answer; reviewer/lead synthesizes.
- sequential_pipeline: agents run in configured order.

Avoid arbitrary graph orchestration in v1; add graph topology after traces, permissions, and cancellation are stable.

### Tooling

Add tools usable by agents:

- `send_agent_message`: send direct message to a teammate in the same run/conversation.
- `broadcast_team_message`: send to all active team members.
- `list_team_members`: inspect team members/roles/capabilities.
- `handoff_to_agent`: request another agent to perform a subtask.

These tools must enforce owner/team/run scope; agents must not message arbitrary sessions or users unless policy allows it.

## UI/UX Proposal

Add a dedicated “Agents” workspace in the rail/sidebar.

### Screens

- Agents list: cards/table, search, status, clone/archive.
- Agent editor: identity, prompt, model/endpoint, tools, memory, limits, test prompt.
- Teams list: cards showing members, topology, last run.
- Team builder: drag/drop agents into roles, topology selector, shared settings.
- Team chat/run page: objective input, live trace, agent messages, tool calls, final answer.
- Run history: status, duration, cost/tokens if available, errors, replay.

### UX Principles

- Treat teams as manageable assets, not hidden settings.
- Show what each agent did and why.
- Make communication visible: user/team/agent/tool lanes.
- Provide templates: Research Team, Coding Review Team, Email Triage Team, Writing Team.
- Safe defaults: limited tools, bounded steps, explicit external-send permissions.

## Migration Strategy

### Phase 1: Foundations

- Add DB tables for teams, profiles, memberships, conversations, messages, runs, steps.
- Add schemas/services/routes with CRUD only.
- Backfill current default assistant as an agent profile or expose read-only bridge.
- Add tests for owner isolation, CRUD, soft delete, membership constraints.

### Phase 2: UI CRUD

- Add `static/js/agents.js` and UI panels.
- Create/manage agents and teams.
- No orchestration yet beyond manual test calls.

### Phase 3: Communication Layer

- Add durable message bus service.
- Add `send_agent_message`, `broadcast_team_message`, `list_team_members` tools.
- Add tests for scope enforcement and message ordering.

### Phase 4: Team Runs

- Implement lead_routed and sequential_pipeline.
- Persist run steps and expose status/trace APIs.
- Deliver final run output to chat/session/task.

### Phase 5: Scheduled Team Tasks

- Extend `ScheduledTask` with `agent_team_id` and run config.
- Allow tasks to target a team instead of a single crew member.
- Keep old `crew_member_id` behavior untouched.

### Phase 6: Advanced UX

- Live run trace.
- Templates.
- Visual topology.
- Run replay and debugging.

## Technical Debt Avoidance Rules

- Do not overload `assistant_routes.py` with team features.
- Do not use `ChatMessage` as the only inter-agent message store.
- Do not encode team topology only in prompts; persist it structurally.
- Do not let agents call `send_to_session` for internal team messaging by default.
- Do not hard-delete active agents/teams; use archive/soft-delete first.
- Do not create direct cyclic DB dependencies with existing sessions/tasks unless needed.
- Do not ship orchestration before CRUD, ownership, audit, cancellation, and trace basics are tested.

## Recommended First Implementation Slice

The cleanest first PR should be CRUD-only:

1. Add new agent/team DB models.
2. Add service layer with owner-scoped CRUD.
3. Add REST routes.
4. Add tests for permissions, membership constraints, archive behavior.
5. Add minimal UI list/editor.

Then add communication and runs in separate PRs. This avoids coupling UI, DB migrations, orchestration, and agent-loop behavior into one high-risk patch.
