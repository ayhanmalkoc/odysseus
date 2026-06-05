import uiModule from './ui.js';

const API_BASE = window.API_BASE || '';
let modalEl = null;
let agents = [];
let groups = [];

function esc(value) {
  return String(value || '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

async function jsonFetch(url, options = {}) {
  const res = await fetch(`${API_BASE}${url}`, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
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
    <div class="modal-content" style="max-width:980px;width:96%;max-height:88vh;">
      <div class="modal-header">
        <h4>Agents & Teams</h4>
        <button class="close-btn" id="agents-close">✖</button>
      </div>
      <div class="modal-body" id="agents-body"></div>
    </div>`;
  document.body.appendChild(el);
  el.querySelector('#agents-close').addEventListener('click', closeAgents);
  el.addEventListener('click', (event) => { if (event.target === el) closeAgents(); });
  modalEl = el;
  return el;
}

function closeAgents() {
  if (modalEl) modalEl.style.display = 'none';
}

async function loadData() {
  const [agentData, groupData] = await Promise.all([
    jsonFetch('/api/agents?include_inactive=true'),
    jsonFetch('/api/presets/groups'),
  ]);
  agents = agentData.agents || [];
  groups = groupData.groups || [];
}

function agentOptions(selected = '') {
  return agents.filter((a) => a.is_active).map((a) => (
    `<option value="${esc(a.id)}"${a.id === selected ? ' selected' : ''}>${esc(a.name)}</option>`
  )).join('');
}

function render() {
  const body = ensureModal().querySelector('#agents-body');
  body.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start;">
      <section class="panel" style="padding:12px;border:1px solid var(--border);border-radius:10px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
          <h3 style="margin:0;">Agents</h3>
          <button class="btn" id="agent-create">New agent</button>
        </div>
        <div id="agent-list" style="display:grid;gap:8px;margin-top:10px;">${renderAgents()}</div>
      </section>
      <section class="panel" style="padding:12px;border:1px solid var(--border);border-radius:10px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
          <h3 style="margin:0;">Teams</h3>
          <button class="btn" id="team-create">New team</button>
        </div>
        <div id="team-list" style="display:grid;gap:8px;margin-top:10px;">${renderTeams()}</div>
      </section>
    </div>`;
  wireEvents(body);
}

function renderAgents() {
  if (!agents.length) return '<div class="muted">No agents yet.</div>';
  return agents.map((agent) => `
    <div style="border:1px solid var(--border);border-radius:8px;padding:10px;opacity:${agent.is_active ? '1' : '.55'};">
      <div style="display:flex;justify-content:space-between;gap:8px;">
        <strong>${esc(agent.name)}</strong>
        <span class="muted">${agent.is_default_assistant ? 'default assistant' : (agent.is_active ? 'active' : 'archived')}</span>
      </div>
      <div class="muted" style="font-size:12px;">${esc(agent.model || 'no model')} ${agent.endpoint_url ? '· ' + esc(agent.endpoint_url) : ''}</div>
      <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;">
        <button class="btn btn-small" data-agent-edit="${esc(agent.id)}">Edit</button>
        <button class="btn btn-small" data-agent-clone="${esc(agent.id)}">Clone</button>
        <button class="btn btn-small" data-agent-chat="${esc(agent.id)}">Chat</button>
        ${agent.is_default_assistant ? '' : `<button class="btn btn-small" data-agent-archive="${esc(agent.id)}">Archive</button>`}
      </div>
    </div>`).join('');
}

function renderTeams() {
  if (!groups.length) return '<div class="muted">No teams yet.</div>';
  return groups.map((group) => {
    const lead = agents.find((a) => a.id === group.lead_crew_member_id);
    return `
      <div style="border:1px solid var(--border);border-radius:8px;padding:10px;">
        <div style="display:flex;justify-content:space-between;gap:8px;">
          <strong>${esc(group.name)}</strong>
          <span class="muted">${esc(group.topology || 'lead_routed')}</span>
        </div>
        <div class="muted" style="font-size:12px;">Lead: ${esc(lead ? lead.name : group.lead_crew_member_id)} · Members: ${(group.members || []).length}</div>
        <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;">
          <button class="btn btn-small" data-team-edit="${esc(group.id)}">Edit</button>
          <button class="btn btn-small" data-team-chat="${esc(group.id)}">Team chat</button>
          <button class="btn btn-small" data-team-delete="${esc(group.id)}">Delete</button>
        </div>
      </div>`;
  }).join('');
}

function wireEvents(root) {
  root.querySelector('#agent-create')?.addEventListener('click', () => openAgentEditor());
  root.querySelector('#team-create')?.addEventListener('click', () => openTeamEditor());
  root.querySelectorAll('[data-agent-edit]').forEach((btn) => btn.addEventListener('click', () => openAgentEditor(btn.dataset.agentEdit)));
  root.querySelectorAll('[data-agent-clone]').forEach((btn) => btn.addEventListener('click', () => cloneAgent(btn.dataset.agentClone)));
  root.querySelectorAll('[data-agent-archive]').forEach((btn) => btn.addEventListener('click', () => archiveAgent(btn.dataset.agentArchive)));
  root.querySelectorAll('[data-agent-chat]').forEach((btn) => btn.addEventListener('click', () => startAgentChat(btn.dataset.agentChat)));
  root.querySelectorAll('[data-team-edit]').forEach((btn) => btn.addEventListener('click', () => openTeamEditor(btn.dataset.teamEdit)));
  root.querySelectorAll('[data-team-delete]').forEach((btn) => btn.addEventListener('click', () => deleteTeam(btn.dataset.teamDelete)));
  root.querySelectorAll('[data-team-chat]').forEach((btn) => btn.addEventListener('click', () => startTeamChat(btn.dataset.teamChat)));
}

function renderMemberPickerRows(group) {
  const selected = new Map((group.members || []).map((m) => [m.crew_member_id, m.role || 'worker']));
  return agents.filter((a) => a.is_active && a.id !== group.lead_crew_member_id).map((agent) => {
    const checked = selected.has(agent.id);
    const role = selected.get(agent.id) || 'worker';
    return `<label class="agent-team-member-row">
      <input type="checkbox" value="${esc(agent.id)}" ${checked ? 'checked' : ''} />
      <span>${esc(agent.name)}</span>
      <select data-role-for="${esc(agent.id)}">
        ${['worker', 'researcher', 'reviewer', 'writer', 'critic'].map((r) => `<option value="${r}"${role === r ? ' selected' : ''}>${r}</option>`).join('')}
      </select>
    </label>`;
  }).join('') || '<div class="muted">Create agents first, then add them as members.</div>';
}

function editorShell(title, html, onSave) {
  const body = ensureModal().querySelector('#agents-body');
  body.innerHTML = `<button class="btn btn-small" id="agents-back">← Back</button><h3>${esc(title)}</h3>${html}`;
  body.querySelector('#agents-back').addEventListener('click', () => render());
  body.querySelector('[data-save]')?.addEventListener('click', onSave);
}

function openAgentEditor(id = '') {
  const agent = agents.find((a) => a.id === id) || {};
  editorShell(id ? 'Edit agent' : 'New agent', `
    <div style="display:grid;gap:10px;max-width:720px;">
      <label>Name <input id="agent-name" value="${esc(agent.name)}" /></label>
      <label>Model <input id="agent-model" value="${esc(agent.model)}" /></label>
      <label>Endpoint URL <input id="agent-endpoint" value="${esc(agent.endpoint_url)}" /></label>
      <label>Personality / system prompt <textarea id="agent-personality" rows="7">${esc(agent.personality)}</textarea></label>
      <label>Enabled tools <input id="agent-tools" value="${esc((agent.enabled_tools || []).join(', '))}" placeholder="web_search, read_file" /></label>
      <button class="btn" data-save>Save agent</button>
    </div>`, async () => {
      const payload = {
        name: document.getElementById('agent-name').value.trim(),
        model: document.getElementById('agent-model').value.trim(),
        endpoint_url: document.getElementById('agent-endpoint').value.trim(),
        personality: document.getElementById('agent-personality').value,
        enabled_tools: document.getElementById('agent-tools').value.split(',').map((x) => x.trim()).filter(Boolean),
      };
      if (!payload.name) return uiModule.showToast('Agent name required');
      await jsonFetch(id ? `/api/agents/${id}` : '/api/agents', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
      await refresh();
    });
}

function openTeamEditor(id = '') {
  const group = groups.find((g) => g.id === id) || { topology: 'lead_routed', members: [], run_config: { max_steps: 8, parallel: false, show_activity: true } };
  editorShell(id ? 'Edit team' : 'New team', `
    <div style="display:grid;gap:10px;max-width:760px;">
      <label>Name <input id="team-name" value="${esc(group.name)}" /></label>
      <label>Description <input id="team-description" value="${esc(group.description)}" /></label>
      <label>Lead <select id="team-lead">${agentOptions(group.lead_crew_member_id)}</select></label>
      <label>Topology <select id="team-topology">
        ${['lead_routed', 'sequential_pipeline', 'broadcast_review'].map((t) => `<option value="${t}"${group.topology === t ? ' selected' : ''}>${t}</option>`).join('')}
      </select></label>
      <label>Members</label>
      <div class="agent-team-member-picker">${renderMemberPickerRows(group)}</div>
      <label>Shared instructions <textarea id="team-instructions" rows="5">${esc(group.shared_instructions)}</textarea></label>
      <label>Max steps <input id="team-max-steps" type="number" min="1" max="64" value="${esc(group.run_config?.max_steps || 8)}" /></label>
      <button class="btn" data-save>Save team</button>
    </div>`, async () => {
      const members = Array.from(document.querySelectorAll('.agent-team-member-picker input[type="checkbox"]:checked')).map((box, index) => {
        const roleSel = document.querySelector(`[data-role-for="${CSS.escape(box.value)}"]`);
        return { crew_member_id: box.value, role: roleSel?.value || 'worker', order: index + 1, enabled: true };
      });
      const payload = {
        id: id || '',
        name: document.getElementById('team-name').value.trim(),
        description: document.getElementById('team-description').value.trim(),
        lead_crew_member_id: document.getElementById('team-lead').value,
        members,
        topology: document.getElementById('team-topology').value,
        shared_instructions: document.getElementById('team-instructions').value,
        run_config: { max_steps: Number(document.getElementById('team-max-steps').value || 8), parallel: false, show_activity: true },
      };
      if (!payload.name || !payload.lead_crew_member_id) return uiModule.showToast('Team name and lead required');
      await jsonFetch(id ? `/api/presets/groups/${id}` : '/api/presets/groups', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
      await refresh();
    });
}

async function cloneAgent(id) { await jsonFetch(`/api/agents/${id}/clone`, { method: 'POST' }); await refresh(); }
async function archiveAgent(id) { await jsonFetch(`/api/agents/${id}`, { method: 'DELETE' }); await refresh(); }
async function deleteTeam(id) { await jsonFetch(`/api/presets/groups/${id}`, { method: 'DELETE' }); await refresh(); }

function startAgentChat(id) {
  const sm = window.sessionModule;
  sm?.setNextChatBinding?.({ crewMemberId: id });
  sm?.createDirectChat?.(sm.getCurrentEndpointUrl?.() || '', sm.getCurrentModel?.() || '', '');
  closeAgents();
}

function startTeamChat(id) {
  const sm = window.sessionModule;
  sm?.setNextChatBinding?.({ groupPresetId: id });
  sm?.createDirectChat?.(sm.getCurrentEndpointUrl?.() || '', sm.getCurrentModel?.() || '', '');
  closeAgents();
}

async function refresh() {
  await loadData();
  render();
}

export async function openAgents() {
  ensureModal().style.display = 'flex';
  try {
    await refresh();
  } catch (err) {
    ensureModal().querySelector('#agents-body').innerHTML = `<div class="error">${esc(err.message)}</div>`;
  }
}

window.agentTeamModule = { openAgents };

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('rail-agents')?.addEventListener('click', openAgents);
  document.getElementById('sidebar-agents-btn')?.addEventListener('click', openAgents);
  if (window.location.pathname === '/agents') openAgents();
});
