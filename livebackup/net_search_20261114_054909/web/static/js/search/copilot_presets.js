/**
 * copilot_presets.js
 * Global Preset loader, Soul/Personality avatar resolution, metadata chips, and preset popover UI.
 */
window.SearchCopilotPresets = (function () {
  'use strict';

  let currentPresetId = 'default';
  let activeGlobalPresetId = '';
  let presetsMap = {};

  function escapeHtml(str) {
    return window.SearchCopilotMarkdown ? window.SearchCopilotMarkdown.escapeHtml(str) : String(str || '');
  }

  // ── 1. Avatar Helpers ──────────────────────────────────────────────────────
  function getAssistantAvatarHtml(preset) {
    const p = preset || presetsMap[currentPresetId] || {
      name: 'Hecos AI',
      soul_name: 'Hecos AI',
      avatar_url: '/assets/Hecos_Logo_SQR_NBG_LogoOnly.png',
      avatar_type: 'image'
    };
    const url = escapeHtml(p.avatar_url || '/assets/Hecos_Logo_SQR_NBG_LogoOnly.png');
    const charName = escapeHtml(p.soul_name || p.name || 'Hecos AI');

    if (p.avatar_type === 'video') {
      return `<video src="${url}" autoplay loop muted playsinline class="copilot-avatar-video" title="${charName}"></video>`;
    }
    return `<img src="${url}" class="copilot-avatar-img" alt="${charName}" title="${charName}" onerror="this.src='/assets/Hecos_Logo_SQR_NBG_LogoOnly.png';">`;
  }

  function updatePersonalityUI() {
    const curPreset = presetsMap[currentPresetId];
    const charName = curPreset ? (curPreset.soul_name || curPreset.name || 'Hecos AI') : 'Hecos AI';
    const avatarHtml = getAssistantAvatarHtml(curPreset);

    // 1. Update initial greeting avatar & persona name
    const initialAvatar = document.getElementById('copilot-initial-avatar');
    if (initialAvatar) {
      initialAvatar.innerHTML = avatarHtml;
      initialAvatar.title = charName;
    }
    const initialNameEl = document.getElementById('copilot-initial-name');
    if (initialNameEl) {
      // Character name omitted from greeting per user preference
    }

    // 2. Update all assistant avatar elements currently rendered in chat
    const allAvatars = document.querySelectorAll('.copilot-chat-messages .copilot-assistant-avatar');
    allAvatars.forEach(el => {
      el.innerHTML = avatarHtml;
      el.title = charName;
    });

    // 3. Update the Card Title: "Ask <Character Name>"
    const titleTextEl = document.getElementById('copilot-chat-title-text');
    if (titleTextEl) {
      titleTextEl.textContent = `Ask ${charName}`;
    }

    // 4. Update the input placeholder (distinct from card title)
    const inputEl = document.getElementById('copilot-chat-input');
    if (inputEl) {
      inputEl.placeholder = 'Type a question or search query...';
    }

    // 5. Update Global Preset rich tooltip, summary chips, and popover
    renderPresetMetadata(curPreset);
  }

  function buildPresetTooltip(preset) {
    if (!preset) return 'Select Global Preset (AI Soul / Model / Voice Profile)';
    const m = preset.model || {};
    const inf = preset.inference || {};
    const v = preset.voice || {};
    const lines = [];
    lines.push(`🎭 Global Preset: ${preset.name || preset.id}${preset.is_active_global ? ' (System Default)' : ''}`);
    if (preset.description) lines.push(`📝 ${preset.description}`);
    lines.push(`🤖 Model: ${m.model_name || 'System Default'} (${m.backend_type || 'auto'})${m.is_default ? ' [Default]' : ''}`);
    lines.push(`👤 Soul: ${preset.soul_file || preset.soul_name || 'System Default'}`);
    const temp = inf.temperature ?? 'Default';
    const topP = inf.top_p ?? 'Default';
    const repPen = inf.repeat_penalty ?? 'Default';
    const ctx = inf.num_ctx ?? 'Default';
    lines.push(`⚙ Temp: ${temp} | Top P: ${topP} | Rep Pen: ${repPen} | Ctx: ${ctx}`);
    lines.push(`🔊 TTS: ${v.tts_engine || 'piper'} / ${v.tts_voice || 'Default'}${v.is_default ? ' [Default]' : ''}`);
    return lines.join('\n');
  }

  function renderPresetMetadata(preset) {
    const tooltip = buildPresetTooltip(preset);
    const cardEl = document.getElementById('copilot-preset-card');
    const selectEl = document.getElementById('copilot-preset-select');
    const infoBtn = document.getElementById('copilot-preset-info-btn');
    const summaryEl = document.getElementById('copilot-preset-summary');
    const popoverEl = document.getElementById('copilot-preset-popover');

    if (cardEl) cardEl.title = tooltip;
    if (selectEl) selectEl.title = tooltip;
    if (infoBtn) infoBtn.title = tooltip;

    if (!preset) {
      if (summaryEl) summaryEl.innerHTML = '';
      if (popoverEl) popoverEl.innerHTML = '';
      return;
    }

    const m = preset.model || {};
    const inf = preset.inference || {};
    const v = preset.voice || {};
    const modelShort = m.model_name || 'System Default';
    const voiceShort = `${v.tts_engine || 'piper'} · ${v.tts_voice || 'Default'}`;
    const tempVal = inf.temperature !== null && inf.temperature !== undefined ? inf.temperature : 'Def';

    if (summaryEl) {
      summaryEl.innerHTML = `
        <span class="copilot-preset-chip" title="Model: ${escapeHtml(modelShort)} (${escapeHtml(m.backend_type || 'auto')})">
          <i class="fas fa-microchip"></i> <strong>${escapeHtml(modelShort)}</strong>
        </span>
        <span class="copilot-preset-chip" title="TTS Voice: ${escapeHtml(voiceShort)}">
          <i class="fas fa-volume-up"></i> <strong>${escapeHtml(voiceShort)}</strong>
        </span>
        <span class="copilot-preset-chip" title="Temperature: ${escapeHtml(String(tempVal))}">
          <i class="fas fa-sliders"></i> T=${escapeHtml(String(tempVal))}
        </span>
      `;
    }

    if (popoverEl) {
      const infLine = `${inf.preset_name ? inf.preset_name + ' · ' : ''}Temp ${inf.temperature ?? 'Def'} | Top P ${inf.top_p ?? 'Def'} | Rep ${inf.repeat_penalty ?? 'Def'} | Ctx ${inf.num_ctx ?? 'Def'}`;
      popoverEl.innerHTML = `
        <div class="copilot-preset-popover-row"><span class="copilot-preset-popover-label">Preset</span><span>${escapeHtml(preset.name || preset.id)}${preset.is_active_global ? ' (System Default)' : ''}</span></div>
        ${preset.description ? `<div class="copilot-preset-popover-row"><span class="copilot-preset-popover-label">Summary</span><span>${escapeHtml(preset.description)}</span></div>` : ''}
        <div class="copilot-preset-popover-row"><span class="copilot-preset-popover-label">Model</span><span>${escapeHtml(modelShort)} (${escapeHtml(m.backend_type || 'auto')})</span></div>
        <div class="copilot-preset-popover-row"><span class="copilot-preset-popover-label">Soul</span><span>${escapeHtml(preset.soul_file || preset.soul_name || 'System Default')}</span></div>
        <div class="copilot-preset-popover-row"><span class="copilot-preset-popover-label">Inference</span><span>${escapeHtml(infLine)}</span></div>
        <div class="copilot-preset-popover-row"><span class="copilot-preset-popover-label">Voice TTS</span><span>${escapeHtml(v.tts_engine || 'piper')} / ${escapeHtml(v.tts_voice || 'Default')}</span></div>
      `;
    }
  }

  // ── 2. Presets Management ──────────────────────────────────────────────────
  async function loadPresets() {
    const select = document.getElementById('copilot-preset-select');
    if (!select) return;

    /** Populate the <select> with an array of preset objects. */
    function _populateSelect(presets, activeGlobalId = '') {
      presetsMap = {};
      presets.forEach(p => { presetsMap[p.id] = p; });
      if (activeGlobalId) activeGlobalPresetId = activeGlobalId;
      const saved = localStorage.getItem('hecos_search_copilot_preset');
      const targetId = (saved && presetsMap[saved])
        ? saved
        : ((activeGlobalId && presetsMap[activeGlobalId]) ? activeGlobalId : (presets[0] ? presets[0].id : 'default'));
      select.innerHTML = presets.map(p => `
        <option value="${escapeHtml(p.id)}" title="${escapeHtml(buildPresetTooltip(p))}" ${p.id === targetId ? 'selected' : ''}>
          ${escapeHtml(p.icon || '\u{1F9E0}')} ${escapeHtml(p.name)}
        </option>
      `).join('');
      currentPresetId = select.value || targetId;
      updatePersonalityUI();
    }

    /** Minimal fallback shown when the API is unreachable or returns an error. */
    const _fallbackPresets = [
      { id: 'default', name: 'Hecos AI', soul_name: 'Hecos AI', icon: '\u{1F9E0}',
        avatar_url: '/assets/Hecos_Logo_NBG.png', avatar_type: 'image', description: 'Standard Assistant',
        model: { model_name: 'System Default', backend_type: 'auto', is_default: true },
        inference: {},
        voice: { tts_engine: 'piper', tts_voice: 'Default', is_default: true } }
    ];

    try {
      const res = await fetch('/api/hsearch/copilot/presets', { credentials: 'same-origin' });
      if (!res.ok) {
        // Non-2xx (e.g. 401 not authenticated) — use fallback silently
        console.warn(`[HecosAI] Presets API HTTP ${res.status}; using fallback preset.`);
        _populateSelect(_fallbackPresets);
      } else {
        const data = await res.json();
        if (data.ok && Array.isArray(data.presets) && data.presets.length > 0) {
          _populateSelect(data.presets, data.active_global_id || '');
        } else {
          console.warn('[HecosAI] Presets list empty or malformed; using fallback preset.');
          _populateSelect(_fallbackPresets);
        }
      }
    } catch (e) {
      console.warn('[HecosAI] Could not load presets:', e);
      _populateSelect(_fallbackPresets);
    }
    select.addEventListener('change', () => {
      currentPresetId = select.value;
      localStorage.setItem('hecos_search_copilot_preset', currentPresetId);
      const curPreset = presetsMap[currentPresetId];
      const charName = curPreset ? (curPreset.soul_name || curPreset.name || 'Hecos AI') : 'Hecos AI';
      updatePersonalityUI();
      window.SearchCopilot?.appendSystemNotice?.(`Active Preset: <strong>${escapeHtml(charName)}</strong>`);
    });
  }

  return {
    loadPresets,
    updatePersonalityUI,
    buildPresetTooltip,
    renderPresetMetadata,
    getAssistantAvatarHtml,
    getCurrentPresetId() { return currentPresetId; },
    getActiveGlobalPresetId() { return activeGlobalPresetId; },
    getCurrentPreset() { return presetsMap[currentPresetId] || null; },
    getCharacterName() {
      const p = presetsMap[currentPresetId];
      return p ? (p.soul_name || p.name || 'Hecos AI') : 'Hecos AI';
    }
  };
})();
