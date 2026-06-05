# Multi-Agent Teams Decision and Implementation Plan

## Decision

Build Odysseus multi-agent teams as a first-class product surface, not as an extension of the existing personal assistant settings. The feature will introduce explicit team, agent, membership, conversation, message, run, and run-step models while preserving the current `CrewMember`-based personal assistant behavior.

The default UX will be: create or select an agent team, start a new chat with that team, talk to the lead agent, and let the lead coordinate workers/reviewers through a durable internal team communication layer. Team activity, messages, tool calls, and final output must be visible and auditable.

## Goals

- Users can create, edit, archive, clone, and delete agents.
- Users can create multiple teams with roles, topology, shared settings, and member permissions.
- A new chat can be bound to a selected team.
- The lead agent can plan, delegate, coordinate, synthesize, and respond to the user.
- Worker agents can communicate with lead/teammates through scoped team messages.
- Runs have durable trace, status, cancellation, errors, and final outputs.
- Scheduled tasks/webhooks can later target a team using the same run infrastructure.
- Existing assistant/check-in behavior remains backward compatible.

## Non-Goals For V1

- Arbitrary graph orchestration UI.
- Multi-tenant enterprise permissions beyond current owner isolation.
- Cost accounting if token/cost plumbing is not already reliable.
- Removing or replacing `CrewMember`.
- Fully autonomous always-on agents without explicit schedule/event/user trigger.

## Architecture Principles

- Keep `assistant_routes.py` focused on the personal assistant.
- Add a dedicated agents bounded context.
- Persist topology, roles, messages, and runs structurally; do not hide them only in prompts.
- Keep user chat history separate from internal agent messages.
- Every inter-agent action must be owner/team/run scoped.
- Prefer soft-delete/archive for agents and teams.
- Add orchestration only after CRUD, ownership, message persistence, and run trace exist.

## Proposed Modules

- `src/agents/schemas.py`: Pydantic request/response schemas.
- `src/agents/service.py`: owner-scoped CRUD and validation.
- `src/agents/message_bus.py`: durable team message API.
- `src/agents/orchestrator.py`: team run state machine.
- `src/agents/tools.py`: agent-team tool handlers.
- `routes/agent_routes.py`: REST endpoints.
- `static/js/agents.js`: agent/team management UI.
- `tests/test_agent_teams_*.py`: DB/API/service/orchestration tests.

## Data Model Plan

### `agent_profiles`

Fields:

- `id`, `owner`, `name`, `avatar`, `description`
- `system_prompt`, `model`, `endpoint_url`
- `enabled_tools` JSON text
- `memory_policy` JSON text
- `execution_limits` JSON text
- `is_active`, `archived_at`, timestamps

Purpose: reusable managed agent/persona. This is the long-term replacement/generalization for `CrewMember`, but no destructive migration in V1.

### `agent_teams`

Fields:

- `id`, `owner`, `name`, `description`
- `default_topology`
- `shared_memory_policy` JSON text
- `default_run_config` JSON text
- `is_active`, `archived_at`, timestamps

Purpose: named team config selected by chat/task/webhook.

### `agent_team_members`

Fields:

- `id`, `team_id`, `agent_id`
- `role`, `sort_order`
- `permissions` JSON text
- `routing_config` JSON text
- `is_active`, timestamps

Constraints:

- `(team_id, agent_id)` unique.
- owner isolation validated through team/profile owner checks.

### `agent_conversations`

Fields:

- `id`, `team_id`, `owner`, `title`
- `source_type`, `source_id`
- `status`, timestamps

Purpose: team-scoped communication thread. A user chat session may point to one conversation, but internal messages live here.

### `agent_messages`

Fields:

- `id`, `conversation_id`, `team_id`, `run_id`
- `sender_type`, `sender_agent_id`
- `recipient_type`, `recipient_agent_id`
- `parent_message_id`, `message_type`
- `content`, `metadata` JSON text
- `visibility`, `created_at`

Purpose: durable user/team/agent/system/tool communication.

### `agent_runs`

Fields:

