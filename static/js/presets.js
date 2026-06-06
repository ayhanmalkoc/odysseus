// Agent/Team refactor: legacy Prompt/Inject/Persona/Group UI removed.
// This module remains as a compatibility shim for chat/compare imports.

export const PROMPT_TEMPLATES = [];

export function loadStoredArray(key) {
  try { return JSON.parse(localStorage.getItem(key) || '[]'); } catch { return []; }
}

export function loadStoredObject(key) {
  try { return JSON.parse(localStorage.getItem(key) || '{}'); } catch { return {}; }
}

export function init() {}
export async function loadPresets() { return {}; }
export function setActivePreset() { return false; }
export function openCustomPresetModal() {
  window.agentTeamModule?.openAgents?.();
}
export async function saveCustomPreset() { return false; }
export function getSelectedPreset() { return null; }
export function getPreset() { return null; }
export function getAllPresets() { return []; }
export function getCharacterName() { return ''; }
export function getInject() { return { prefix: '', suffix: '' }; }
export function deactivateCharacter() { return false; }
export function onSessionSwitch() { return false; }
export function isPersistentChat() { return false; }
export function removePersistentChat() { return false; }

const presetsModule = {
  PROMPT_TEMPLATES,
  loadStoredArray,
  loadStoredObject,
  init,
  loadPresets,
  setActivePreset,
  openCustomPresetModal,
  saveCustomPreset,
  getSelectedPreset,
  getPreset,
  getAllPresets,
  getCharacterName,
  getInject,
  deactivateCharacter,
  onSessionSwitch,
  isPersistentChat,
  removePersistentChat,
};

window.presetsModule = presetsModule;
export default presetsModule;
