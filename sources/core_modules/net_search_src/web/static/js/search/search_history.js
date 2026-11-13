/**
 * search_history.js
 * Session history retrieval, sidebar list rendering, real-time live synchronization,
 * and past session detail loader for Deep Search.
 */
(function() {
  const state = window.SearchState;
  const api = window.SearchAPI;

  let _lastSessionsDigest = '';
  let _isLoading = false;
  let _editingSessionId = null;
  let _sessionsById = {};
  let _cachedSessions = [];
  let _liveSession = null;
  const _groupOpenState = {};

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getLocalDateKey(dateObj) {
    const y = dateObj.getFullYear();
    const m = String(dateObj.getMonth() + 1).padStart(2, '0');
    const d = String(dateObj.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function extractSessionDateKey(createdAt) {
    const m = String(createdAt || '').trim().match(/^(\d{4}-\d{2}-\d{2})/);
    return m ? m[1] : 'unknown';
  }

  function formatDateGroupLabel(dateKey) {
    if (dateKey === 'unknown') return 'Other Dates';
    const now = new Date();
    const todayKey = getLocalDateKey(now);
    if (dateKey === todayKey) return 'Today';

    const yest = new Date(now);
    yest.setDate(yest.getDate() - 1);
    if (dateKey === getLocalDateKey(yest)) return 'Yesterday';

    const parts = dateKey.split('-').map(Number);
    if (parts.length === 3 && !parts.some(isNaN)) {
      const d = new Date(parts[0], parts[1] - 1, parts[2]);
      try {
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
      } catch (_e) { /* fallback below */ }
    }
    return dateKey;
  }

  function isDateGroupOpen(dateKey) {
    if (Object.prototype.hasOwnProperty.call(_groupOpenState, dateKey)) {
      return Boolean(_groupOpenState[dateKey]);
    }
    return dateKey === getLocalDateKey(new Date());
  }

  function toggleDateGroup(dateKey) {
    if (!dateKey) return;
    const nextOpen = !isDateGroupOpen(dateKey);
    _groupOpenState[dateKey] = nextOpen;

    const groupEl = document.querySelector(`.history-date-group[data-date-key="${CSS.escape(dateKey)}"]`);
    if (groupEl) {
      groupEl.classList.toggle('is-collapsed', !nextOpen);
      const headerBtn = groupEl.querySelector('.history-date-header');
      if (headerBtn) {
        headerBtn.setAttribute('aria-expanded', nextOpen ? 'true' : 'false');
      }
    }
  }

  function notifySessionsUpdated() {
    if (typeof BroadcastChannel !== 'undefined') {
      try {
        const bc = new BroadcastChannel('hecos_netsearch_channel');
        bc.postMessage({ type: 'session_updated' });
        bc.close();
      } catch (_e) { /* ignore */ }
    }
  }

  function formatNowLocalDateTime() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    return `${y}-${m}-${day} ${hh}:${mm}:${ss}`;
  }

  function mergeWithLiveSession(serverSessions) {
    const list = Array.isArray(serverSessions) ? serverSessions.map(s => Object.assign({}, s)) : [];
    if (!_liveSession) return list;

    const liveIds = new Set([_liveSession.id, _liveSession.tempId].filter(Boolean));
    let matched = false;
    const merged = list.map(s => {
      if (liveIds.has(s.id)) {
        matched = true;
        return Object.assign({}, s, {
          total_results: Math.max(Number(s.total_results || 0), Number(_liveSession.total_results || 0)),
          is_live: Boolean(_liveSession.is_live)
        });
      }
      return s;
    });
    if (!matched) {
      merged.unshift(Object.assign({}, _liveSession));
    }
    return merged;
  }

  function renderHistoryItemHtml(s, isNew) {
    const safeId = escapeHtml(s.id);
    const displayTitle = (s.title && s.title.trim()) ? s.title.trim() : s.query;
    const tooltipText = (s.title && s.title.trim() && s.title.trim() !== s.query)
      ? `${s.title.trim()} (Original query: ${s.query})`
      : s.query;
    const isLive = Boolean(_liveSession && (_liveSession.id === s.id || _liveSession.tempId === s.id) && _liveSession.is_live);
    const liveCount = isLive ? Math.max(Number(s.total_results || 0), Number(_liveSession.total_results || 0)) : (s.total_results || 0);

    return `
      <div class="history-item ${s.id === state.activeSessionId ? 'active' : ''} ${isNew ? 'history-item-new' : ''} ${isLive ? 'is-live-searching' : ''}"
           data-session-id="${safeId}"
           onclick="window.loadSession('${safeId}')">
        <div class="history-item-top">
          <div class="history-query" title="${escapeHtml(tooltipText)}">
            ${isLive ? '<i class="fas fa-circle-notch fa-spin history-live-spinner" aria-hidden="true"></i> ' : ''}${escapeHtml(displayTitle)}
          </div>
          <div class="history-item-actions" onclick="event.stopPropagation()">
            <button type="button" class="btn-history-action btn-history-rename"
                    title="Rename search tab"
                    aria-label="Rename search tab"
                    onclick="event.stopPropagation(); window.startRenameHistoryTab('${safeId}')">
              <i class="fas fa-pen"></i>
            </button>
            <button type="button" class="btn-history-action btn-history-delete"
                    title="Delete search tab"
                    aria-label="Delete search tab"
                    onclick="event.stopPropagation(); window.deleteHistoryTab('${safeId}')">
              <i class="fas fa-trash-alt"></i>
            </button>
          </div>
        </div>
        <div class="history-meta">
          <span class="history-mode-pill">${escapeHtml((s.mode || 'web').toUpperCase())}</span>
          <span>&bull;</span>
          <span class="history-count-label">${liveCount} res.</span>
          <span>&bull;</span>
          <span class="history-time-label">${isLive ? 'searching...' : escapeHtml((s.created_at || '').split(' ')[1] || '')}</span>
        </div>
      </div>
    `;
  }

  function renderHistoryList(sessions) {
    const historyListEl = document.getElementById('history-list');
    if (!historyListEl) return;

    const isInitial = !_lastSessionsDigest;
    const prevScrollTop = historyListEl.scrollTop;

    if (!sessions || sessions.length === 0) {
      historyListEl.innerHTML = '<div class="history-empty-hint">No saved searches yet</div>';
      historyListEl.scrollTop = 0;
      return;
    }

    const todayKey = getLocalDateKey(new Date());
    const groupedOrder = [];
    const groupsByDate = {};

    sessions.forEach((s, idx) => {
      const dateKey = extractSessionDateKey(s.created_at);
      if (!groupsByDate[dateKey]) {
        groupsByDate[dateKey] = [];
        groupedOrder.push(dateKey);
      }
      groupsByDate[dateKey].push({ session: s, globalIdx: idx });
    });

    historyListEl.innerHTML = groupedOrder.map(dateKey => {
      const items = groupsByDate[dateKey];
      const safeKey = escapeHtml(dateKey);
      const label = formatDateGroupLabel(dateKey);
      const isOpen = isDateGroupOpen(dateKey);
      const isToday = dateKey === todayKey;

      return `
        <div class="history-date-group ${isOpen ? '' : 'is-collapsed'}" data-date-key="${safeKey}">
          <button type="button"
                  class="history-date-header ${isToday ? 'is-today' : ''}"
                  aria-expanded="${isOpen ? 'true' : 'false'}"
                  title="${escapeHtml(dateKey === 'unknown' ? 'Other Dates' : dateKey)}"
                  onclick="window.toggleHistoryDateGroup('${safeKey}')">
            <span class="history-date-header-left">
              <i class="fas fa-chevron-down history-date-chevron" aria-hidden="true"></i>
              <span class="history-date-label">${escapeHtml(label)}</span>
            </span>
            <span class="history-date-count">${items.length}</span>
          </button>
          <div class="history-date-items">
            ${items.map(entry => renderHistoryItemHtml(entry.session, !isInitial && entry.globalIdx === 0)).join('')}
          </div>
        </div>
      `;
    }).join('');

    historyListEl.scrollTop = prevScrollTop;
  }

  function startRenameHistoryTab(sessionId) {
    if (!sessionId) return;
    if (_editingSessionId && _editingSessionId !== sessionId) {
      cancelRenameHistoryTab(false);
    }

    const itemEl = document.querySelector(`.history-item[data-session-id="${CSS.escape(sessionId)}"]`);
    if (!itemEl) return;
    const topEl = itemEl.querySelector('.history-item-top');
    if (!topEl) return;

    const sess = _sessionsById[sessionId] || {};
    const currentTitle = (sess.title && sess.title.trim()) ? sess.title.trim() : (sess.query || itemEl.querySelector('.history-query')?.innerText || '');

    _editingSessionId = sessionId;
    itemEl.classList.add('is-renaming');

    topEl.innerHTML = `
      <div class="history-rename-row" onclick="event.stopPropagation()">
        <input type="text" class="history-rename-input" value="${escapeHtml(currentTitle)}"
               maxlength="200" aria-label="New search tab name">
        <button type="button" class="btn-history-action btn-history-save" title="Save name" aria-label="Save name">
          <i class="fas fa-check"></i>
        </button>
        <button type="button" class="btn-history-action btn-history-cancel" title="Cancel rename" aria-label="Cancel rename">
          <i class="fas fa-times"></i>
        </button>
      </div>
    `;

    const inputEl = topEl.querySelector('.history-rename-input');
    const saveBtn = topEl.querySelector('.btn-history-save');
    const cancelBtn = topEl.querySelector('.btn-history-cancel');

    if (saveBtn) {
      saveBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        commitRenameHistoryTab(sessionId, inputEl ? inputEl.value : '');
      });
    }
    if (cancelBtn) {
      cancelBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        cancelRenameHistoryTab(true);
      });
    }
    if (inputEl) {
      inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          e.stopPropagation();
          commitRenameHistoryTab(sessionId, inputEl.value);
        } else if (e.key === 'Escape') {
          e.preventDefault();
          e.stopPropagation();
          cancelRenameHistoryTab(true);
        }
      });
      inputEl.focus();
      inputEl.select();
    }
  }

  function cancelRenameHistoryTab(shouldRefresh = true) {
    _editingSessionId = null;
    if (shouldRefresh) {
      loadHistory(true);
    }
  }

  async function commitRenameHistoryTab(sessionId, rawTitle) {
    const cleanTitle = (rawTitle || '').trim();
    if (!cleanTitle) {
      cancelRenameHistoryTab(true);
      return;
    }

    if (!api || !api.renameSession) return;
    try {
      const res = await api.renameSession(sessionId, cleanTitle);
      if (res && res.ok) {
        if (_sessionsById[sessionId]) {
          _sessionsById[sessionId].title = res.title || cleanTitle;
        }
        _editingSessionId = null;
        notifySessionsUpdated();
        await loadHistory(true);
      } else {
        console.warn('[SearchHistory] Rename rejected:', res);
        cancelRenameHistoryTab(true);
      }
    } catch (e) {
      console.error('[SearchHistory] Failed to rename session:', e);
      cancelRenameHistoryTab(true);
    }
  }

  async function deleteHistoryTab(sessionId) {
    if (!sessionId || !api || !api.deleteSession) return;
    try {
      const res = await api.deleteSession(sessionId);
      if (res && res.ok) {
        if (_editingSessionId === sessionId) {
          _editingSessionId = null;
        }
        delete _sessionsById[sessionId];
        if (_liveSession && (_liveSession.id === sessionId || _liveSession.tempId === sessionId)) {
          _liveSession = null;
        }
        if (state.activeSessionId === sessionId && typeof window.startNewSearch === 'function') {
          window.startNewSearch('search');
        }
        notifySessionsUpdated();
        await loadHistory(true);
      } else {
        console.warn('[SearchHistory] Delete failed:', res);
      }
    } catch (e) {
      console.error('[SearchHistory] Failed to delete session:', e);
    }
  }

  async function loadHistory(force = false) {
    const historyListEl = document.getElementById('history-list');
    if (!historyListEl || !api || !api.getSessions || _isLoading) return;
    if (_editingSessionId && !force) return;
    
    _isLoading = true;
    try {
      const res = await api.getSessions(200);
      if (res.ok && res.sessions) {
        if (_editingSessionId && !force) return;

        _cachedSessions = res.sessions;
        const combined = mergeWithLiveSession(res.sessions);

        const nextMap = {};
        combined.forEach(s => { nextMap[s.id] = s; });
        _sessionsById = nextMap;

        const todayKey = getLocalDateKey(new Date());
        const liveFlag = _liveSession && _liveSession.is_live ? `|LIVE:${_liveSession.id}:${_liveSession.total_results}` : '';
        const digest = `${todayKey}${liveFlag}|` + combined.map(s => `${s.id}:${s.total_results}:${s.title || ''}`).join('|');
        
        // If nothing changed in the sessions list, only update active highlight
        if (!force && digest === _lastSessionsDigest) {
          historyListEl.querySelectorAll('.history-item').forEach(el => {
            const sid = el.getAttribute('data-session-id');
            el.classList.toggle('active', sid === state.activeSessionId);
          });
          return;
        }

        renderHistoryList(combined);
        _lastSessionsDigest = digest;
      }
    } catch (e) {
      console.error('[SearchHistory] Failed to load history:', e);
    } finally {
      _isLoading = false;
    }
  }

  async function loadSession(sessionId, preferredFilter = null, updateCopilot = true) {
    if (!sessionId || String(sessionId).startsWith('pending_') || !api || !api.getSessionDetail) return;
    try {
      const res = await api.getSessionDetail(sessionId);
      if (res.ok && res.session) {
        const s = res.session;
        state.activeSessionId = s.id;
        state.currentQuery = s.query;
        state.currentMode = s.mode;
        state.results = s.results || [];
        state.activeEngine = null;
        state.activeProvider = null;
        state.excludedProviders = [];
        state.refineQuery = '';
        state.sortBy = 'default';
        state.mediaSubFilter = 'all';
        state.currentPage = 1;
        state.scrollRenderCount = 40;
        state.hasMorePages = (s.mode !== 'dark');

        const searchInput = document.getElementById('search-input');
        if (searchInput) searchInput.value = s.query;

        // Set active mode pill
        const modePills = document.querySelectorAll('.mode-pill');
        modePills.forEach(p => {
          p.classList.toggle('active', p.dataset.mode === s.mode);
        });

        const filters = window.SearchFilters;
        if (filters && filters.renderFilterTabsForMode) {
          filters.renderFilterTabsForMode(s.mode, !preferredFilter);
          if (preferredFilter && filters.setFilter) {
            filters.setFilter(preferredFilter, false, true);
          }
        }

        // Rebuild persistent engine chips from saved session
        const engineCounts = {};
        const engineStats = {};
        state.results.forEach(r => {
          const eng = r.engine_id || r.metadata?.engine_id || r.engine || 'web';
          engineCounts[eng] = (engineCounts[eng] || 0) + 1;
          if (!engineStats[eng]) {
            engineStats[eng] = { count: 0, raw_count: 0, new_count: 0, status: 'done', categories: {} };
          }
          engineStats[eng].count += 1;
          const cat = r.category || 'web';
          engineStats[eng].categories[cat] = (engineStats[eng].categories[cat] || 0) + 1;
        });
        state.engineStats = engineStats;

        const streamBar = document.getElementById('stream-live-bar');
        const streamBadges = document.getElementById('stream-badges');
        const streamStatusIcon = document.getElementById('stream-status-icon');
        const streamStatusText = document.getElementById('stream-status-text');
        const btnClearEngine = document.getElementById('btn-clear-engine-filter');

        if (streamBar) {
          streamBar.classList.add('active');
          streamBar.classList.toggle('is-collapsed', Boolean(state.isStreamCollapsed));
        }
        if (streamStatusIcon) {
          streamStatusIcon.className = 'fas fa-circle-check';
          streamStatusIcon.style.color = 'var(--accent-emerald)';
        }
        if (streamStatusText) {
          streamStatusText.innerText = 'Engines used in this session (click to filter):';
        }
        if (btnClearEngine) {
          btnClearEngine.style.display = 'none';
        }

        const getMacroInfo = (eng) => {
          if (window.SearchStream && window.SearchStream.HECOS_ENGINE_INFO && window.SearchStream.HECOS_ENGINE_INFO[eng.toLowerCase()]) {
            return window.SearchStream.HECOS_ENGINE_INFO[eng.toLowerCase()];
          }
          if (window.SearchFilters && window.SearchFilters.getEngineDisplayInfo) {
            const d = window.SearchFilters.getEngineDisplayInfo(eng);
            return { name: d.name, icon: d.icon, desc: eng };
          }
          if (window.SearchStream && window.SearchStream.getHecosEngineInfo) {
            return window.SearchStream.getHecosEngineInfo(eng);
          }
          return { name: eng, icon: 'fas fa-check', desc: eng };
        };

        if (streamBadges) {
          streamBadges.innerHTML = Object.entries(engineCounts).map(([eng, count]) => {
            const info = getMacroInfo(eng);
            const safeEng = escapeHtml(eng);
            const safeName = escapeHtml(info.name);
            const safeIcon = escapeHtml(info.icon || 'fas fa-check');
            return `
            <button class="engine-chip done" id="chip-${safeEng}" data-engine="${safeEng}" onclick="window.filterByEngine('${safeEng}')" title="${safeName} (${count} results)&#10;Click to filter exclusively">
              <i class="${safeIcon}"></i> <span class="chip-engine-name">${safeName}</span> <span class="chip-count">${count}</span>
            </button>
          `;
          }).join('');
        }

        const copilot = window.SearchCopilot;
        if (filters) {
          if (filters.syncRefineToolbarUI) {
            filters.syncRefineToolbarUI();
          }
          filters.updateFilterCounts();
          if (filters.updateExclusionBar) {
            filters.updateExclusionBar();
          }
          if (filters.renderGranularProviderChips) {
            filters.renderGranularProviderChips();
          }
          if (filters.updateCollapsedPill) {
            filters.updateCollapsedPill();
          }
          filters.renderCurrentView();
        }
        if (copilot && copilot.update) {
          copilot.update(state.results, s.query, s.mode, updateCopilot);
        }

        document.querySelectorAll('.history-item').forEach(it => {
          it.classList.toggle('active', it.getAttribute('data-session-id') === s.id);
        });
      }
    } catch (e) {
      console.error('[SearchHistory] Load session detail error:', e);
    }
  }

  // ── History Sidebar Width Resizer ─────────────────────────────────────────
  function initHistorySidebarResizer() {
    const resizer = document.getElementById('sidebar-resizer');
    const sidebar = document.getElementById('search-sidebar');
    if (!resizer || !sidebar) return;

    // Restore saved width from localStorage
    const savedWidth = parseInt(localStorage.getItem('hecos_search_sidebar_w'), 10);
    if (savedWidth && savedWidth >= 180 && savedWidth <= window.innerWidth * 0.5) {
      sidebar.style.width = savedWidth + 'px';
      document.documentElement.style.setProperty('--sidebar-w', savedWidth + 'px');
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
        const deltaX = moveEvent.clientX - startX; // Dragging right widens left sidebar
        let newW = Math.round(startW + deltaX);
        const minW = 180;
        const maxW = Math.floor(window.innerWidth * 0.45);
        if (newW < minW) newW = minW;
        if (newW > maxW) newW = maxW;

        sidebar.style.width = newW + 'px';
        document.documentElement.style.setProperty('--sidebar-w', newW + 'px');
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
        try {
          localStorage.setItem('hecos_search_sidebar_w', String(finalW));
        } catch (e) { /* ignore */ }
      };

      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
    });
  }

  // ── Real-Time Auto-Sync Listeners ───────────────────────────────────────────
  // 1. Cross-tab BroadcastChannel (instant push when a search completes in another tab)
  if (typeof BroadcastChannel !== 'undefined') {
    try {
      const bc = new BroadcastChannel('hecos_netsearch_channel');
      bc.onmessage = function(event) {
        if (event.data && (event.data.type === 'new_session' || event.data.type === 'session_updated')) {
          loadHistory(true);
        }
      };
    } catch (e) {}
  }

  // 2. Storage event fallback (for cross-window sync)
  window.addEventListener('storage', function(e) {
    if (e.key === 'hecos_netsearch_event') {
      loadHistory(true);
    }
  });

  // 3. Tab visibility / Window Focus: refresh immediately when returning to Net Search tab
  window.addEventListener('focus', function() {
    loadHistory();
  });
  document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') {
      loadHistory();
    }
  });

  // 4. Background Poller: every 3 seconds while page is active
  setInterval(function() {
    if (document.visibilityState === 'visible') {
      loadHistory();
    }
  }, 3000);

  // Auto-init resizer when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHistorySidebarResizer);
  } else {
    initHistorySidebarResizer();
  }

  function createPendingTab(queryStr, mode, tempId) {
    const cleanQ = String(queryStr || '').trim();
    if (!cleanQ) return;
    const todayKey = getLocalDateKey(new Date());
    _groupOpenState[todayKey] = true;

    _liveSession = {
      id: tempId,
      tempId: tempId,
      query: cleanQ,
      title: '',
      mode: mode || 'clear',
      total_results: 0,
      created_at: formatNowLocalDateTime(),
      is_live: true
    };
    state.activeSessionId = tempId;
    state.currentSessionId = tempId;

    const combined = mergeWithLiveSession(_cachedSessions);
    const nextMap = {};
    combined.forEach(s => { nextMap[s.id] = s; });
    _sessionsById = nextMap;
    _lastSessionsDigest = '';
    renderHistoryList(combined);
  }

  function bindLiveSessionId(tempId, realId, createdAt) {
    if (!realId) return;
    state.activeSessionId = realId;
    state.currentSessionId = realId;
    if (_liveSession && (_liveSession.tempId === tempId || _liveSession.id === tempId)) {
      _liveSession.id = realId;
      if (createdAt) _liveSession.created_at = createdAt;
    } else {
      _liveSession = {
        id: realId,
        tempId: tempId,
        query: state.currentQuery || '',
        title: '',
        mode: state.currentMode || 'clear',
        total_results: (state.results && state.results.length) || 0,
        created_at: createdAt || formatNowLocalDateTime(),
        is_live: true
      };
    }

    const oldEl = tempId
      ? document.querySelector(`.history-item[data-session-id="${CSS.escape(tempId)}"]`)
      : null;
    if (oldEl) {
      oldEl.setAttribute('data-session-id', realId);
      oldEl.setAttribute('onclick', `window.loadSession('${realId}')`);
      const renameBtn = oldEl.querySelector('.btn-history-rename');
      if (renameBtn) renameBtn.setAttribute('onclick', `event.stopPropagation(); window.startRenameHistoryTab('${realId}')`);
      const delBtn = oldEl.querySelector('.btn-history-delete');
      if (delBtn) delBtn.setAttribute('onclick', `event.stopPropagation(); window.deleteHistoryTab('${realId}')`);
    }
    if (_sessionsById[tempId]) {
      _sessionsById[realId] = Object.assign({}, _sessionsById[tempId], { id: realId });
      delete _sessionsById[tempId];
    }
  }

  function updateLiveTabProgress(sessionId, count, isDone = false) {
    if (_liveSession && (!sessionId || _liveSession.id === sessionId || _liveSession.tempId === sessionId)) {
      _liveSession.total_results = Number(count || 0);
      if (isDone) {
        _liveSession.is_live = false;
      }
    }
    const targetId = sessionId || (_liveSession && _liveSession.id);
    if (targetId) {
      const el = document.querySelector(`.history-item[data-session-id="${CSS.escape(targetId)}"]`);
      if (el) {
        const cntEl = el.querySelector('.history-count-label');
        if (cntEl) cntEl.textContent = `${Number(count || 0)} res.`;
        if (isDone) {
          el.classList.remove('is-live-searching');
          const spin = el.querySelector('.history-live-spinner');
          if (spin) spin.remove();
          const tEl = el.querySelector('.history-time-label');
          if (tEl) {
            const hhmm = (_liveSession && _liveSession.created_at ? _liveSession.created_at.split(' ')[1] : '') || '';
            tEl.textContent = hhmm;
          }
        }
      }
    }
    if (isDone) {
      _liveSession = null;
    }
  }

  window.SearchHistory = {
    loadHistory,
    loadSession,
    createPendingTab,
    bindLiveSessionId,
    updateLiveTabProgress,
    clearLiveSession: () => { _liveSession = null; },
    initHistorySidebarResizer,
    startRenameHistoryTab,
    deleteHistoryTab,
    toggleHistoryDateGroup: toggleDateGroup
  };

  // Global window alias
  window.loadHistory = loadHistory;
  window.loadSession = loadSession;
  window.createPendingTab = createPendingTab;
  window.bindLiveSessionId = bindLiveSessionId;
  window.updateLiveTabProgress = updateLiveTabProgress;
  window.startRenameHistoryTab = startRenameHistoryTab;
  window.deleteHistoryTab = deleteHistoryTab;
  window.toggleHistoryDateGroup = toggleDateGroup;
})();