- `id`, `team_id`, `conversation_id`, `owner`
- `objective`, `status`, `topology`
- `config` JSON text
- `started_at`, `completed_at`, timestamps

Purpose: one coordinated job execution.

### `agent_run_steps`

Fields:

- `id`, `run_id`, `agent_id`
- `step_type`, `status`
- `input` JSON text, `output` JSON text
- `error`, `started_at`, `completed_at`, `created_at`

Purpose: trace/debug/audit.

## API Plan

### Agent Profiles

- `GET /api/agents`
- `POST /api/agents`
- `GET /api/agents/{agent_id}`
- `PATCH /api/agents/{agent_id}`
- `DELETE /api/agents/{agent_id}`
- `POST /api/agents/{agent_id}/clone`

### Teams

- `GET /api/agent-teams`
- `POST /api/agent-teams`
- `GET /api/agent-teams/{team_id}`
- `PATCH /api/agent-teams/{team_id}`
- `DELETE /api/agent-teams/{team_id}`

### Team Members

- `POST /api/agent-teams/{team_id}/members`
- `PATCH /api/agent-teams/{team_id}/members/{member_id}`
- `DELETE /api/agent-teams/{team_id}/members/{member_id}`
- `POST /api/agent-teams/{team_id}/members/reorder`

### Conversations And Messages

- `GET /api/agent-teams/{team_id}/conversations`
- `POST /api/agent-teams/{team_id}/conversations`
- `GET /api/agent-conversations/{conversation_id}/messages`
- `POST /api/agent-conversations/{conversation_id}/messages`

### Runs

- `POST /api/agent-teams/{team_id}/runs`
- `GET /api/agent-runs/{run_id}`
- `GET /api/agent-runs/{run_id}/steps`
- `POST /api/agent-runs/{run_id}/cancel`
- `POST /api/agent-runs/{run_id}/resume`

## Chat UX Plan

### New Chat Flow

1. User clicks New Chat.
2. UI offers mode selector: normal chat or team chat.
3. User selects a team.
4. System creates or links an `AgentConversation`.
5. User message starts an `AgentRun`.
6. Lead agent responds in the normal chat stream.
7. Team activity panel shows internal planning, messages, tool calls, and progress.
8. Final response appears as the lead answer.

### Team Activity Panel

Sections:

- Plan
- Messages
- Tool calls
- Artifacts/results
- Errors/warnings
- Final synthesis

Default collapsed for casual users; expanded for power users/debugging.

## Orchestration Plan

### V1 Topologies

- `lead_routed`: lead plans, delegates, synthesizes.
- `sequential_pipeline`: agents run in configured order.
- `broadcast_review`: multiple agents answer, lead/reviewer synthesizes.

### Lead-Routed Flow

1. Create run.
2. Add user objective message.
3. Load team members and roles.
4. Run lead planner.
5. Persist plan step.
6. For each assignment, run selected agent with scoped prompt.
7. Persist worker messages/results.
8. Run reviewer if configured.
9. Run lead synthesis.
10. Write final response to chat/session output.

### Agent Team Tools

- `list_team_members`
- `send_agent_message`
- `broadcast_team_message`
- `handoff_to_agent`

All tools enforce owner/team/conversation/run scope.

## UI Plan

### Agents Workspace

- Agents list: card/table view, search, active/archive filter.
- Agent editor: identity, prompt, model, endpoint, tools, memory, limits.
- Team list: members, topology, status, last run.
- Team builder: add/remove/reorder members, assign roles, configure topology.
- Team run page: objective, live status, trace, messages, final output.
- Run history: past runs, steps, errors, replay entry point.

### Templates

Ship after CRUD works:

- Research Team
- Coding Review Team
- Writing Team
- Email Triage Team
- Planning Team

## Implementation Phases

### Phase 1 — DB And Service CRUD

Deliverables:

- Add SQLAlchemy models.
- Add schemas.
- Add service functions.
- Add owner-scoped validation.
- Add archive behavior.
- Add CRUD tests.

Exit criteria:

- Agents/teams/members can be created and queried by owner.
- Cross-owner access is denied.
- Deleting a team/agent archives safely.

