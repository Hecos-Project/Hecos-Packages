/**
 * search_copilot.js
 * Hecos AI Support intelligence, live SSE chat, sidebar/presenter drag-resizer, and orchestration.
 * Delegates Markdown (copilot_markdown.js), Voice/TTS (copilot_voice.js), Mic STT (copilot_mic.js), and Presets (copilot_presets.js).
 */
window.SearchCopilot = (function () {
  'use strict';

  let chatHistory = [];
  let isGenerating = false;
  let activeRequestController = null;
  let activeRequestToken = 0;
  let activeGenerationState = null;
  let presenterEventSource = null;
  let userAvatarUrl = window.HecosUserAvatar || '';
  let autoMode = (function () {
    try {
      const v = localStorage.getItem('hecos_copilot_automode');
      return v === null ? true : v !== 'false';
    } catch (e) {
      return true;
    }
  })();

  function updateAutoModeUI() {
    const btn = document.getElementById('copilot-automode-toggle');
    if (!btn) return;
    btn.classList.toggle('is-auto', autoMode);
    btn.classList.toggle('is-manual', !autoMode);
    if (autoMode) {
      btn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> Auto-Mode: ON';
      btn.title = 'Auto-Mode ON: AI autonomously chooses optimal mode (Global Sweep, ClearWeb, DarkWeb, Files, OSINT) and category tab. Click to lock to manual mode pill.';
    } else {
      btn.innerHTML = '<i class="fas fa-lock"></i> Mode: Manual';
      btn.title = 'Manual Mode: AI strictly searches inside your currently selected mode pill. Click to enable autonomous Auto-Mode.';
    }
  }

  function toggleAutoMode() {
    autoMode = !autoMode;
    try {
      localStorage.setItem('hecos_copilot_automode', autoMode ? 'true' : 'false');
    } catch (e) { /* ignore */ }
    updateAutoModeUI();
    appendSystemNotice(autoMode
      ? '<i class="fas fa-wand-magic-sparkles"></i> <strong>Auto-Mode ON</strong>: AI will pick the best search mode autonomously.'
      : `<i class="fas fa-lock"></i> <strong>Manual Mode</strong>: AI locked to <strong>${escapeHtml((window.SearchState?.currentMode || 'clear').toUpperCase())}</strong>.`
    );
  }

  async function resolveUserAvatar() {
    if (window.HecosUserAvatar) {
      userAvatarUrl = window.HecosUserAvatar;
      return;
    }
    try {
      const res = await fetch('/hecos/api/users/me/avatar');
      if (res.ok && res.url && !res.url.includes('/login')) {
        userAvatarUrl = res.url;
        window.HecosUserAvatar = res.url;
        document.querySelectorAll('.copilot-chat-messages .copilot-user-avatar').forEach(el => {
          el.innerHTML = `<img src="${escapeHtml(userAvatarUrl)}" class="copilot-avatar-img" alt="User" onerror="this.outerHTML='<i class=\\'fas fa-user\\'></i>';">`;
        });
      }
    } catch (e) {
      // Keep icon fallback
    }
  }


  // ── Helper Module Bridges ────────────────────────────────────────────────
  const escapeHtml = (s) => (window.SearchCopilotMarkdown ? window.SearchCopilotMarkdown.escapeHtml(s) : String(s || ''));
  const formatMarkdown = (t, c) => (window.SearchCopilotMarkdown ? window.SearchCopilotMarkdown.formatMarkdown(t, c) : escapeHtml(t));
  const renderAssistantBubble = (el, t, s) => window.SearchCopilotMarkdown?.renderAssistantBubble?.(el, t, s);

  const isVoiceActive = () => Boolean(window.SearchCopilotVoice?.isVoiceActive?.());
  const isVoiceEnabled = () => Boolean(window.SearchCopilotVoice?.isVoiceEnabled?.());
  const stopVoice = () => window.SearchCopilotVoice?.stopVoice?.();
  const toggleVoiceOutput = () => window.SearchCopilotVoice?.toggleVoiceOutput?.();
  const updateTtsToggleUI = () => window.SearchCopilotVoice?.updateTtsToggleUI?.();
  const speakAssistantMessage = (el, ov) => window.SearchCopilotVoice?.speakAssistantMessage?.(el, ov);
  const attachListenAction = (el, b) => window.SearchCopilotVoice?.attachListenAction?.(el, b);

  const loadPresets = () => window.SearchCopilotPresets?.loadPresets?.();
  const getCurrentPresetId = () => (window.SearchCopilotPresets ? window.SearchCopilotPresets.getCurrentPresetId() : 'default');
  const getCurrentPreset = () => (window.SearchCopilotPresets ? window.SearchCopilotPresets.getCurrentPreset() : null);
  const getAssistantAvatarHtml = (p) => (window.SearchCopilotPresets ? window.SearchCopilotPresets.getAssistantAvatarHtml(p) : '');

  const bindCopilotMicButton = () => window.SearchCopilotMic?.bindCopilotMicButton?.();
  const bindCopilotMicKeyboard = () => window.SearchCopilotMic?.bindCopilotMicKeyboard?.();
  const setCopilotMicState = (st) => window.SearchCopilotMic?.setCopilotMicState?.(st);

  // ── 3. Chat UI Helpers ─────────────────────────────────────────────────────
  function appendMessage(role, text) {
    const container = document.getElementById('copilot-chat-messages');
    if (!container) return null;

    const msgEl = document.createElement('div');
    msgEl.className = `copilot-msg copilot-msg-${role}`;

    let avatarInner = '';
    let avatarClass = 'copilot-msg-avatar';
    let avatarTitle = '';

    if (role === 'user') {
      avatarClass += ' copilot-user-avatar';
      const usrName = window.HecosUserName || 'User';
      avatarTitle = usrName;
      const usrSrc = window.HecosUserAvatar || userAvatarUrl;
      if (usrSrc) {
        avatarInner = `<img src="${escapeHtml(usrSrc)}" class="copilot-avatar-img" alt="${escapeHtml(usrName)}" onerror="this.outerHTML='<i class=\\'fas fa-user\\'></i>';">`;
      } else {
        avatarInner = '<i class="fas fa-user"></i>';
      }
    } else {
      avatarClass += ' copilot-assistant-avatar';
      const curPreset = getCurrentPreset();
      avatarTitle = curPreset ? (curPreset.soul_name || curPreset.name || 'Hecos AI') : 'Hecos AI';
      avatarInner = getAssistantAvatarHtml(curPreset);
    }

    msgEl.innerHTML = `
      <div class="${avatarClass}" title="${escapeHtml(avatarTitle)}">${avatarInner}</div>
      <div class="copilot-msg-bubble">
        <div class="copilot-msg-text"></div>
      </div>
    `;

    if (role === 'assistant') {
      renderAssistantBubble(msgEl, text, false);
    } else {
      const textEl = msgEl.querySelector('.copilot-msg-text');
      if (textEl) textEl.innerHTML = formatMarkdown(text);
    }

    container.appendChild(msgEl);
    container.scrollTop = container.scrollHeight;
    return msgEl;
  }

  function appendSystemNotice(text, upsertKey = null) {
    const container = document.getElementById('copilot-chat-messages');
    if (!container) return;
    if (upsertKey) {
      const existing = Array.from(container.querySelectorAll('.copilot-sys-notice')).find(
        n => n.dataset && n.dataset.upsertKey === upsertKey
      );
      if (existing) {
        existing.innerHTML = text;
        return;
      }
    }
    const el = document.createElement('div');
    el.className = 'copilot-sys-notice';
    if (upsertKey) {
      el.dataset.upsertKey = upsertKey;
    }
    el.innerHTML = text;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
  }

  // ── 3.5 UI Sync Helpers for Copilot-Driven Search ────────────────────────
  function applyPlannedSearchToUI(plan) {
    if (!plan || !plan.query) return;
    const targetMode = plan.mode || window.SearchState?.currentMode || 'clear';
    const targetFilter = plan.filter || 'all';

    const searchInput = document.getElementById('search-input');
    if (searchInput) {
      searchInput.value = plan.query;
    }

    if (window.SearchState) {
      window.SearchState.currentQuery = plan.query;
      window.SearchState.currentMode = targetMode;
      window.SearchState.hasMorePages = (targetMode !== 'dark');
    }

    const targetPill = document.querySelector(`.mode-pill[data-mode="${targetMode}"]`);
    if (targetPill) {
      document.querySelectorAll('.mode-pill').forEach(p => p.classList.remove('active'));
      targetPill.classList.add('active');
    }

    if (window.SearchFilters && window.SearchFilters.renderFilterTabsForMode) {
      window.SearchFilters.renderFilterTabsForMode(targetMode, false);
      if (targetFilter && window.SearchFilters.setFilter) {
        window.SearchFilters.setFilter(targetFilter, false, true);
      }
    }

    const resultsCountEl = document.getElementById('results-count');
    if (resultsCountEl) {
      const curPreset = getCurrentPreset();
      const charName = (curPreset && (curPreset.soul_name || curPreset.name)) || 'Hecos AI';
      resultsCountEl.innerText = `${charName} searching ${targetMode.toUpperCase()} for "${plan.query}"...`;
    }
  }

  // ── 4. Chat Send, Instant Stop & SSE Stream ────────────────────────────────
  function updateSendButtonState(generating) {
    const sendBtn = document.getElementById('copilot-chat-send');
    if (!sendBtn) return;
    sendBtn.disabled = false;
    if (generating) {
      sendBtn.classList.add('is-stopping');
      sendBtn.innerHTML = '<i class="fas fa-stop"></i><span>Stop</span>';
      sendBtn.title = 'Stop request (Esc)';
      sendBtn.setAttribute('aria-label', 'Stop request');
    } else {
      sendBtn.classList.remove('is-stopping');
      sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
      sendBtn.title = 'Send message (Enter)';
      sendBtn.setAttribute('aria-label', 'Send message');
    }
  }

  function stopActiveMainSearchStream() {
    if (window.SearchState?.activeEventSource && window.SearchState.activeEventSource.readyState !== 2) {
      if (window.SearchStream && typeof window.SearchStream.stopSearch === 'function') {
        window.SearchStream.stopSearch();
        return true;
      }
      if (typeof window.stopSearch === 'function') {
        window.stopSearch();
        return true;
      }
    }
    return false;
  }

  function stopCopilotRequest() {
    let stoppedAny = false;
    if (isGenerating || activeRequestController) {
      stoppedAny = true;
      activeRequestToken += 1;
      isGenerating = false;

      if (activeRequestController) {
        try { activeRequestController.abort(); } catch (e) {}
        activeRequestController = null;
      }

      if (activeGenerationState) {
        const { assistantMsg, bubbleTextEl, getAccumulated } = activeGenerationState;
        const partial = typeof getAccumulated === 'function' ? (getAccumulated() || '') : '';
        if (partial.trim() && assistantMsg) {
          renderAssistantBubble(assistantMsg, partial, false);
          if (bubbleTextEl) {
            const note = document.createElement('div');
            note.className = 'copilot-stopped-note';
            note.innerHTML = '<i class="fas fa-stop-circle"></i> Request stopped';
            bubbleTextEl.appendChild(note);
          }
          chatHistory.push({ role: 'assistant', content: partial });
        } else if (bubbleTextEl) {
          bubbleTextEl.innerHTML = '<span class="copilot-stopped-inline"><i class="fas fa-stop-circle"></i> Request stopped by user.</span>';
        }
        activeGenerationState = null;
      }
      updateSendButtonState(false);

      const resultsCountEl = document.getElementById('results-count');
      if (resultsCountEl && /searching/i.test(resultsCountEl.innerText || '')) {
        const total = window.SearchState?.results?.length || 0;
        resultsCountEl.innerText = total > 0 ? `${total} of ${total} results found (Stopped)` : 'Search stopped by user';
      }
    }

    if (stopActiveMainSearchStream()) {
      stoppedAny = true;
    }

    if (stoppedAny) {
      const input = document.getElementById('copilot-chat-input');
      if (input && !input.disabled) {
        input.focus();
      }
    }
    return stoppedAny;
  }

  async function sendMessage(text) {
    if (!text || !text.trim() || isGenerating) return;
    const cleanText = text.trim();

    const input = document.getElementById('copilot-chat-input');
    if (input) input.value = '';

    appendMessage('user', cleanText);
    chatHistory.push({ role: 'user', content: cleanText });

    const myGenToken = ++activeRequestToken;
    const controller = new AbortController();
    activeRequestController = controller;
    isGenerating = true;
    updateSendButtonState(true);

    // Prepare assistant message bubble for streaming
    const assistantMsg = appendMessage('assistant', '');
    const bubbleTextEl = assistantMsg ? assistantMsg.querySelector('.copilot-msg-text') : null;
    if (bubbleTextEl) {
      bubbleTextEl.innerHTML = '<span class="copilot-typing-dots"><span>.</span><span>.</span><span>.</span></span>';
    }

    const activeSessionId = window.SearchState?.activeSessionId || window.SearchState?.currentSessionId || '';
    const hasResults = Boolean(window.SearchState?.results && window.SearchState.results.length > 0);
    let accumulated = '';
    let plannedNewSearch = false;
    let plannedFilter = null;
    activeGenerationState = {
      assistantMsg,
      bubbleTextEl,
      getAccumulated: () => accumulated
    };

    try {
      const response = await fetch('/api/hsearch/copilot/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          message: cleanText,
          preset_id: getCurrentPresetId(),
          session_id: activeSessionId,
          active_mode: window.SearchState?.currentMode || 'clear',
          auto_mode: autoMode,
          current_query: window.SearchState?.currentQuery || '',
          has_results: hasResults,
          limit: window.SearchState?.searchLimit ?? 100,
          safe_search: Boolean(window.SearchState?.safeSearch),
          dark_bypass: window.SearchState?.darkBypass !== false,
          local_only: Boolean(window.SearchState?.localOnly),
          stream: true
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        if (myGenToken !== activeRequestToken) {
          try { await reader.cancel(); } catch (_e) {}
          break;
        }
        const { value, done } = await reader.read();
        if (done) break;
        if (myGenToken !== activeRequestToken) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (myGenToken !== activeRequestToken) break;
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;
          const jsonStr = trimmed.slice(5).trim();
          if (!jsonStr) continue;

          try {
            const ev = JSON.parse(jsonStr);
            if (ev.type === 'search_plan') {
              plannedNewSearch = (ev.action === 'new_search');
              plannedFilter = ev.filter || null;
              applyPlannedSearchToUI(ev);
              if (bubbleTextEl && !accumulated) {
                bubbleTextEl.innerHTML = `<span style="color:var(--accent-cyan, #06b6d4); font-size:12px;"><i class="fas fa-satellite fa-spin"></i> Searching ${escapeHtml((ev.mode || 'deep').toUpperCase())}: "${escapeHtml(ev.query || '')}"...</span>`;
              }
            } else if (ev.type === 'session') {
              if (window.SearchState && ev.session_id) {
                window.SearchState.activeSessionId = ev.session_id;
                window.SearchState.currentSessionId = ev.session_id;
              }
              if (ev.session_id && (plannedNewSearch || ev.session_id !== activeSessionId)) {
                if (window.SearchHistory && typeof window.SearchHistory.loadSession === 'function') {
                  Promise.resolve(
                    window.SearchHistory.loadSession(ev.session_id, ev.filter || plannedFilter, false)
                  ).then(() => {
                    if (myGenToken !== activeRequestToken) return;
                    if (assistantMsg && window.SearchState && Array.isArray(window.SearchState.results)) {
                      assistantMsg._citeResults = window.SearchState.results.slice(0, 25);
                      if (accumulated && !isGenerating) {
                        renderAssistantBubble(assistantMsg, accumulated, false);
                      }
                    }
                  }).catch(() => {});
                  if (typeof window.SearchHistory.loadHistory === 'function') {
                    window.SearchHistory.loadHistory(true);
                  }
                }
              }
            } else if (ev.type === 'status') {
              if (bubbleTextEl && !accumulated) {
                bubbleTextEl.innerHTML = `<span style="color:var(--accent-cyan, #06b6d4); font-size:12px;"><i class="fas fa-satellite fa-spin"></i> ${escapeHtml(ev.text || 'Processing...')}</span>`;
              }
            } else if (ev.type === 'token') {
              accumulated += ev.text || '';
              if (assistantMsg) {
                renderAssistantBubble(assistantMsg, accumulated, true);
                const container = document.getElementById('copilot-chat-messages');
                if (container) container.scrollTop = container.scrollHeight;
              }
            } else if (ev.type === 'done') {
              if (ev.text && !accumulated) {
                accumulated = ev.text;
              }
              if (assistantMsg && accumulated) {
                renderAssistantBubble(assistantMsg, accumulated, false);
              }
            } else if (ev.type === 'error') {
              if (bubbleTextEl) bubbleTextEl.innerHTML = `<span style="color:#f87171;">⚠️ ${escapeHtml(ev.error || 'Generation error')}</span>`;
            }
          } catch (pe) {
            // Non-JSON SSE line or heartbeat
          }
        }
      }

      if (myGenToken !== activeRequestToken) {
        return;
      }

      if (assistantMsg && accumulated) {
        if (!assistantMsg._citeResults && window.SearchState && Array.isArray(window.SearchState.results) && window.SearchState.results.length) {
          assistantMsg._citeResults = window.SearchState.results.slice(0, 25);
        }
        renderAssistantBubble(assistantMsg, accumulated, false);
        if (isVoiceEnabled()) {
          speakAssistantMessage(assistantMsg);
        }
      }
      chatHistory.push({ role: 'assistant', content: accumulated });
    } catch (err) {
      if ((err && err.name === 'AbortError') || myGenToken !== activeRequestToken) {
        return;
      }
      console.error('[HecosAI] Chat streaming failed:', err);
      if (bubbleTextEl) {
        bubbleTextEl.innerHTML = `<span style="color:#f87171;">⚠️ Connection error to Hecos AI Assistant: ${escapeHtml(err.message)}</span>`;
      }
    } finally {
      if (myGenToken === activeRequestToken) {
        isGenerating = false;
        activeRequestController = null;
        activeGenerationState = null;
        updateSendButtonState(false);
      }
    }
  }

  // ── 5. Sidebar Width Resizer ──────────────────────────────────────────────
  function initSidebarResizer() {
    const resizer = document.getElementById('copilot-resizer');
    const sidebar = document.getElementById('search-copilot');
    if (!resizer || !sidebar) return;

    // Restore saved width from localStorage
    const savedWidth = parseInt(localStorage.getItem('hecos_search_copilot_w'), 10);
    if (savedWidth && savedWidth >= 240 && savedWidth <= window.innerWidth * 0.8) {
      sidebar.style.width = savedWidth + 'px';
      document.documentElement.style.setProperty('--copilot-w', savedWidth + 'px');
    }

    let isDragging = false;
    let startX = 0;
    let startW = 0;

    resizer.addEventListener('mousedown', (e) => {
      isDragging = true;
      startX = e.clientX;
      startW = sidebar.getBoundingClientRect().width;
      resizer.classList.add('is-resizing');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';

      const onMouseMove = (moveEvent) => {
        if (!isDragging) return;
        const deltaX = startX - moveEvent.clientX; // Moving left widens sidebar
        let newW = Math.round(startW + deltaX);
        const minW = 260;
        const maxW = Math.floor(window.innerWidth * 0.65);
        if (newW < minW) newW = minW;
        if (newW > maxW) newW = maxW;

        sidebar.style.width = newW + 'px';
        document.documentElement.style.setProperty('--copilot-w', newW + 'px');
      };

      const onMouseUp = () => {
        if (!isDragging) return;
        isDragging = false;
        resizer.classList.remove('is-resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);

        const finalW = Math.round(sidebar.getBoundingClientRect().width);
        localStorage.setItem('hecos_search_copilot_w', finalW.toString());
      };

      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
      e.preventDefault();
    });
  }

  // ── 7. Search Updates & Synthesis ──────────────────────────────────────────
  function updateOverview(results, query, mode, showNotice = true) {
    const summaryCard = document.getElementById('copilot-summary-content');
    if (!summaryCard) return;

    if (!results || results.length === 0) {
      summaryCard.innerHTML = '<span style="color:var(--text-dim); font-size:12px;">Waiting for search results to generate intelligence summary...</span>';
      return;
    }

    const total = results.length;
    const onionCount = results.filter(r => r.network === 'tor' || (r.url && r.url.includes('.onion'))).length;
    const clearCount = total - onionCount;
    const engines = [...new Set(results.map(r => r.engine).filter(Boolean))].join(', ');

    summaryCard.innerHTML = `
      <div style="font-weight:600; margin-bottom:6px; color:var(--text-main);">
        Analysis for "${escapeHtml(query)}"
      </div>
      <div style="display:flex; flex-direction:column; gap:4px; font-size:12px; color:var(--text-muted);">
        <div>• <strong>${total}</strong> sources indexed successfully</div>
        <div>• Distribution: <strong>${clearCount}</strong> Clearnet, <strong>${onionCount}</strong> Tor (.onion)</div>
        <div>• Active engines: <span style="font-family:var(--font-mono); color:var(--accent);">${escapeHtml(engines)}</span></div>
      </div>
    `;

    // Prompt greeting in assistant chat (1 deduplicated notice per search session/query)
    if (showNotice) {
      const curPreset = getCurrentPreset();
      const charName = curPreset ? (curPreset.soul_name || curPreset.name || 'AI') : 'AI';
      const noticeKey = `search-complete:${window.SearchState?.activeSessionId || window.SearchState?.currentSessionId || query || ''}`;
      appendSystemNotice(
        `🔍 Search completed for <strong>"${escapeHtml(query)}"</strong> (${total} sources). Ask ${escapeHtml(charName)} to analyze or summarize the findings!`,
        noticeKey
      );
    }
  }

  // ── 8. Export Report ───────────────────────────────────────────────────────
  function generateReport(results, query) {
    if (!results || results.length === 0) {
      alert('No results available to export.');
      return;
    }

    let md = `# Deep Search Investigation Report: ${query}\n`;
    md += `*Date: ${new Date().toLocaleString()}*  \n`;
    md += `*Total indexed sources: ${results.length}*\n\n---\n\n`;

    results.forEach((r, idx) => {
      const net = r.network === 'tor' ? '[TOR/ONION]' : '[CLEARWEB]';
      md += `### ${idx + 1}. ${net} ${r.title}\n`;
      md += `- **URL**: ${r.url}\n`;
      md += `- **Engine**: ${r.engine}\n`;
      if (r.snippet) {
        md += `- **Snippet**: ${r.snippet}\n`;
      }
      md += `\n`;
    });

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `hecos_search_${(query || 'report').replace(/\W+/g, '_')}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function buildInitialGreetingEl() {
    const curPreset = getCurrentPreset();
    const charName = curPreset ? (curPreset.soul_name || curPreset.name || 'Hecos AI') : 'Hecos AI';
    const avatarHtml = getAssistantAvatarHtml(curPreset);
    const welcomeText = 'Hello! I can synthesize sources, surface top media, extract data, and analyze search findings.';

    const msgEl = document.createElement('div');
    msgEl.className = 'copilot-msg copilot-msg-assistant';
    msgEl.innerHTML = `
      <div class="copilot-msg-avatar copilot-assistant-avatar" id="copilot-initial-avatar" title="${escapeHtml(charName)}">${avatarHtml}</div>
      <div class="copilot-msg-bubble">
        <div class="copilot-msg-text">${escapeHtml(welcomeText)}</div>
      </div>
    `;
    attachListenAction(msgEl, welcomeText);
    return msgEl;
  }

  function resetChat() {
    stopVoice();

    activeRequestToken++;
    if (activeRequestController) {
      try { activeRequestController.abort(); } catch (_e) {}
      activeRequestController = null;
    }
    isGenerating = false;
    activeGenerationState = null;
    updateSendButtonState(false);

    chatHistory = [];

    const summaryCard = document.getElementById('copilot-summary-content');
    if (summaryCard) {
      summaryCard.innerHTML = '<span style="color:var(--text-dim); font-size:12px;">Waiting for search results to generate intelligence summary...</span>';
    }

    const container = document.getElementById('copilot-chat-messages');
    if (container) {
      container.innerHTML = '';
      container.appendChild(buildInitialGreetingEl());
      container.scrollTop = 0;
    }

    const inputEl = document.getElementById('copilot-chat-input');
    if (inputEl) {
      inputEl.value = '';
    }
  }

  // ── 9. Public API & Initialization ─────────────────────────────────────────
  return {
    init() {
      loadPresets();
      resolveUserAvatar();
      initSidebarResizer();
      updateAutoModeUI();
      updateTtsToggleUI();
      bindCopilotMicButton();
      bindCopilotMicKeyboard();
      setCopilotMicState('idle');

      // Attach Listen action button on the initial assistant greeting message
      const welcomeMsg = document.querySelector('#copilot-chat-messages .copilot-msg-assistant');
      if (welcomeMsg) {
        attachListenAction(welcomeMsg, welcomeMsg.querySelector('.copilot-msg-text')?.innerText || '');
      }

      const newSearchBtn = document.getElementById('copilot-new-search-btn');
      if (newSearchBtn) {
        newSearchBtn.addEventListener('click', () => {
          if (typeof window.startNewSearch === 'function') {
            window.startNewSearch('copilot');
          } else {
            resetChat();
          }
        });
      }

      const autoBtn = document.getElementById('copilot-automode-toggle');
      if (autoBtn) {
        autoBtn.addEventListener('click', toggleAutoMode);
      }

      const ttsToggleBtn = document.getElementById('copilot-tts-toggle');
      if (ttsToggleBtn) {
        ttsToggleBtn.addEventListener('click', toggleVoiceOutput);
      }

      const stopVoiceBtn = document.getElementById('copilot-stop-voice-btn');
      if (stopVoiceBtn) {
        stopVoiceBtn.addEventListener('click', stopVoice);
      }

      const infoBtn = document.getElementById('copilot-preset-info-btn');
      const popoverEl = document.getElementById('copilot-preset-popover');
      if (infoBtn && popoverEl) {
        infoBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          const willOpen = popoverEl.style.display === 'none';
          popoverEl.style.display = willOpen ? 'flex' : 'none';
          infoBtn.classList.toggle('is-open', willOpen);
        });
        document.addEventListener('click', (e) => {
          if (popoverEl.style.display !== 'none' && !popoverEl.contains(e.target) && e.target !== infoBtn) {
            popoverEl.style.display = 'none';
            infoBtn.classList.remove('is-open');
          }
        });
      }

      document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        if (document.querySelector('.search-modal-backdrop.open')) return;

        // 1st Esc: if voice playback/synthesis is active, stop ONLY voice (never interrupt search/request)
        if (isVoiceActive()) {
          e.preventDefault();
          e.stopPropagation();
          stopVoice();
          return;
        }

        // 2nd Esc (or Esc when no voice is active): stop active Copilot request and/or active Search stream
        if (stopCopilotRequest()) {
          e.preventDefault();
        }
      });

      const input = document.getElementById('copilot-chat-input');
      const sendBtn = document.getElementById('copilot-chat-send');

      if (sendBtn) {
        sendBtn.addEventListener('click', () => {
          if (isGenerating) {
            stopCopilotRequest();
            return;
          }
          if (input) sendMessage(input.value);
        });
      }

      if (input) {
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(input.value);
          }
        });
      }

      // Quick prompt chips
      document.querySelectorAll('.copilot-chip').forEach(chip => {
        chip.addEventListener('click', () => {
          const prompt = chip.dataset.prompt;
          if (prompt) sendMessage(prompt);
        });
      });
    },

    update(results, query, mode, showNotice = true) {
      updateOverview(results, query, mode, showNotice);
    },

    sendMessage(text) {
      sendMessage(text);
    },

    toggleAutoMode() {
      toggleAutoMode();
    },

    isAutoMode() {
      return autoMode;
    },

    toggleVoiceOutput() {
      toggleVoiceOutput();
    },

    isVoiceEnabled() {
      return isVoiceEnabled();
    },

    stopVoice() {
      stopVoice();
    },

    stopRequest() {
      return stopCopilotRequest();
    },

    appendSystemNotice(text) {
      appendSystemNotice(text);
    },

    isGeneratingRequest() {
      return isGenerating;
    },

    resetChat() {
      resetChat();
    },

    isVoiceActive() {
      return isVoiceActive();
    },

    exportReport() {
      generateReport(window.SearchState?.results || [], window.SearchState?.currentQuery || 'query');
    },

    togglePresenter() {
      const toggle = document.getElementById('hbs-presenter-toggle');
      if (toggle) toggle.click();
    }
  };
})();

window.togglePresenterPanel = function () {
  const toggle = document.getElementById('hbs-presenter-toggle');
  if (toggle) {
    toggle.click();
  } else if (window.Presenter && typeof window.Presenter.setDisplayMode === 'function') {
    const emb = document.getElementById('hbs-presenter-embedded');
    const isColl = emb ? emb.classList.contains('collapsed') : false;
    window.Presenter.setDisplayMode(isColl ? 'embedded' : 'collapsed');
  }
};

// Auto-boot on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  if (window.SearchCopilot && typeof window.SearchCopilot.init === 'function') {
    window.SearchCopilot.init();
  }
});
