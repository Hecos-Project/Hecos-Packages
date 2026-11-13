/**
 * search_main.js
 * Main orchestrator and controller for Hecos Deep Search page.
 * Wires together SearchFilters, SearchStream, SearchHistory, and SearchModals.
 */
function initSearchMain() {
  const state = window.SearchState;
  const api = window.SearchAPI;
  const filters = window.SearchFilters;
  const stream = window.SearchStream;
  const history = window.SearchHistory;
  const modals = window.SearchModals;

  const searchInput = document.getElementById('search-input');
  const searchBtn = document.getElementById('search-submit');
  const modePills = document.querySelectorAll('.mode-pill');

  // ── Sync Tor Config from Server ───────────────────────────────────────────
  if (api && api.getConfig) {
    api.getConfig().then(data => {
      if (data && data.ok && data.config) {
        const tor = data.config.tor || {};
        window.currentTorAction = tor.onion_action || 'hecos_viewer';
        window.torBrowserPath = tor.tor_browser_path || '';
      }
    }).catch(() => { });
  }

  // ── Mode Switcher & Subtabs Initialization ────────────────────────────────
  const activeInitialPill = document.querySelector('.mode-pill.active');
  if (activeInitialPill && activeInitialPill.dataset.mode) {
    state.currentMode = activeInitialPill.dataset.mode;
  }
  const activeInitialFilter = document.querySelector('.filter-tab.active');
  if (activeInitialFilter && activeInitialFilter.dataset.filter) {
    state.activeFilter = activeInitialFilter.dataset.filter;
  }

  // Ensure contextual tabs match initial mode
  if (filters && filters.renderFilterTabsForMode) {
    filters.renderFilterTabsForMode(state.currentMode, true);
  }

  modePills.forEach(pill => {
    pill.addEventListener('click', () => {
      modePills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      state.currentMode = pill.dataset.mode;

      // Auto-switch contextual filter tabs for the selected mode
      if (filters && filters.renderFilterTabsForMode) {
        filters.renderFilterTabsForMode(state.currentMode, false);
      }

      if (state.currentQuery && stream && stream.executeSearch) {
        stream.executeSearch(state.currentQuery, state.currentMode);
      }
    });
  });

  // ── Form Submit ────────────────────────────────────────────────────────────
  if (searchBtn && searchInput) {
    searchBtn.addEventListener('click', () => {
      if (stream && stream.executeSearch) {
        stream.executeSearch(searchInput.value, state.currentMode);
      }
    });

    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (stream && stream.executeSearch) {
          stream.executeSearch(searchInput.value, state.currentMode);
        }
      }
    });
  }

  // ── Global Keyboard Shortcuts ──────────────────────────────────────────────
  window.addEventListener('keydown', (e) => {
    const ae = document.activeElement;
    const isTyping = ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.tagName === 'SELECT' || ae.isContentEditable);
    if ((e.ctrlKey && e.key === 'k') || (e.key === '/' && !isTyping)) {
      if (searchInput) {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }
    }
    if (e.key === 'Escape') {
      if (modals && modals.closeAllModals) {
        modals.closeAllModals();
      }
    }
  });

  // ── Initial Subsystems Boot ────────────────────────────────────────────────
  if (filters) {
    filters.updateViewModeButtons();
    filters.initInfiniteScroll();
  }
  if (history && history.loadHistory) {
    history.loadHistory();
    if (history.initHistorySidebarResizer) {
      history.initHistorySidebarResizer();
    }
  }
  if (modals && modals.refreshTorStatus) {
    modals.refreshTorStatus();
  }

  // Load initial settings (e.g. privacy shield local_only default)
  fetch('/api/hsearch/config').then(r => r.json()).then(data => {
    if (data && data.ok && data.config) {
      if (data.config.local_only && filters && filters.toggleLocalOnly) {
        filters.toggleLocalOnly(true);
      }
    }
  }).catch(() => { });

  // If query passed in URL parameter on load
  const urlParams = new URLSearchParams(window.location.search);
  const qParam = urlParams.get('q');
  let modeParam = urlParams.get('mode');
  if (modeParam === 'media') modeParam = 'clear'; // Graceful backward-compat mapping
  if (qParam && searchInput) {
    searchInput.value = qParam;
    if (modeParam) {
      modePills.forEach(p => p.classList.toggle('active', p.dataset.mode === modeParam));
      state.currentMode = modeParam;
      if (filters && filters.renderFilterTabsForMode) {
        filters.renderFilterTabsForMode(state.currentMode, false);
      }
    }
    if (stream && stream.executeSearch) {
      stream.executeSearch(qParam, modeParam || 'clear');
    }
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSearchMain);
} else {
  initSearchMain();
}