### Phase 2 — REST API

Deliverables:

- Add `routes/agent_routes.py`.
- Register router in `app.py`.
- Add API tests.

Exit criteria:

- Full CRUD works through HTTP.
- Membership constraints are enforced.
- API payloads do not leak other owners' data.

### Phase 3 — Minimal UI

Deliverables:

- Add Agents rail/sidebar entry.
- Add list/editor/team builder views.
- Wire API calls.

Exit criteria:

- User can manage agents and teams from UI.
- Existing assistant UI remains unchanged.

### Phase 4 — Message Bus

Deliverables:

- Add conversation/message persistence service.
- Add message APIs.
- Add agent-team tools.
- Add ordering/scope tests.

Exit criteria:

- Agents can send scoped messages to team/teammates.
- Messages are visible in team activity view.

### Phase 5 — Team Runs

Deliverables:

- Add run/step service.
- Implement `lead_routed` and `sequential_pipeline`.
- Persist status, errors, cancellation.
- Deliver final result to chat.

Exit criteria:

- User can start a team chat and receive a final lead response.
- Run trace is complete and inspectable.

### Phase 6 — Automation Targets

Deliverables:

- Extend scheduled tasks with `agent_team_id`.
- Allow webhooks/tasks to start team runs.
- Add run history UX.

Exit criteria:

- Teams can run manually, by schedule, and by webhook/event.

## Test Strategy

- Unit tests for service validation and archive behavior.
- API tests for owner isolation and CRUD.
- Message ordering tests.
- Tool scope enforcement tests.
- Orchestrator tests with mocked agent loop.
- Regression tests ensuring personal assistant routes still work.

## Open Questions

- Whether to bridge `CrewMember` to `AgentProfile` immediately or keep them separate for V1.
- Whether chat session should store `agent_team_id` directly or link through `AgentConversation.source_id`.
- How much live streaming the team activity panel needs in first UI release.
- Whether model parameters beyond endpoint/model are already standardized enough to expose per agent.

## First PR Recommendation

Start with Phase 1 and Phase 2 only: DB models, service layer, REST CRUD, tests. Do not implement orchestration in the first PR. This creates a stable foundation and avoids debt from mixing migrations, UI, and run logic in one change.

## Product Capability Matrix After Delivery

| Product Capability | Backend Capability | Frontend / UX Capability | Product Level Outcome | V1 | V2 |
|---|---|---|---|---|---|
| Agent profile management | `agent_profiles` CRUD, owner isolation, archive/clone, tool/model/prompt config persistence | Agents list, create/edit modal/page, clone/archive controls, tool/model selectors | Users can manage reusable specialist agents as product assets | Yes | Enhanced templates/import-export |
| Team management | `agent_teams` CRUD, team config, topology config, shared policies | Teams list, team detail page, team builder | Users can create multiple named agent teams for different workflows | Yes | Marketplace/team templates |
| Team membership | `agent_team_members`, roles, ordering, permissions, membership validation | Drag/drop or ordered member list, role selector, permission panel | Users can assemble a team with lead/worker/reviewer roles | Yes | Graph topology editor |
| Team chat selection | Chat/session integration with selected `team_id`/conversation binding | New Chat mode selector: Normal vs Team, team picker | Users can start a chat with a selected team | Yes | Suggested teams by task type |
| Lead-led execution | `AgentRun` orchestration, lead-routed topology, scoped agent-loop calls | Chat flows through lead agent; final response appears normally | Lead agent plans, delegates, synthesizes, reports back | Yes | Multi-lead/manager hierarchy |
| Worker execution | Per-agent run steps, model/endpoint/tool overrides, limits | Activity panel shows worker assignments/results | Specialist agents perform delegated subtasks | Yes | Parallel worker fan-out controls |
| Inter-agent messaging | `agent_messages`, message bus, `send_agent_message`, `broadcast_team_message`, scope enforcement | Team activity timeline with agent-to-agent messages | Agents can communicate durably and audibly inside a team | Yes | Live streaming + threaded replies |
| Run trace / audit | `agent_runs`, `agent_run_steps`, status/errors/timestamps, cancellation hooks | Run detail panel: plan, steps, tool calls, errors, final | Users can inspect what happened and debug failures | Yes | Replay/fork run |
| Tool governance | Per-agent `enabled_tools`, team permissions, tool scope checks | Tool permission UI per agent/team | Teams are powerful but controlled/safe | Yes | Approval gates per tool/risk |
| Memory policy | Agent/team memory policy fields, retrieval scope hooks | Memory mode controls: private/shared/off | Teams can use shared or private context intentionally | Partial | Full memory UX + analytics |
| Scheduled team automation | `ScheduledTask.agent_team_id`, run target adapter | Task form can target agent/team | Existing automation can run whole teams, not single assistant only | No | Yes |
| Webhook/event automation | Team run creation from webhook/event source | Automation setup selects target team | External events can trigger agent teams | No | Yes |
| Templates | Seed data/service for common team blueprints | Template gallery: Research, Coding Review, Writing, Email Triage | Faster onboarding and product polish | Partial | Yes |
| Observability | Run/message/step metrics, error summaries | Run history, filters, status badges | Product feels manageable, not black-box | Partial | Full dashboards |
| Backward compatibility | Existing `CrewMember`, assistant routes, tasks preserved | Current Assistant UI unchanged | No regression to existing personal assistant/check-ins | Yes | Optional migration bridge |

