import uiModule from './ui.js';

const API_BASE = window.API_BASE || '';
let modalEl = null;
let agents = [];
let teams = [];
let personas = [];
let roles = [];
let runs = [];

function esc(value) {
  return String(value || '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function jsonFetch(url, options = {}) {
  const res = await fetch(`${API_BASE}${url}`, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`);
  return data;
}

function ensureModal() {
  if (modalEl) return modalEl;
  const el = document.createElement('div');
  el.className = 'modal';
  el.id = 'agents-modal';
  el.innerHTML = `
    <div class="modal-content" style="max-width:1080px;width:96%;max-height:88vh;">
      <div class="modal-header"><h4>Agents & Teams</h4><button class="close-btn" id="agents-close">✖</button></div>
      <div class="modal-body" id="agents-body"></div>
    </div>`;
  document.body.appendChild(el);
  el.querySelector('#agents-close').addEventListener('click', closeAgents);
  el.addEventListener('click', (event) => { if (event.target === el) closeAgents(); });
  modalEl = el;
  return el;
}

function closeAgents() { if (modalEl) modalEl.style.display = 'none'; }

async function loadData() {
  const [agentData, teamData, personaData, roleData, runData] = await Promise.all([
    jsonFetch('/api/agents?include_inactive=true'),
    jsonFetch('/api/agent-teams?include_inactive=true'),
    jsonFetch('/api/agent-personas?include_inactive=true'),
    jsonFetch('/api/agent-roles'),
    jsonFetch('/api/agent-runs'),
  ]);
  agents = agentData.agents || [];
  teams = teamData.teams || [];
  personas = personaData.personas || [];
  roles = roleData.roles || [];
  runs = runData.runs || [];
}

function agentOptions(selected = '') {
  return agents.filter((a) => a.is_active).map((a) => `<option value="${esc(a.id)}"${a.id === selected ? ' selected' : ''}>${esc(a.name)}</option>`).join('');
}

function roleOptions(selected = 'worker') {
  const base = roles.length ? roles : [{ name: 'worker' }, { name: 'researcher' }, { name: 'coder' }, { name: 'reviewer' }];
  return base.map((r) => `<option value="${esc(r.name)}"${r.name === selected ? ' selected' : ''}>${esc(r.name)}</option>`).join('');
}

function chatTargetOptions() {
  const agentOpts = agents.filter((a) => a.is_active).map((a) => `<option value="agent:${esc(a.id)}">Agent · ${esc(a.name)}</option>`).join('');
  const teamOpts = teams.filter((t) => t.is_active).map((t) => `<option value="team:${esc(t.id)}">Team · ${esc(t.name)}</option>`).join('');
  return `<option value="chat:">Chat</option>${agentOpts ? '<optgroup label="Agents">' + agentOpts + '</optgroup>' : ''}${teamOpts ? '<optgroup label="Teams">' + teamOpts + '</optgroup>' : ''}`;
}

function showChatTarget(kind, name) {
  const pill = document.getElementById('agent-chat-target-pill');
  if (!pill) return;
  if (!kind || kind === 'chat') { pill.style.display = 'none'; pill.innerHTML = ''; return; }
  pill.style.display = 'flex';
  pill.innerHTML = `<span>${esc(kind === 'team' ? 'Team' : 'Agent')}: <strong>${esc(name)}</strong></span><button type="button" id="agent-chat-target-clear" title="Clear target">×</button>`;
  pill.querySelector('#agent-chat-target-clear')?.addEventListener('click', () => { showChatTarget('', ''); window.sessionModule?.setNextChatBinding?.({ targetType: 'chat', targetId: '' }); });
}

function render() {
  const body = ensureModal().querySelector('#agents-body');
  body.innerHTML = `
    <section class="agent-team-launcher">
      <div><strong>Start a chat</strong><div class="muted">Choose Chat, one Agent, or a Team. The session stores this target.</div></div>
      <select id="agent-team-chat-target">${chatTargetOptions()}</select>
      <button class="btn" id="agent-team-start-chat">Start</button>
    </section>
    <div class="agent-team-tabs">
      <button class="btn btn-small active" data-agent-tab="agents">Agents</button>
      <button class="btn btn-small" data-agent-tab="teams">Teams</button>
      <button class="btn btn-small" data-agent-tab="runs">Runs</button>
    </div>
    <div id="agent-tab-agents" class="agent-tab-panel">${renderAgentsPanel()}</div>
    <div id="agent-tab-teams" class="agent-tab-panel" style="display:none;">${renderTeamsPanel()}</div>
    <div id="agent-tab-runs" class="agent-tab-panel" style="display:none;">${renderRunsPanel()}</div>`;
  wireEvents(body);
}

function renderAgentsPanel() {
  return `<section class="panel" style="padding:12px;border:1px solid var(--border);border-radius:10px;"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px;"><h3 style="margin:0;">Agents</h3><button class="btn" id="agent-create">New agent</button></div><div style="display:grid;gap:8px;margin-top:10px;">${renderAgents()}</div></section>`;
}

function renderAgents() {
  if (!agents.length) return '<div class="muted">No agents yet.</div>';
  return agents.map((agent) => `<div class="agent-product-card" style="opacity:${agent.is_active ? '1' : '.55'};"><div style="display:flex;justify-content:space-between;gap:8px;"><strong>${esc(agent.name)}</strong><span class="muted">${agent.is_default_assistant ? 'default' : (agent.is_active ? 'active' : 'archived')}</span></div><div class="muted" style="font-size:12px;">${esc(agent.model || 'no model')} ${agent.endpoint_url ? '· ' + esc(agent.endpoint_url) : ''}</div><div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;"><button class="btn btn-small" data-agent-edit="${esc(agent.id)}">Edit</button><button class="btn btn-small" data-agent-chat="${esc(agent.id)}">Chat</button><button class="btn btn-small" data-agent-clone="${esc(agent.id)}">Clone</button>${agent.is_default_assistant ? '' : `<button class="btn btn-small" data-agent-archive="${esc(agent.id)}">Archive</button>`}</div></div>`).join('');
}

function renderTeamsPanel() {
  return `<section class="panel" style="padding:12px;border:1px solid var(--border);border-radius:10px;"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px;"><h3 style="margin:0;">Teams</h3><button class="btn" id="team-create">New team</button></div><div style="display:grid;gap:8px;margin-top:10px;">${renderTeams()}</div></section>`;
}

function renderTeams() {
  if (!teams.length) return '<div class="muted">No teams yet.</div>';
  return teams.map((team) => `<div class="agent-product-card" style="opacity:${team.is_active ? '1' : '.55'};"><div style="display:flex;justify-content:space-between;gap:8px;"><strong>${esc(team.name)}</strong><span class="muted">${esc(team.topology || 'lead_routed')}</span></div><div class="muted" style="font-size:12px;">Leader: ${esc(team.leader?.name || 'not set')} · Members: ${(team.members || []).length} · ${esc(team.description || 'No description')}</div><div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;"><button class="btn btn-small" data-team-edit="${esc(team.id)}">Edit</button><button class="btn btn-small" data-team-chat="${esc(team.id)}">Chat</button><button class="btn btn-small" data-team-clone="${esc(team.id)}">Clone</button><button class="btn btn-small" data-team-delete="${esc(team.id)}">Archive</button></div></div>`).join('');
}

function renderRunsPanel() {
  if (!runs.length) return '<section class="panel" style="padding:12px;border:1px solid var(--border);border-radius:10px;"><h3>Runs</h3><div class="muted">No runs yet.</div></section>';
  return `<section class="panel" style="padding:12px;border:1px solid var(--border);border-radius:10px;"><h3 style="margin-top:0;">Runs</h3><div style="display:grid;gap:8px;">${runs.slice(0, 30).map((run) => `<div class="agent-product-card"><div><strong>${esc(run.target_type)} run</strong> <span class="muted">${esc(run.status)}</span></div><div class="muted" style="font-size:12px;">${esc(run.target_id || '')} · ${esc(run.created_at || '')}</div></div>`).join('')}</div></section>`;
}

function wireEvents(root) {
  root.querySelectorAll('[data-agent-tab]').forEach((btn) => btn.addEventListener('click', () => switchTab(root, btn.dataset.agentTab)));
  root.querySelector('#agent-team-start-chat')?.addEventListener('click', () => startSelectedChat(root.querySelector('#agent-team-chat-target')?.value || 'chat:'));
  root.querySelector('#agent-create')?.addEventListener('click', () => openAgentEditor());
  root.querySelector('#team-create')?.addEventListener('click', () => openTeamEditor());
  root.querySelectorAll('[data-agent-edit]').forEach((btn) => btn.addEventListener('click', () => openAgentEditor(btn.dataset.agentEdit)));
  root.querySelectorAll('[data-agent-clone]').forEach((btn) => btn.addEventListener('click', () => cloneAgent(btn.dataset.agentClone)));
  root.querySelectorAll('[data-agent-archive]').forEach((btn) => btn.addEventListener('click', () => archiveAgent(btn.dataset.agentArchive)));
  root.querySelectorAll('[data-agent-chat]').forEach((btn) => btn.addEventListener('click', () => startAgentChat(btn.dataset.agentChat)));
  root.querySelectorAll('[data-team-edit]').forEach((btn) => btn.addEventListener('click', () => openTeamEditor(btn.dataset.teamEdit)));
  root.querySelectorAll('[data-team-delete]').forEach((btn) => btn.addEventListener('click', () => deleteTeam(btn.dataset.teamDelete)));
  root.querySelectorAll('[data-team-clone]').forEach((btn) => btn.addEventListener('click', () => cloneTeam(btn.dataset.teamClone)));
  root.querySelectorAll('[data-team-chat]').forEach((btn) => btn.addEventListener('click', () => startTeamChat(btn.dataset.teamChat)));
}

function switchTab(root, tab) {
  root.querySelectorAll('[data-agent-tab]').forEach((b) => b.classList.toggle('active', b.dataset.agentTab === tab));
  root.querySelectorAll('.agent-tab-panel').forEach((p) => { p.style.display = p.id === `agent-tab-${tab}` ? '' : 'none'; });
}

function editorShell(title, html, onSave) {
  const body = ensureModal().querySelector('#agents-body');
  body.innerHTML = `<button class="btn btn-small" id="agents-back">← Back</button><h3>${esc(title)}</h3>${html}`;
  body.querySelector('#agents-back').addEventListener('click', () => render());
  body.querySelector('[data-save]')?.addEventListener('click', onSave);
}

function openAgentEditor(id = '') {
  const agent = agents.find((a) => a.id === id) || {};
  editorShell(id ? 'Edit agent' : 'New agent', `<div class="agent-editor-grid"><label>Name <input id="agent-name" value="${esc(agent.name)}" /></label><label>Model <input id="agent-model" value="${esc(agent.model)}" /></label><label>Endpoint URL <input id="agent-endpoint" value="${esc(agent.endpoint_url)}" /></label><label>Persona / system prompt <textarea id="agent-personality" rows="7">${esc(agent.personality)}</textarea></label><label>Prompt tuning prefix <textarea id="agent-prefix" rows="3"></textarea></label><label>Prompt tuning suffix <textarea id="agent-suffix" rows="3"></textarea></label><label>Enabled tools <input id="agent-tools" value="${esc((agent.enabled_tools || []).join(', '))}" /></label><button class="btn" data-save>Save agent</button></div>`, async () => {
    const prefix = document.getElementById('agent-prefix').value.trim();
    const suffix = document.getElementById('agent-suffix').value.trim();
    const personality = document.getElementById('agent-personality').value.trim();
    const payload = { name: document.getElementById('agent-name').value.trim(), model: document.getElementById('agent-model').value.trim(), endpoint_url: document.getElementById('agent-endpoint').value.trim(), personality: [prefix, personality, suffix].filter(Boolean).join('\n\n'), enabled_tools: document.getElementById('agent-tools').value.split(',').map((x) => x.trim()).filter(Boolean) };
    if (!payload.name) return uiModule.showToast('Agent name required');
    await jsonFetch(id ? `/api/agents/${id}` : '/api/agents', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
    await refresh();
  });
}

function renderMemberPickerRows(team) {
  const selected = new Map((team.members || []).map((m) => [m.agent_id, m.role || 'worker']));
  return agents.filter((a) => a.is_active && a.id !== team.leader_agent_id).map((agent) => `<div class="agent-team-member-row"><label><input type="checkbox" value="${esc(agent.id)}"${selected.has(agent.id) ? ' checked' : ''}> ${esc(agent.name)}</label><select data-role-for="${esc(agent.id)}">${roleOptions(selected.get(agent.id) || 'worker')}</select></div>`).join('') || '<div class="muted">Create agents first, then add members.</div>';
}

function openTeamEditor(id = '') {
  const team = teams.find((t) => t.id === id) || { topology: 'lead_routed', members: [], run_policy: { max_steps: 8 } };
  editorShell(id ? 'Edit team' : 'New team', `<div class="agent-editor-grid"><label>Name <input id="team-name" value="${esc(team.name)}" /></label><label>Description <input id="team-description" value="${esc(team.description)}" /></label><label>Leader <select id="team-leader">${agentOptions(team.leader_agent_id)}</select></label><label>Topology <select id="team-topology">${['lead_routed', 'sequential', 'parallel_review', 'debate'].map((t) => `<option value="${t}"${team.topology === t ? ' selected' : ''}>${t}</option>`).join('')}</select></label><label>Members</label><div class="agent-team-member-picker">${renderMemberPickerRows(team)}</div><label>Shared instructions <textarea id="team-instructions" rows="5">${esc(team.shared_instructions)}</textarea></label><label>Max steps <input id="team-max-steps" type="number" min="1" max="64" value="${esc(team.run_policy?.max_steps || 8)}" /></label><button class="btn" data-save>Save team</button></div>`, async () => {
    const members = Array.from(document.querySelectorAll('.agent-team-member-picker input[type="checkbox"]:checked')).map((box, index) => ({ agent_id: box.value, role: document.querySelector(`[data-role-for="${CSS.escape(box.value)}"]`)?.value || 'worker', sort_order: index + 1, enabled: true }));
    const payload = { name: document.getElementById('team-name').value.trim(), description: document.getElementById('team-description').value.trim(), leader_agent_id: document.getElementById('team-leader').value, members, topology: document.getElementById('team-topology').value, shared_instructions: document.getElementById('team-instructions').value, run_policy: { max_steps: Number(document.getElementById('team-max-steps').value || 8) } };
    if (!payload.name || !payload.leader_agent_id) return uiModule.showToast('Team name and leader required');
    await jsonFetch(id ? `/api/agent-teams/${id}` : '/api/agent-teams', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
    await refresh();
  });
}

async function cloneAgent(id) { await jsonFetch(`/api/agents/${id}/clone`, { method: 'POST' }); await refresh(); }
async function archiveAgent(id) { await jsonFetch(`/api/agents/${id}`, { method: 'DELETE' }); await refresh(); }
async function cloneTeam(id) { await jsonFetch(`/api/agent-teams/${id}/clone`, { method: 'POST' }); await refresh(); }
async function deleteTeam(id) { await jsonFetch(`/api/agent-teams/${id}`, { method: 'DELETE' }); await refresh(); }

function startSelectedChat(value) {
  const [kind, id] = String(value || 'chat:').split(':');
  if (kind === 'agent') return startAgentChat(id);
  if (kind === 'team') return startTeamChat(id);
  showChatTarget('', '');
  window.sessionModule?.setNextChatBinding?.({ targetType: 'chat', targetId: '' });
  window.sessionModule?.createDirectChat?.(window.sessionModule.getCurrentEndpointUrl?.() || '', window.sessionModule.getCurrentModel?.() || '', '');
  closeAgents();
}

function startAgentChat(id) {
  const agent = agents.find((a) => a.id === id);
  const sm = window.sessionModule;
  sm?.setNextChatBinding?.({ targetType: 'agent', targetId: id, targetName: agent?.name || id });
  showChatTarget('agent', agent?.name || id);
  sm?.createDirectChat?.(sm.getCurrentEndpointUrl?.() || '', sm.getCurrentModel?.() || '', '');
  closeAgents();
}

function startTeamChat(id) {
  const team = teams.find((t) => t.id === id);
  const sm = window.sessionModule;
  sm?.setNextChatBinding?.({ targetType: 'team', targetId: id, targetName: team?.name || id });
  showChatTarget('team', team?.name || id);
  sm?.createDirectChat?.(sm.getCurrentEndpointUrl?.() || '', sm.getCurrentModel?.() || '', '');
  closeAgents();
}

async function refresh() { await loadData(); render(); }

export async function openAgents() {
  ensureModal().style.display = 'flex';
  try { await refresh(); } catch (err) { ensureModal().querySelector('#agents-body').innerHTML = `<div class="error">${esc(err.message)}</div>`; }
}

window.agentTeamModule = { openAgents };

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('rail-agents')?.addEventListener('click', openAgents);
  document.getElementById('sidebar-agents-btn')?.addEventListener('click', openAgents);
  if (window.location.pathname === '/agents') openAgents();
});
