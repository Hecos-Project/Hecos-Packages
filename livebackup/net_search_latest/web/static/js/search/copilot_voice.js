/**
 * copilot_voice.js
 * Copilot TTS voice controls, progressive/single audio playback, and cross-tab HecosAudioBus synchronization.
 */
window.SearchCopilotVoice = (function () {
  'use strict';

  let ttsEnabled = (function () {
    try {
      return localStorage.getItem('hecos_search_tts_enabled') === 'true';
    } catch (e) {
      return false;
    }
  })();
  let activeTtsAudio = null;
  let activeTtsEvtSource = null;
  let activeTtsFetchController = null;
  let isTtsInProgress = false;
  let activeTtsToken = 0;

  // ── 1a. Voice / TTS Controls & Cross-Tab Audio Coordination ───────────────
  function updateTtsToggleUI() {
    const btn = document.getElementById('copilot-tts-toggle');
    if (!btn) return;
    btn.classList.toggle('is-active', ttsEnabled);
    btn.classList.toggle('is-muted', !ttsEnabled);
    if (ttsEnabled) {
      btn.innerHTML = '<i class="fas fa-volume-up"></i> Voice: ON';
      btn.title = 'Voice Output ON: Net Search Copilot replies will be spoken using the active Global Preset TTS (automatically pauses Main Chat if playing).';
    } else {
      btn.innerHTML = '<i class="fas fa-volume-xmark"></i> Voice: OFF';
      btn.title = 'Toggle Voice Output (auto-speak Copilot replies using the selected Global Preset TTS)';
    }
  }

  function showCopilotStopVoiceBtn(visible) {
    const btn = document.getElementById('copilot-stop-voice-btn');
    if (btn) {
      btn.style.display = visible ? 'inline-flex' : 'none';
    }
  }

  function isVoiceActive() {
    if (isTtsInProgress || activeTtsEvtSource) return true;
    if (activeTtsAudio && !activeTtsAudio.paused && !activeTtsAudio.ended) return true;
    const sidebarAudio = document.querySelector('#search-copilot audio');
    if (sidebarAudio && !sidebarAudio.paused && !sidebarAudio.ended) return true;
    const stopBtn = document.getElementById('copilot-stop-voice-btn');
    if (stopBtn && stopBtn.style.display !== 'none') return true;
    return false;
  }

  function stopLocalSearchAudio() {
    activeTtsToken += 1;
    isTtsInProgress = false;
    if (activeTtsFetchController) {
      try { activeTtsFetchController.abort(); } catch (e) {}
      activeTtsFetchController = null;
    }
    if (activeTtsEvtSource) {
      try { activeTtsEvtSource.close(); } catch (e) {}
      activeTtsEvtSource = null;
    }
    if (activeTtsAudio) {
      try { activeTtsAudio.pause(); } catch (e) {}
      activeTtsAudio = null;
    }
    document.querySelectorAll('.copilot-tts-progress').forEach(el => el.remove());
    document.querySelectorAll('.copilot-listen-btn').forEach(btn => {
      btn.disabled = false;
    });
    showCopilotStopVoiceBtn(false);
  }

  function stopVoice() {
    stopLocalSearchAudio();
    if (window.HecosAudioBus) {
      window.HecosAudioBus.stopAll('net_search');
    }
    try { fetch('/api/audio/stop', { method: 'POST' }).catch(() => {}); } catch (e) {}
    try { fetch('/api/audio/speaking/stop', { method: 'POST' }).catch(() => {}); } catch (e) {}
  }

  function toggleVoiceOutput() {
    ttsEnabled = !ttsEnabled;
    try {
      localStorage.setItem('hecos_search_tts_enabled', ttsEnabled ? 'true' : 'false');
    } catch (e) { /* ignore */ }
    updateTtsToggleUI();
    if (!ttsEnabled) {
      stopVoice();
    }
    window.SearchCopilot?.appendSystemNotice?.(ttsEnabled
      ? '<i class="fas fa-volume-up"></i> <strong>Voice Output ON</strong>: Copilot replies will use the selected Global Preset voice.'
      : '<i class="fas fa-volume-xmark"></i> <strong>Voice Output OFF</strong>: Manual Listen button remains available on every reply.'
    );
  }

  function extractSpokenText(rawText) {
    if (!rawText) return '';
    const { body } = (window.SearchCopilotMarkdown ? window.SearchCopilotMarkdown.splitThinkingContent : (t) => ({ thinking: "", body: String(t || ""), isThinkingStreaming: false }))(rawText);
    return (body || rawText || '')
      .replace(/```[\s\S]*?```/g, ' ')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\[(\d+)\]/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/https?:\/\/\S+/g, '')
      .replace(/\*{1,3}|_{1,3}|~{1,2}/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  async function speakAssistantMessage(msgEl, overrideText = null) {
    if (!msgEl) return;
    const bubbleEl = msgEl.querySelector('.copilot-msg-bubble');
    const textEl = msgEl.querySelector('.copilot-msg-text');
    if (!bubbleEl || !textEl) return;

    const spokenText = extractSpokenText(
      overrideText !== null ? overrideText : (msgEl.dataset.rawBody || textEl.innerText || textEl.textContent || '')
    );
    if (!spokenText) return;

    // Preempt our own previous player and claim global browser audio ownership
    stopLocalSearchAudio();
    const myToken = ++activeTtsToken;
    isTtsInProgress = true;
    const ttsController = new AbortController();
    activeTtsFetchController = ttsController;
    if (window.HecosAudioBus) {
      window.HecosAudioBus.claim('net_search', { playbackId: 'ns_' + myToken });
    }

    const listenBtn = msgEl.querySelector('.copilot-listen-btn');
    if (listenBtn) listenBtn.disabled = true;
    showCopilotStopVoiceBtn(true);

    bubbleEl.querySelectorAll('.copilot-audio-badge, .copilot-tts-progress').forEach(el => el.remove());

    const progressEl = document.createElement('div');
    progressEl.className = 'copilot-tts-progress';
    progressEl.innerHTML = `
      <div class="copilot-tts-progress-header">
        <span class="copilot-tts-progress-label">Generating audio... (0%)</span>
        <button type="button" class="copilot-tts-cancel" title="Cancel voice generation">✖</button>
      </div>
      <div class="copilot-tts-track"><div class="copilot-tts-fill" style="width:0%;"></div></div>
    `;
    bubbleEl.appendChild(progressEl);

    const fillEl = progressEl.querySelector('.copilot-tts-fill');
    const labelEl = progressEl.querySelector('.copilot-tts-progress-label');
    const cancelBtn = progressEl.querySelector('.copilot-tts-cancel');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => stopVoice());
    }

    const cleanupUi = () => {
      if (progressEl.parentNode) progressEl.remove();
      if (listenBtn) listenBtn.disabled = false;
    };

    try {
      const res = await fetch('/api/audio/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        signal: ttsController.signal,
        body: JSON.stringify({
          text: spokenText,
          mode: 'web',
          bypass_cache: true,
          preset_id: (window.SearchCopilotPresets ? window.SearchCopilotPresets.getCurrentPresetId() : 'default')
        })
      });
      if (myToken !== activeTtsToken) {
        cleanupUi();
        return;
      }
      const data = await res.json();
      if (!res.ok || !data.ok || !data.job_id) {
        isTtsInProgress = false;
        cleanupUi();
        showCopilotStopVoiceBtn(false);
        return;
      }

      const evt = new EventSource(`/api/audio/test/progress/${encodeURIComponent(data.job_id)}`);
      activeTtsEvtSource = evt;

      evt.onmessage = async (event) => {
        if (myToken !== activeTtsToken) {
          evt.close();
          cleanupUi();
          return;
        }
        try {
          const prog = JSON.parse(event.data);
          if (prog.status === 'not_found' || prog.status === 'error') {
            evt.close();
            if (activeTtsEvtSource === evt) activeTtsEvtSource = null;
            isTtsInProgress = false;
            cleanupUi();
            showCopilotStopVoiceBtn(false);
            return;
          }
          if (prog.total > 0) {
            const pct = Math.min(100, Math.round((prog.current / prog.total) * 100));
            if (fillEl) fillEl.style.width = `${pct}%`;
            if (labelEl) labelEl.textContent = `Generating audio... (${pct}%)`;
          }
          if (prog.status === 'done') {
            evt.close();
            if (activeTtsEvtSource === evt) activeTtsEvtSource = null;
            cleanupUi();
            const audioUrl = prog.audio_id
              ? `/api/audio?id=${encodeURIComponent(prog.audio_id)}`
              : `/api/audio?t=${Date.now()}`;
            await playGeneratedAudio(bubbleEl, audioUrl, myToken);
          }
        } catch (err) {
          console.warn('[HecosAI] TTS progress parse error:', err);
        }
      };

      evt.onerror = () => {
        evt.close();
        if (activeTtsEvtSource === evt) activeTtsEvtSource = null;
        isTtsInProgress = false;
        cleanupUi();
        showCopilotStopVoiceBtn(false);
      };
    } catch (e) {
      isTtsInProgress = false;
      if (!e || e.name !== 'AbortError') {
        console.warn('[HecosAI] TTS request failed:', e);
      }
      cleanupUi();
      showCopilotStopVoiceBtn(false);
    }
  }

  async function playGeneratedAudio(bubbleEl, audioUrl, expectedToken) {
    if (!bubbleEl || expectedToken !== activeTtsToken) return;
    const badge = document.createElement('div');
    badge.className = 'copilot-audio-badge';

    const audioFetchCtrl = new AbortController();
    activeTtsFetchController = audioFetchCtrl;
    let blobUrl = '';
    try {
      const resp = await fetch(audioUrl, { credentials: 'same-origin', signal: audioFetchCtrl.signal });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      blobUrl = URL.createObjectURL(blob);
    } catch (err) {
      isTtsInProgress = false;
      if (err && err.name === 'AbortError') return;
      console.warn('[HecosAI] Audio blob fetch failed:', err);
      badge.innerHTML = `<span style="font-size:11px; color:#f87171;"><i class="fas fa-exclamation-triangle"></i> Audio unavailable</span>`;
      bubbleEl.appendChild(badge);
      showCopilotStopVoiceBtn(false);
      return;
    }

    if (expectedToken !== activeTtsToken) {
      URL.revokeObjectURL(blobUrl);
      return;
    }

    const audioEl = document.createElement('audio');
    audioEl.controls = true;
    audioEl.src = blobUrl;
    if (typeof window.globalTTSVolume === 'number') {
      audioEl.volume = window.globalTTSVolume;
    }
    audioEl.onplay = () => {
      activeTtsAudio = audioEl;
      isTtsInProgress = true;
      if (window.HecosAudioBus) {
        window.HecosAudioBus.claim('net_search', { playbackId: 'ns_play_' + Date.now() });
      }
      showCopilotStopVoiceBtn(true);
    };
    const _onStopOrEnd = () => {
      if (activeTtsAudio === audioEl) activeTtsAudio = null;
      isTtsInProgress = false;
      showCopilotStopVoiceBtn(false);
      try { fetch('/api/audio/speaking/stop', { method: 'POST' }).catch(() => {}); } catch (e) {}
    };
    audioEl.onpause = _onStopOrEnd;
    audioEl.onended = _onStopOrEnd;
    audioEl.onerror = _onStopOrEnd;

    activeTtsAudio = audioEl;
    badge.appendChild(audioEl);
    bubbleEl.appendChild(badge);

    try {
      await audioEl.play();
    } catch (playErr) {
      isTtsInProgress = false;
      const hint = document.createElement('span');
      hint.style.cssText = 'display:block; margin-top:4px; font-size:10.5px; color:var(--accent);';
      hint.textContent = 'Click Play to listen (browser autoplay blocked)';
      badge.appendChild(hint);
      showCopilotStopVoiceBtn(false);
    }
  }

  function attachListenAction(msgEl, rawBody) {
    if (!msgEl) return;
    const bubbleEl = msgEl.querySelector('.copilot-msg-bubble');
    if (!bubbleEl) return;
    let bar = bubbleEl.querySelector('.copilot-msg-actions');
    if (!bar) {
      bar = document.createElement('div');
      bar.className = 'copilot-msg-actions';

      const listenBtn = document.createElement('button');
      listenBtn.type = 'button';
      listenBtn.className = 'copilot-msg-action-btn copilot-listen-btn';
      listenBtn.innerHTML = '<i class="fas fa-volume-up" aria-hidden="true"></i> Listen';
      listenBtn.title = 'Listen (full message or highlighted text using active Global Preset TTS)';

      let capturedSelection = null;
      listenBtn.addEventListener('pointerdown', (e) => {
        if (e.pointerType === 'mouse') e.preventDefault();
        const sel = window.getSelection();
        capturedSelection = (sel && sel.toString().trim()) ? sel.toString().trim() : null;
      });
      listenBtn.addEventListener('click', () => {
        const toSpeak = capturedSelection || msgEl.dataset.rawBody || null;
        capturedSelection = null;
        speakAssistantMessage(msgEl, toSpeak);
      });

      bar.appendChild(listenBtn);
      bubbleEl.appendChild(bar);
    }
    if (rawBody !== undefined && rawBody !== null) {
      msgEl.dataset.rawBody = String(rawBody);
    }
  }

  // Register cross-tab listeners once
  if (window.HecosAudioBus) {
    window.HecosAudioBus.onClaim((msg) => {
      console.log(`[HecosAI] Remote tab (${msg.owner}) claimed audio — stopping Net Search player.`);
      stopLocalSearchAudio();
    });
    window.HecosAudioBus.onStopAll(() => {
      stopLocalSearchAudio();
    });
  }

  return {
    updateTtsToggleUI,
    showCopilotStopVoiceBtn,
    isVoiceActive,
    stopLocalSearchAudio,
    stopVoice,
    toggleVoiceOutput,
    isVoiceEnabled() { return ttsEnabled; },
    extractSpokenText,
    speakAssistantMessage,
    playGeneratedAudio,
    attachListenAction
  };
})();