/**
 * Resets the active search workspace (results, filters, history selection, URL params)
 * and Copilot conversation so the user can immediately start a clean new search or AI chat.
 */
function startNewSearch(focusTarget = 'search') {
  const state = window.SearchState;
  const filters = window.SearchFilters;
  const copilot = window.SearchCopilot;

  if (copilot && typeof copilot.resetChat === 'function') {
    copilot.resetChat();
  }

  if (state) {
    state.activeSessionId = null;
    state.currentSessionId = null;
    state.activeSession = null;
    state.currentQuery = '';
    state.activeFilter = 'all';
    if (typeof state.resetResults === 'function') {
      state.resetResults();
    }
  }

  if (filters) {
    if (typeof filters.renderFilterTabsForMode === 'function') {
      filters.renderFilterTabsForMode((state && state.currentMode) || 'clear', true);
    }
    if (typeof filters.syncRefineToolbarUI === 'function') {
      filters.syncRefineToolbarUI();
    }
    if (typeof filters.updateFilterCounts === 'function') {
      filters.updateFilterCounts();
    }
    if (typeof filters.updateExclusionBar === 'function') {
      filters.updateExclusionBar();
    }
  }

  document.querySelectorAll('.history-item.active').forEach(el => el.classList.remove('active'));

  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    searchInput.value = '';
  }

  const btnStop = document.getElementById('search-stop');
  if (btnStop) btnStop.style.display = 'none';

  const btnClearEngine = document.getElementById('btn-clear-engine-filter');
  if (btnClearEngine) btnClearEngine.style.display = 'none';

  const streamBar = document.getElementById('stream-live-bar');
  if (streamBar) streamBar.classList.remove('active');

  const streamBadges = document.getElementById('stream-badges');
  if (streamBadges) streamBadges.innerHTML = '';

  const streamProviderBadges = document.getElementById('stream-provider-badges');
  if (streamProviderBadges) streamProviderBadges.innerHTML = '';

  const streamProvidersSection = document.getElementById('stream-providers-section');
  if (streamProvidersSection) streamProvidersSection.style.display = 'none';

  const exclusionBar = document.getElementById('exclusion-bar');
  if (exclusionBar) {
    exclusionBar.style.display = 'none';
    exclusionBar.innerHTML = '';
  }

  const resultsCountEl = document.getElementById('results-count');
  if (resultsCountEl) resultsCountEl.innerText = 'Ready to search';

  const resultsDurationEl = document.getElementById('results-duration');
  if (resultsDurationEl) resultsDurationEl.innerText = '';

  const infiniteFooter = document.getElementById('infinite-scroll-footer');
  if (infiniteFooter) infiniteFooter.style.display = 'none';

  const paginationFooter = document.getElementById('pagination-footer');
  if (paginationFooter) paginationFooter.style.display = 'none';

  const resultsList = document.getElementById('results-list');
  if (resultsList) {
    resultsList.className = 'results-list';
    resultsList.innerHTML = `
      <div style="text-align:center; padding: 60px 20px; color: var(--text-dim);">
        <div style="font-size: 48px; margin-bottom: 16px; opacity:0.3;"><i class="fas fa-satellite-dish"></i></div>
        <div style="font-size: 16px; font-weight:600; color:var(--text-main); margin-bottom:6px;">Hecos Deep Search &amp; Intelligence</div>
        <div style="font-size: 13px; max-width: 480px; margin: 0 auto; line-height: 1.6;">
          Enter keywords to run simultaneous unfiltered multi-engine searches across the Clear Web and Tor hidden services.
        </div>
      </div>
    `;
  }

  if (window.location.search && window.history && typeof window.history.replaceState === 'function') {
    try {
      window.history.replaceState(null, '', window.location.pathname);
    } catch (_e) { }
  }

  if (focusTarget === 'copilot') {
    const copilotInput = document.getElementById('copilot-chat-input');
    if (copilotInput) copilotInput.focus();
  } else if (searchInput) {
    searchInput.focus();
  }
}

window.startNewSearch = startNewSearch;