## Backend Deliverables By Layer

| Layer | Files / Modules | Responsibility | Done When |
|---|---|---|---|
| Persistence | `core/database.py` or dedicated agent model module | Agent/team/message/run tables and indexes | DB creates cleanly; owner-scoped tests pass |
| Schemas | `src/agents/schemas.py` | API contracts and validation | Invalid payloads fail predictably |
| Domain service | `src/agents/service.py` | CRUD, archive, clone, membership rules | No route contains business logic bulk |
| Message bus | `src/agents/message_bus.py` | Durable scoped messages | Ordering/scope tests pass |
| Orchestrator | `src/agents/orchestrator.py` | Run state machine and topology execution | Mocked runs complete with trace |
| Tools | `src/agents/tools.py`, existing tool registry files | Agent-team messaging/handoff/list tools | Tools enforce team/run scope |
| API | `routes/agent_routes.py`, `app.py` router registration | REST endpoints | HTTP CRUD/run tests pass |
| Task bridge | `src/task_scheduler.py`, `routes/task_routes.py` | Scheduled tasks target teams | Existing task tests still pass |

## Frontend Deliverables By Surface

| Surface | Files / Modules | UX Responsibility | Done When |
|---|---|---|---|
| Navigation | `static/index.html`, existing rail JS | Add Agents workspace entry | Users can open Agents area |
| Agent manager | `static/js/agents.js` | Agent list/create/edit/archive/clone | Full agent CRUD works from UI |
| Team manager | `static/js/agents.js` | Team list/detail/team builder | Users can assemble teams and roles |
| Chat integration | existing chat/session JS + team selector | Start chat with selected team | User message starts team conversation/run |
| Activity panel | new or existing chat side panel | Show plan/messages/tool calls/run status | User can inspect team work |
| Run history | `static/js/agents.js` | Past runs, status, errors, final output | Debuggable product workflow |
| Settings reuse | existing settings/model/tool selectors | Reuse endpoint/model/tool picker patterns | No duplicate config UX |

## Product Maturity Gates

| Gate | Requirement | Blocks Release If Missing |
|---|---|---|
| Foundation | CRUD + owner isolation + archive behavior + tests | Yes |
| Usability | UI can create agents, create teams, assign roles | Yes |
| Chat Product | New chat can select team and receive lead final answer | Yes |
| Transparency | Activity/run trace visible for every team run | Yes |
| Safety | Tool/message scope enforced server-side | Yes |
| Compatibility | Existing assistant/check-in/task behavior unchanged | Yes |
| Automation | Scheduled/webhook team runs | No for V1, yes for automation release |
| Polish | Templates, replay, dashboards | No for V1 |
