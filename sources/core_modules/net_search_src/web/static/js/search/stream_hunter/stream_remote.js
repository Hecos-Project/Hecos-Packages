/**
 * stream_remote.js
 * Modular TV Remote Controller for Hecos NetSearch Stream Hunter.
 * Manages:
 *  - Left Sidebar Docked / Floating Draggable / Multi-Monitor Pop-out Window modes
 *  - Numbered channel lineup (CH 01..NN), keypad digit buffer, CH+/CH-/LAST zapping
 *  - Physical Keyboard TV shortcuts (0-9, Arrows, PageUp/Down, Space, M, B, V, S, Enter)
 *  - On-Screen Display (OSD) HUD & tuned card highlight + smooth scroll
 *  - BroadcastChannel + Backend /api/hsearch/streams/remote/* synchronization (LLM & Pop-out)
 *  - Net Search Global Preset LCD Badge + Central Hub toggle awareness
 */
(function () {
  const IS_POPOUT = Boolean(window.SH_REMOTE_POPOUT_MODE);
  const BC_NAME = 'hecos_stream_remote_channel';
  const FLOAT_POS_KEY = 'hecos_sh_remote_float_pos';
  const FLOAT_ACTIVE_KEY = 'hecos_sh_remote_is_floating';
  const COLLAPSE_KEY = 'hecos_sh_remote_collapsed';

  let bc = null;
  try {
    if (typeof BroadcastChannel !== 'undefined') {
      bc = new BroadcastChannel(BC_NAME);
    }
  } catch (_e) {}

  const state = {
    visible: IS_POPOUT,
    isFloating: false,
    isCollapsed: false,
    queue: [],
    activeIndex: -1,
    lastIndex: -1,
    volume: 85,
    muted: false,
    paused: false,
    target: 'app', // app | vlc | libvlc
    proxyEnabled: false,
    category: 'all',
    query: '',
    lastSeq: 0,
    presetSettings: {
      use_global_preset: true,
      preset_voice_announcer: true,
      preset_remote_sync: true,
    },
  };

  let digitBuffer = '';
  let digitTimer = null;
  let osdTimer = null;
  let popoutWin = null;
  let pollTimer = null;
  let syncDebounceTimer = null;

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatCh(num) {
    const n = parseInt(num, 10);
    if (!n || n < 1) return '--';
    return n < 10 ? '0' + n : String(n);
  }

  // ── 1. TV OSD HUD ───────────────────────────────────────────────────────
  function ensureOsdDom() {
    if (IS_POPOUT) return null;
    let osd = document.getElementById('sh-tv-osd');
    if (osd) return osd;
    osd = document.createElement('div');
    osd.id = 'sh-tv-osd';
    osd.className = 'sh-tv-osd';
    osd.innerHTML = `
      <div class="sh-tv-osd-ch" id="sh-tv-osd-ch">CH --</div>
      <div class="sh-tv-osd-sub" id="sh-tv-osd-sub">Standby</div>
    `;
    document.body.appendChild(osd);
    return osd;
  }

  function showOsd(mainText, subText = '', durationMs = 2600) {
    if (IS_POPOUT) return;
    const osd = ensureOsdDom();
    if (!osd) return;
    const chEl = document.getElementById('sh-tv-osd-ch');
    const subEl = document.getElementById('sh-tv-osd-sub');
    if (chEl) chEl.textContent = mainText;
    if (subEl) subEl.textContent = subText;
    osd.classList.add('is-visible');
    if (osdTimer) clearTimeout(osdTimer);
    osdTimer = setTimeout(() => {
      osd.classList.remove('is-visible');
    }, durationMs);
  }

  // ── 2. Global Preset LCD Badge ──────────────────────────────────────────
  function refreshPresetBadge() {
    const row = document.getElementById('sh-lcd-preset-row');
    const txt = document.getElementById('sh-lcd-preset-text');
    if (!row || !txt) return;

    const ps = state.presetSettings || {};
    if (ps.preset_remote_sync === false) {
      row.style.display = 'none';
      return;
    }
    row.style.display = 'flex';

    if (ps.use_global_preset === false) {
      row.classList.add('is-neutral');
      txt.textContent = 'Preset: OFF (Neutral TV Mode)';
      return;
    }

    row.classList.remove('is-neutral');
    if (window.SearchCopilotPresets && typeof window.SearchCopilotPresets.getCurrentPresetSummary === 'function') {
      const sum = window.SearchCopilotPresets.getCurrentPresetSummary();
      const shortModel = (sum.model_name || 'Default').split('/').pop().slice(0, 16);
      const shortVoice = (sum.tts_voice || 'Default').split(/[\\/]/).pop().slice(0, 14);
      txt.textContent = `${sum.icon || '🧠'} ${sum.soul_name} · ${shortModel} · ${shortVoice}`;
      row.title = `Global Preset ON — Soul: ${sum.soul_name} | Model: ${sum.model_name} | Voice: ${sum.tts_voice}`;
    } else {
      txt.textContent = 'Global Preset: Synced';
    }
  }

  async function fetchPresetSettings() {
    try {
      const res = await fetch('/api/hsearch/streams/preset_settings', { credentials: 'same-origin' });
      if (res.ok) {
        const data = await res.json();
        if (data && data.preset_settings) {
          state.presetSettings = data.preset_settings;
          refreshPresetBadge();
        }
      }
    } catch (_e) {}
  }

  // ── 3. Render Remote UI & Cards Highlight ───────────────────────────────
  function updateRemoteUI() {
    const wrap = document.getElementById('sh-remote-wrap');
    if (wrap && !IS_POPOUT) {
      wrap.style.display = state.visible ? 'block' : 'none';
      wrap.classList.toggle('is-floating', Boolean(state.isFloating));
    }

    const shell = document.getElementById('sh-remote-shell');
    const collapseBtn = document.getElementById('sh-rem-collapse-btn');
    if (shell) {
      shell.classList.toggle('is-collapsed', Boolean(state.isCollapsed && !IS_POPOUT));
    }
    if (collapseBtn) {
      collapseBtn.innerHTML = state.isCollapsed ? '<i class="fas fa-chevron-down"></i>' : '<i class="fas fa-chevron-up"></i>';
    }

    const floatBtn = document.getElementById('sh-rem-float-btn');
    if (floatBtn) {
      floatBtn.classList.toggle('is-active', Boolean(state.isFloating));
      if (IS_POPOUT) floatBtn.style.display = 'none';
    }
    const popBtn = document.getElementById('sh-rem-popout-btn');
    if (popBtn && IS_POPOUT) popBtn.style.display = 'none';
    if (collapseBtn && IS_POPOUT) collapseBtn.style.display = 'none';

    const active = (state.activeIndex >= 0 && state.activeIndex < state.queue.length)
      ? state.queue[state.activeIndex]
      : null;

    const statusPill = document.getElementById('sh-remote-status-pill');
    const chPill = document.getElementById('sh-lcd-ch-pill');
    const digitsEl = document.getElementById('sh-lcd-digits');
    const titleEl = document.getElementById('sh-lcd-title');
    const targetPill = document.getElementById('sh-lcd-target-pill');
    const targetTxt = document.getElementById('sh-rem-target-txt');
    const volLabel = document.getElementById('sh-lcd-vol-label');
    const queueLabel = document.getElementById('sh-lcd-queue-label');
    const proxyLabel = document.getElementById('sh-lcd-proxy-label');
    const volSlider = document.getElementById('sh-rem-vol-slider');
    const muteBtn = document.getElementById('sh-rem-mute-btn');

    if (statusPill) {
      statusPill.textContent = active ? (state.paused ? 'PAUSED' : 'ON AIR') : 'STANDBY';
      statusPill.className = 'sh-pill ' + (active ? 'sh-pill-live' : 'sh-pill-ready');
    }
    if (chPill) {
      chPill.textContent = active ? `CH ${formatCh(state.activeIndex + 1)}` : 'CH --';
    }
    if (digitsEl) {
      digitsEl.textContent = digitBuffer ? `CH ${digitBuffer}_` : '';
    }
    if (titleEl) {
      titleEl.textContent = active ? (active.title || active.stream_url) : 'Select a channel or press CH+';
    }
    if (targetPill) targetPill.textContent = (state.target || 'app').toUpperCase();
    if (targetTxt) targetTxt.textContent = (state.target || 'app').toUpperCase();
    if (volLabel) volLabel.textContent = state.muted ? 'MUTED' : `VOL ${state.volume}%`;
    if (queueLabel) queueLabel.textContent = `${state.queue.length} CH`;
    if (proxyLabel) proxyLabel.style.display = state.proxyEnabled ? 'inline' : 'none';
    if (volSlider && document.activeElement !== volSlider) {
      volSlider.value = String(state.volume);
    }
    if (muteBtn) {
      muteBtn.classList.toggle('is-active', Boolean(state.muted));
    }

    document.querySelectorAll('[data-sh-action="toggle_proxy"]').forEach(btn => {
      btn.classList.toggle('is-active', Boolean(state.proxyEnabled));
    });
    document.querySelectorAll('[data-sh-action="category"]').forEach(btn => {
      btn.classList.toggle('is-active', (btn.dataset.shCat || 'all') === state.category);
    });

    refreshPresetBadge();
    if (!IS_POPOUT) {
      highlightActiveCard();
    } else {
      renderPopoutLineup();
    }
  }

  function highlightActiveCard() {
    const active = (state.activeIndex >= 0 && state.activeIndex < state.queue.length)
      ? state.queue[state.activeIndex]
      : null;
    const activeUrl = active ? (active.stream_url || active.url || '') : '';
    document.querySelectorAll('.sh-card').forEach(card => {
      const match = Boolean(activeUrl && card.dataset.streamUrl === activeUrl);
      card.classList.toggle('is-tuned', match);
    });
  }

  function scrollCardIntoView(idx) {
    if (IS_POPOUT || idx < 0) return;
    const cards = document.querySelectorAll('.sh-card');
    const card = cards[idx];
    if (card && typeof card.scrollIntoView === 'function') {
      card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function renderPopoutLineup() {
    const listEl = document.getElementById('sh-popout-lineup-list');
    const cntEl = document.getElementById('sh-popout-qcount');
    if (cntEl) cntEl.textContent = `${state.queue.length} CH`;
    if (!listEl) return;

    if (!state.queue.length) {
      listEl.innerHTML = '<div class="sh-popout-empty">No channels loaded yet. Open Live Streams in Net Search or ask Hecos AI.</div>';
      return;
    }
    listEl.innerHTML = state.queue.map((st, idx) => `
      <button type="button" class="sh-popout-ch-row ${idx === state.activeIndex ? 'is-active' : ''}" data-ch-num="${idx + 1}">
        <span class="sh-ch-badge">${formatCh(idx + 1)}</span>
        <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(st.title || st.stream_url)}</span>
        <span style="font-size:10px; opacity:0.75;">${escapeHtml((st.protocol || 'HLS').toUpperCase())}</span>
      </button>
    `).join('');

    listEl.querySelectorAll('.sh-popout-ch-row').forEach(row => {
      row.addEventListener('click', () => {
        const ch = parseInt(row.dataset.chNum, 10);
        if (ch >= 1) executeAction('play_channel', { channel: ch }, 'popout');
      });
    });
  }

  // ── 4. Cross-Window Sync & Backend Command Bus ──────────────────────────
  function broadcastLocalState() {
    if (!bc || IS_POPOUT) return;
    try {
      bc.postMessage({
        type: 'state_sync',
        payload: {
          queue: state.queue,
          activeIndex: state.activeIndex,
          lastIndex: state.lastIndex,
          volume: state.volume,
          muted: state.muted,
          paused: state.paused,
          target: state.target,
          proxyEnabled: state.proxyEnabled,
          category: state.category,
          query: state.query,
          presetSettings: state.presetSettings,
        },
      });
    } catch (_e) {}
  }

  function scheduleBackendSync() {
    if (IS_POPOUT) return;
    broadcastLocalState();
    if (syncDebounceTimer) clearTimeout(syncDebounceTimer);
    syncDebounceTimer = setTimeout(syncStateToBackend, 180);
  }

  async function syncStateToBackend() {
    if (IS_POPOUT) return;
    try {
      await fetch('/api/hsearch/streams/remote/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          queue: state.queue.slice(0, 150),
          active_index: state.activeIndex,
          volume: state.volume,
          muted: state.muted,
          paused: state.paused,
          target: state.target,
          proxy_enabled: state.proxyEnabled,
          category: state.category,
          query: state.query,
        }),
      });
    } catch (_e) {}
  }

  // ── 5. Playback & Action Execution ──────────────────────────────────────
  function tuneChannelIndex(idx, announceOsd = true) {
    if (!state.queue.length || idx < 0 || idx >= state.queue.length) return false;
    if (state.activeIndex >= 0 && state.activeIndex !== idx) {
      state.lastIndex = state.activeIndex;
    }
    state.activeIndex = idx;
    state.paused = false;
    const st = state.queue[idx];

    if (announceOsd) {
      showOsd(`CH ${formatCh(idx + 1)}`, `${st.title || 'Live Stream'} [${(state.target || 'app').toUpperCase()}]`);
    }

    if (!IS_POPOUT) {
      if (state.target === 'vlc') {
        if (window.StreamHunterUI) {
          window.StreamHunterUI.openInVlc(st.stream_url || st.url, st.title || '');
        }
      } else if (state.target === 'libvlc') {
        fetch('/api/hsearch/streams/vlc/libvlc', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({
            action: 'play',
            url: st.stream_url || st.url,
            title: st.title || '',
            volume: state.muted ? 0 : state.volume,
          }),
        }).catch(() => {});
      } else if (window.StreamPlayerDock) {
        window.StreamPlayerDock.playStream(st, Boolean(state.proxyEnabled));
        window.StreamPlayerDock.setVolume(state.volume);
        window.StreamPlayerDock.toggleMute(Boolean(state.muted));
      }
      scrollCardIntoView(idx);
    }

    updateRemoteUI();
    scheduleBackendSync();
    return true;
  }

  function applyCommandLocally(cmd, payload = {}) {
    const c = (cmd || '').toLowerCase();
    const len = state.queue.length;

    if (c === 'play_channel' || c === 'channel' || c === 'tune') {
      const ch = parseInt(payload.channel, 10);
      if (ch >= 1 && ch <= len) {
        tuneChannelIndex(ch - 1, true);
      } else if (payload.stream && (payload.stream.stream_url || payload.stream.url)) {
        state.queue.unshift(payload.stream);
        tuneChannelIndex(0, true);
      }
    } else if (c === 'ch_up' || c === 'next') {
      if (len > 0) {
        const nxt = state.activeIndex < 0 ? 0 : (state.activeIndex + 1) % len;
        tuneChannelIndex(nxt, true);
      }
    } else if (c === 'ch_down' || c === 'prev') {
      if (len > 0) {
        const prv = state.activeIndex <= 0 ? len - 1 : state.activeIndex - 1;
        tuneChannelIndex(prv, true);
      }
    } else if (c === 'last') {
      if (state.lastIndex >= 0 && state.lastIndex < len) {
        tuneChannelIndex(state.lastIndex, true);
      }
    } else if (c === 'ok') {
      if (digitBuffer) {
        commitDigitBuffer();
      } else if (state.activeIndex >= 0) {
        tuneChannelIndex(state.activeIndex, true);
      } else if (len > 0) {
        tuneChannelIndex(0, true);
      }
    } else if (c === 'stop') {
      state.activeIndex = -1;
      state.paused = false;
      if (!IS_POPOUT && window.StreamPlayerDock) {
        window.StreamPlayerDock.stopAndClose();
      }
      showOsd('STOP', 'Playback stopped');
      updateRemoteUI();
      scheduleBackendSync();
    } else if (c === 'pause' || c === 'play_pause') {
      if (!IS_POPOUT && window.StreamPlayerDock) {
        state.paused = window.StreamPlayerDock.pauseToggle();
      } else {
        state.paused = !state.paused;
      }
      showOsd(state.paused ? 'PAUSED' : 'PLAY', activeTitle());
      updateRemoteUI();
      scheduleBackendSync();
    } else if (c === 'vol_up' || c === 'vol_down' || c === 'set_volume') {
      const step = parseInt(payload.step || 10, 10);
      const nextVol = c === 'set_volume'
        ? parseInt(payload.volume, 10)
        : (c === 'vol_up' ? state.volume + step : state.volume - step);
      state.volume = Math.max(0, Math.min(100, isNaN(nextVol) ? state.volume : nextVol));
      if (state.volume > 0) state.muted = false;
      if (!IS_POPOUT && window.StreamPlayerDock) {
        window.StreamPlayerDock.setVolume(state.volume);
      }
      showOsd(`VOL ${state.volume}%`, activeTitle(), 1600);
      updateRemoteUI();
      scheduleBackendSync();
    } else if (c === 'mute') {
      state.muted = typeof payload.muted === 'boolean' ? payload.muted : !state.muted;
      if (!IS_POPOUT && window.StreamPlayerDock) {
        window.StreamPlayerDock.toggleMute(state.muted);
      }
      showOsd(state.muted ? 'MUTED' : `VOL ${state.volume}%`, activeTitle(), 1600);
      updateRemoteUI();
      scheduleBackendSync();
    } else if (c === 'target') {
      const order = ['app', 'vlc', 'libvlc'];
      const nxtTgt = (payload.target && order.includes(payload.target))
        ? payload.target
        : order[(order.indexOf(state.target) + 1) % order.length];
      state.target = nxtTgt;
      showOsd(`TARGET: ${nxtTgt.toUpperCase()}`, activeTitle(), 1800);
      updateRemoteUI();
      scheduleBackendSync();
    } else if (c === 'toggle_proxy') {
      state.proxyEnabled = !state.proxyEnabled;
      if (state.activeIndex >= 0 && state.target === 'app') {
        tuneChannelIndex(state.activeIndex, false);
      }
      showOsd(`PROXY ${state.proxyEnabled ? 'ON' : 'OFF'}`, activeTitle(), 1600);
      updateRemoteUI();
      scheduleBackendSync();
    } else if (c === 'open_vlc') {
      const targetIdx = (payload.channel && parseInt(payload.channel, 10) >= 1)
        ? parseInt(payload.channel, 10) - 1
        : state.activeIndex;
      const st = (targetIdx >= 0 && targetIdx < len) ? state.queue[targetIdx] : (payload.stream || null);
      if (st && !IS_POPOUT && window.StreamHunterUI) {
        window.StreamHunterUI.openInVlc(st.stream_url || st.url, st.title || '');
        showOsd('VLC DESKTOP', st.title || st.stream_url);
      }
    } else if (c === 'probe') {
      const st = (state.activeIndex >= 0 && state.activeIndex < len) ? state.queue[state.activeIndex] : null;
      if (st && !IS_POPOUT && window.StreamHunterUI) {
        window.StreamHunterUI.probeSingleById(st.id);
        showOsd('PROBING...', st.title || '');
      }
    } else if (c === 'category') {
      const cat = (payload.category || 'all').toLowerCase();
      state.category = cat;
      if (!IS_POPOUT && window.StreamHunterUI) {
        window.StreamHunterUI.setSubfilter(cat);
      }
      updateRemoteUI();
    } else if (c === 'search') {
      const q = (payload.query || '').trim();
      const cat = (payload.category || 'all').toLowerCase();
      state.category = cat;
      state.query = q;
      if (!IS_POPOUT && window.StreamHunterUI) {
        window.StreamHunterUI.quickSearch(q, cat);
      }
    }
  }

  function activeTitle() {
    const st = (state.activeIndex >= 0 && state.activeIndex < state.queue.length) ? state.queue[state.activeIndex] : null;
    return st ? (st.title || st.stream_url) : 'Standby';
  }

  async function executeAction(action, payload = {}, source = 'remote') {
    // UI-only layout actions
    if (action === 'toggle_float') {
      if (IS_POPOUT) return;
      state.isFloating = !state.isFloating;
      localStorage.setItem(FLOAT_ACTIVE_KEY, state.isFloating ? '1' : '0');
      applyFloatPosition();
      updateRemoteUI();
      return;
    }
    if (action === 'toggle_collapse') {
      if (IS_POPOUT) return;
      state.isCollapsed = !state.isCollapsed;
      localStorage.setItem(COLLAPSE_KEY, state.isCollapsed ? '1' : '0');
      updateRemoteUI();
      return;
    }
    if (action === 'popout') {
      openPopoutWindow();
      return;
    }

    if (IS_POPOUT) {
      // Pop-out sends command via BroadcastChannel AND backend API so it controls main /search or headless VLC
      if (bc) {
        try { bc.postMessage({ type: 'remote_cmd', command: action, payload }); } catch (_e) {}
      }
      try {
        const res = await fetch('/api/hsearch/streams/remote/command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ command: action, payload, source: 'popout' }),
        });
        if (res.ok) {
          const data = await res.json();
          if (data && data.state) applyServerState(data.state);
        }
      } catch (_e) {}
      return;
    }

    applyCommandLocally(action, payload);
  }

  function applyRemoteCommandFromBus(cmdObj, serverState) {
    if (!cmdObj) return;
    const seq = parseInt(cmdObj.seq || 0, 10);
    if (seq > state.lastSeq) state.lastSeq = seq;

    if (serverState && Array.isArray(serverState.queue) && serverState.queue.length > 0) {
      const cmdPayload = cmdObj.payload || {};
      if (cmdPayload.discovered_new_lineup || state.queue.length === 0) {
        state.queue = serverState.queue;
        if (typeof serverState.category === 'string') state.category = serverState.category;
      }
    }
    applyCommandLocally(cmdObj.command, cmdObj.payload || {});
  }

  // ── 6. Numeric Keypad Buffer & Physical Keyboard Shortcuts ──────────────
  function pushDigit(d) {
    if (!/^[0-9]$/.test(String(d))) return;
    if (digitBuffer.length >= 3) digitBuffer = '';
    digitBuffer += String(d);
    showOsd(`CH ${digitBuffer}_`, 'Entering channel number...', 1600);
    updateRemoteUI();
    if (digitTimer) clearTimeout(digitTimer);
    digitTimer = setTimeout(commitDigitBuffer, 1150);
  }

  function commitDigitBuffer() {
    if (digitTimer) {
      clearTimeout(digitTimer);
      digitTimer = null;
    }
    if (!digitBuffer) return;
    const chNum = parseInt(digitBuffer, 10);
    digitBuffer = '';
    updateRemoteUI();
    if (chNum >= 1) {
      executeAction('play_channel', { channel: chNum }, 'keypad');
    }
  }

  function isEditableElement(el) {
    if (!el) return false;
    const tag = (el.tagName || '').toUpperCase();
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || Boolean(el.isContentEditable);
  }

  function handleGlobalKeydown(e) {
    if (isEditableElement(e.target)) return;
    if (!IS_POPOUT) {
      const curMode = window.SearchState && window.SearchState.currentMode;
      if (curMode !== 'streams' && !state.visible) return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    if (/^[0-9]$/.test(e.key)) {
      e.preventDefault();
      pushDigit(e.key);
      return;
    }
    if (e.key === 'Enter') {
      if (digitBuffer) {
        e.preventDefault();
        commitDigitBuffer();
      }
      return;
    }
    if (e.key === 'ArrowUp' || e.key === 'PageUp') {
      e.preventDefault();
      executeAction('ch_up');
    } else if (e.key === 'ArrowDown' || e.key === 'PageDown') {
      e.preventDefault();
      executeAction('ch_down');
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      executeAction('vol_up');
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      executeAction('vol_down');
    } else if (e.key === ' ') {
      e.preventDefault();
      executeAction('pause');
    } else if (e.key === 'm' || e.key === 'M') {
      e.preventDefault();
      executeAction('mute');
    } else if (e.key === 'b' || e.key === 'B' || e.key === 'Backspace') {
      e.preventDefault();
      executeAction('last');
    } else if (e.key === 'v' || e.key === 'V') {
      e.preventDefault();
      executeAction('open_vlc');
    } else if (e.key === 's' || e.key === 'S') {
      e.preventDefault();
      executeAction('stop');
    }
  }

  // ── 7. Floating Drag & Multi-Monitor Pop-out ────────────────────────────
  function applyFloatPosition() {
    const wrap = document.getElementById('sh-remote-wrap');
    if (!wrap) return;
    if (!state.isFloating) {
      wrap.style.left = '';
      wrap.style.top = '';
      return;
    }
    try {
      const saved = JSON.parse(localStorage.getItem(FLOAT_POS_KEY) || 'null');
      if (saved && typeof saved.left === 'number' && typeof saved.top === 'number') {
        wrap.style.left = Math.max(8, Math.min(window.innerWidth - 280, saved.left)) + 'px';
        wrap.style.top = Math.max(8, Math.min(window.innerHeight - 160, saved.top)) + 'px';
      }
    } catch (_e) {}
  }

  function initDragFloating() {
    if (IS_POPOUT) return;
    const handle = document.getElementById('sh-remote-drag-handle');
    const wrap = document.getElementById('sh-remote-wrap');
    if (!handle || !wrap) return;

    let dragging = false;
    let startX = 0, startY = 0, origL = 24, origT = 86;

    handle.addEventListener('mousedown', (e) => {
      if (!state.isFloating) return;
      if (e.target && e.target.closest('button')) return;
      dragging = true;
      const rect = wrap.getBoundingClientRect();
      origL = rect.left;
      origT = rect.top;
      startX = e.clientX;
      startY = e.clientY;
      e.preventDefault();

      const onMove = (mv) => {
        if (!dragging) return;
        const nl = Math.max(8, Math.min(window.innerWidth - 280, origL + (mv.clientX - startX)));
        const nt = Math.max(8, Math.min(window.innerHeight - 80, origT + (mv.clientY - startY)));
        wrap.style.left = nl + 'px';
        wrap.style.top = nt + 'px';
      };
      const onUp = () => {
        if (!dragging) return;
        dragging = false;
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
        const r = wrap.getBoundingClientRect();
        localStorage.setItem(FLOAT_POS_KEY, JSON.stringify({ left: Math.round(r.left), top: Math.round(r.top) }));
      };
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    });
  }

  function openPopoutWindow() {
    try {
      if (popoutWin && !popoutWin.closed) {
        popoutWin.focus();
        return;
      }
      popoutWin = window.open(
        '/search/stream_remote',
        'HecosStreamRemote',
        'width=340,height=660,resizable=yes,scrollbars=yes'
      );
      if (popoutWin) {
        setTimeout(broadcastLocalState, 400);
      }
    } catch (err) {
      console.warn('[StreamRemote] Pop-out blocked:', err);
    }
  }

  // ── 8. Pop-out / Command Polling ────────────────────────────────────────
  function applyServerState(sv) {
    if (!sv || !sv.ok) return;
    if (Array.isArray(sv.queue)) state.queue = sv.queue;
    if (typeof sv.active_index === 'number') state.activeIndex = sv.active_index;
    if (typeof sv.last_index === 'number') state.lastIndex = sv.last_index;
    if (typeof sv.volume === 'number') state.volume = sv.volume;
    if (typeof sv.muted === 'boolean') state.muted = sv.muted;
    if (typeof sv.paused === 'boolean') state.paused = sv.paused;
    if (sv.target) state.target = sv.target;
    if (typeof sv.proxy_enabled === 'boolean') state.proxyEnabled = sv.proxy_enabled;
    if (sv.category) state.category = sv.category;
    if (typeof sv.query === 'string') state.query = sv.query;
    if (sv.preset_settings) state.presetSettings = sv.preset_settings;
    if (typeof sv.command_seq === 'number' && sv.command_seq > state.lastSeq) {
      state.lastSeq = sv.command_seq;
    }
    updateRemoteUI();
  }

  async function pollRemoteBus() {
    try {
      const res = await fetch(`/api/hsearch/streams/remote/state?since_seq=${state.lastSeq}`, {
        credentials: 'same-origin',
      });
      if (!res.ok) return;
      const data = await res.json();
      if (!data || !data.ok) return;
      if (data.preset_settings) {
        state.presetSettings = data.preset_settings;
      }
      if (IS_POPOUT) {
        applyServerState(data);
        return;
      }
      if (Array.isArray(data.pending_commands) && data.pending_commands.length > 0) {
        for (const cmdObj of data.pending_commands) {
          if (cmdObj.source === 'ui') {
            if (cmdObj.seq > state.lastSeq) state.lastSeq = cmdObj.seq;
            continue;
          }
          applyRemoteCommandFromBus(cmdObj, data);
        }
      }
    } catch (_e) {}
  }

  // ── 9. Initialization & Public API ──────────────────────────────────────
  function bindRemoteControls() {
    const shell = document.getElementById('sh-remote-shell');
    if (shell && !shell.dataset.bound) {
      shell.dataset.bound = '1';
      shell.addEventListener('click', (e) => {
        const btn = e.target.closest('button');
        if (!btn) return;
        if (btn.dataset.shDigit !== undefined) {
          pushDigit(btn.dataset.shDigit);
          return;
        }
        const act = btn.dataset.shAction;
        if (!act) return;
        if (act === 'category') {
          executeAction('category', { category: btn.dataset.shCat || 'all' });
        } else {
          executeAction(act);
        }
      });

      const volSlider = document.getElementById('sh-rem-vol-slider');
      if (volSlider) {
        volSlider.addEventListener('input', () => {
          executeAction('set_volume', { volume: parseInt(volSlider.value, 10) });
        });
      }
    }

    if (bc) {
      bc.onmessage = (ev) => {
        const msg = ev && ev.data;
        if (!msg) return;
        if (IS_POPOUT && msg.type === 'state_sync' && msg.payload) {
          Object.assign(state, msg.payload);
          updateRemoteUI();
        } else if (!IS_POPOUT && msg.type === 'remote_cmd' && msg.command) {
          applyCommandLocally(msg.command, msg.payload || {});
        }
      };
    }

    window.addEventListener('keydown', handleGlobalKeydown);
    window.addEventListener('hecos:preset_changed', refreshPresetBadge);
  }

  function init() {
    if (!IS_POPOUT) {
      state.isFloating = localStorage.getItem(FLOAT_ACTIVE_KEY) === '1';
      state.isCollapsed = localStorage.getItem(COLLAPSE_KEY) === '1';
      const curMode = window.SearchState && window.SearchState.currentMode;
      state.visible = (curMode === 'streams');
      applyFloatPosition();
    } else if (window.SH_REMOTE_INITIAL_STATE) {
      applyServerState(window.SH_REMOTE_INITIAL_STATE);
    }

    bindRemoteControls();
    initDragFloating();
    updateRemoteUI();
    fetchPresetSettings();

    if (!pollTimer) {
      pollTimer = setInterval(pollRemoteBus, IS_POPOUT ? 1600 : 2500);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.StreamRemoteController = {
    syncLineup(streams, meta = {}) {
      state.queue = (streams || []).map((st, i) => ({ ...st, ch_num: i + 1 }));
      if (meta.category) state.category = meta.category;
      if (typeof meta.query === 'string') state.query = meta.query;
      if (state.activeIndex >= state.queue.length) state.activeIndex = -1;
      updateRemoteUI();
      scheduleBackendSync();
    },
    setActiveStream(streamObj) {
      if (!streamObj) {
        state.activeIndex = -1;
      } else {
        const url = streamObj.stream_url || streamObj.url || '';
        const idx = state.queue.findIndex(x => (x.stream_url || x.url) === url || x.id === streamObj.id);
        if (idx >= 0) {
          if (state.activeIndex >= 0 && state.activeIndex !== idx) state.lastIndex = state.activeIndex;
          state.activeIndex = idx;
          showOsd(`CH ${formatCh(idx + 1)}`, streamObj.title || url);
        }
      }
      updateRemoteUI();
      scheduleBackendSync();
    },
    setRemoteModeVisible(show) {
      state.visible = Boolean(show) || IS_POPOUT;
      updateRemoteUI();
      if (state.visible) fetchPresetSettings();
    },
    executeAction,
    applyRemoteCommandFromBus,
    getState() { return { ...state }; },
    refreshPresetBadge,
  };
})();
