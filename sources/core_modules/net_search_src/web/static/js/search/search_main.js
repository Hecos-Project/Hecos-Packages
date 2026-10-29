/**
 * search_main.js
 * Main initialization and controller for Hecos Deep Search page.
 * Manages streaming, persistent engine filter buttons, category tabs, and component statuses.
 */
function initSearchMain() {
  const state = window.SearchState;
  const api = window.SearchAPI;
  const resultsRenderer = window.SearchResults;
  const copilot = window.SearchCopilot;

  const searchInput = document.getElementById('search-input');
  const searchBtn = document.getElementById('search-submit');
  const streamBar = document.getElementById('stream-live-bar');
  const streamBadges = document.getElementById('stream-badges');
  const streamStatusIcon = document.getElementById('stream-status-icon');
  const streamStatusText = document.getElementById('stream-status-text');
  const btnClearEngine = document.getElementById('btn-clear-engine-filter');
  const resultsCountEl = document.getElementById('results-count');
  const resultsDurationEl = document.getElementById('results-duration');
  const historyListEl = document.getElementById('history-list');
  const torStatusPill = document.getElementById('tor-status-pill');
  const torDot = document.getElementById('tor-dot');
  const torLabel = document.getElementById('tor-label');

  // ── Mode Switchers ─────────────────────────────────────────────────────────
  if (api && api.getConfig) {
    api.getConfig().then(data => {
      if (data && data.ok && data.config) {
        const tor = data.config.tor || {};
        window.currentTorAction = tor.onion_action || 'hecos_viewer';
        window.torBrowserPath = tor.tor_browser_path || '';
      }
    }).catch(() => {});
  }

  const modePills = document.querySelectorAll('.mode-pill');
  const activeInitialPill = document.querySelector('.mode-pill.active');
  if (activeInitialPill && activeInitialPill.dataset.mode) {
    state.currentMode = activeInitialPill.dataset.mode;
  }
  const activeInitialFilter = document.querySelector('.filter-tab.active');
  if (activeInitialFilter && activeInitialFilter.dataset.filter) {
    state.activeFilter = activeInitialFilter.dataset.filter;
  }

  modePills.forEach(pill => {
    pill.addEventListener('click', () => {
      modePills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      state.currentMode = pill.dataset.mode;
      
      // Auto-align category filter tab if relevant
      if (state.currentMode === 'media') {
        window.setFilter('images', false);
      } else if (state.currentMode === 'files') {
        window.setFilter('files', false);
      } else if (state.currentMode === 'dark') {
        window.setFilter('dark', false);
      } else if (state.currentMode === 'osint') {
        window.setFilter('osint', false);
      } else {
        window.setFilter('all', false);
      }

      if (state.currentQuery) {
        executeSearch(state.currentQuery, state.currentMode);
      }
    });
  });

  // ── Filter Methods ─────────────────────────────────────────────────────────
  window.setFilter = function(filterName, shouldRender = true, clearEngine = true) {
    state.activeFilter = filterName || 'all';
    // If user explicitly clicks a category tab, clear any specific engine filter
    if (clearEngine && state.activeEngine) {
      state.activeEngine = null;
      updateEngineChipsSelection();
    }
    document.querySelectorAll('.filter-tab').forEach(tab => {
      tab.classList.toggle('active', tab.dataset.filter === state.activeFilter);
    });
    if (shouldRender) {
      renderCurrentView();
    }
  };

  window.filterByEngine = function(engineId) {
    if (state.activeEngine === engineId) {
      state.activeEngine = null; // Toggle off
    } else {
      state.activeEngine = engineId;
      // Reset category tab to 'all' so all engine results are immediately visible, without clearing activeEngine
      setFilter('all', false, false);
    }
    updateEngineChipsSelection();
    renderCurrentView();
  };

  window.clearEngineFilter = function() {
    state.activeEngine = null;
    updateEngineChipsSelection();
    renderCurrentView();
  };

  window.updateFilterCounts = updateFilterCounts;
  window.renderCurrentView = renderCurrentView;

  // ── Moderation & Uncensored Filter Controls ────────────────────────────────
  window.toggleContentFilter = function() {
    state.safeSearch = !state.safeSearch;
    const badge = document.getElementById('badge-content-filter');
    const btn = document.getElementById('btn-content-filter');
    if (badge) {
      if (state.safeSearch) {
        badge.innerText = 'ON';
        badge.className = 'badge-pill badge-warn';
        if (btn) btn.title = 'Content Filter: ON (SafeSearch Moderate active)';
      } else {
        badge.innerText = 'OFF';
        badge.className = 'badge-pill badge-neutral';
        if (btn) btn.title = 'Content Filter: OFF (Unfiltered / Raw Search)';
      }
    }
  };

  window.toggleDarkFilter = function() {
    state.darkBypass = !state.darkBypass;
    const badge = document.getElementById('badge-dark-filter');
    const btn = document.getElementById('btn-dark-filter');
    if (badge) {
      if (state.darkBypass) {
        badge.innerText = 'BYPASSED';
        badge.className = 'badge-pill badge-ok';
        if (btn) btn.title = 'DarkWeb Filters: BYPASSED (100% Uncensored / Blacklists disabled)';
      } else {
        badge.innerText = 'FILTERED';
        badge.className = 'badge-pill badge-neutral';
        if (btn) btn.title = 'DarkWeb Filters: ACTIVE (Ahmia standard moderation)';
      }
    }
  };

  window.setSearchDepth = function(val) {
    let num = parseInt(val);
    if (isNaN(num) || num < 0) num = 0;
    state.searchLimit = num;
    const presetSel = document.getElementById('search-depth-presets');
    if (presetSel) {
      const matchingOpt = Array.from(presetSel.options).find(o => parseInt(o.value) === num);
      if (matchingOpt) {
        presetSel.value = matchingOpt.value;
      } else {
        presetSel.value = "";
      }
    }
  };

  window.setSearchDepthPreset = function(val) {
    const num = parseInt(val) || 0;
    state.searchLimit = num;
    const input = document.getElementById('search-depth-input');
    if (input) input.value = num;
  };

  // ── View Mode & Pagination Controls ────────────────────────────────────────
  window.setViewMode = function(mode) {
    state.viewMode = mode;
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('hecos_search_view_mode', mode);
      }
    } catch (e) {}
    updateViewModeButtons();
    renderCurrentView();
  };

  function updateViewModeButtons() {
    const btnScroll = document.getElementById('btn-view-scroll');
    const btnPaging = document.getElementById('btn-view-paging');
    if (btnScroll) btnScroll.classList.toggle('active', state.viewMode === 'scroll');
    if (btnPaging) btnPaging.classList.toggle('active', state.viewMode === 'paging');
  }

  window.gotoPage = function(p) {
    state.currentPage = p;
    renderCurrentView();
    const list = document.getElementById('results-list');
    if (list) list.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  window.prevPage = function() {
    if (state.currentPage > 1) {
      window.gotoPage(state.currentPage - 1);
    }
  };

  window.nextPage = function() {
    const filtered = getFilteredResults();
    const totalPages = Math.max(1, Math.ceil(filtered.length / state.pageSize));
    if (state.currentPage < totalPages) {
      window.gotoPage(state.currentPage + 1);
    }
  };

  window.gotoLastPage = function() {
    const filtered = getFilteredResults();
    const totalPages = Math.max(1, Math.ceil(filtered.length / state.pageSize));
    window.gotoPage(totalPages);
  };

  window.setPageSize = function(size) {
    state.pageSize = parseInt(size) || 25;
    state.currentPage = 1;
    renderCurrentView();
  };

  // ── Stop Search Stream ─────────────────────────────────────────────────────
  window.stopSearch = function() {
    if (state.activeEventSource) {
      state.activeEventSource.close();
      state.activeEventSource = null;
    }
    const btnStop = document.getElementById('search-stop');
    if (btnStop) btnStop.style.display = 'none';

    if (streamStatusIcon) {
      streamStatusIcon.className = 'fas fa-stop-circle';
      streamStatusIcon.style.color = 'var(--accent-amber, #f59e0b)';
    }
    if (streamStatusText) {
      streamStatusText.innerText = `Search halted by user (${state.results.length} total results collected):`;
    }
    updateFilterCounts();
    renderCurrentView();
    copilot.update(state.results, state.currentQuery, state.currentMode);
  };

  // ── Infinite Scroll Observer ───────────────────────────────────────────────
  let infiniteScrollObserver = null;
  function initInfiniteScroll() {
    const sentinel = document.getElementById('infinite-scroll-sentinel');
    if (!sentinel) return;

    if (infiniteScrollObserver) {
      infiniteScrollObserver.disconnect();
    }

    infiniteScrollObserver = new IntersectionObserver((entries) => {
      const entry = entries[0];
      if (entry && entry.isIntersecting && state.viewMode === 'scroll') {
        const filtered = getFilteredResults();
        if (state.scrollRenderCount < filtered.length) {
          state.scrollRenderCount += 35;
          renderCurrentView();
        }
      }
    }, { rootMargin: '300px' });

    infiniteScrollObserver.observe(sentinel);
  }

  function updateEngineChipsSelection() {
    if (btnClearEngine) {
      btnClearEngine.style.display = state.activeEngine ? 'inline-flex' : 'none';
    }
    document.querySelectorAll('.engine-chip').forEach(chip => {
      const eng = chip.dataset.engine || chip.id.replace('chip-', '');
      chip.classList.toggle('selected-engine', eng === state.activeEngine);
    });
  }

  function updateFilterCounts() {
    const results = state.results || [];
    const counts = {
      all: results.length,
      images: results.filter(r => r.category === 'images' || (r.engine_id === 'media_images') || (r.engine && r.engine.includes('image')) || (r.thumbnail_url && r.category !== 'videos')).length,
      videos: results.filter(r => r.category === 'videos' || (r.engine_id === 'media_videos') || (r.engine && (r.engine.includes('video') || r.engine.includes('youtube') || r.engine.includes('yt-dlp')))).length,
      audio: results.filter(r => r.category === 'audio' || (r.engine_id === 'media_audio') || (r.engine && (r.engine.includes('audio') || r.engine.includes('podcast')))).length,
      files: results.filter(r => r.category === 'files' || (r.engine_id === 'files_dorks') || (r.engine && r.engine.includes('dork')) || (r.metadata && r.metadata.extension)).length,
      dark: results.filter(r => 
        r.network === 'tor' || 
        r.category === 'onion' || 
        r.category === 'dark' || 
        (r.engine_id && r.engine_id.startsWith('dark_')) ||
        (r.url && r.url.includes('.onion')) ||
        (r.engine && (r.engine.includes('tor') || r.engine.includes('onion') || r.engine.includes('ahmia') || r.engine.includes('torch') || r.engine.includes('haystak') || r.engine.includes('onionland') || r.engine.includes('excavator') || r.engine.includes('phobos') || r.engine.includes('tor66') || r.engine.includes('danieltore') || r.engine.includes('custom')))
      ).length,
      osint: results.filter(r => r.category === 'osint' || (r.engine_id === 'osint_sherlock') || (r.engine && r.engine.includes('sherlock'))).length
    };

    for (const [key, count] of Object.entries(counts)) {
      const el = document.getElementById(`count-${key}`);
      if (el) el.innerText = count;
      const tab = document.getElementById(`filter-tab-${key}`);
      if (tab) {
        tab.classList.toggle('has-results', count > 0);
      }
    }
  }

  function engineMatches(r, target) {
    if (!target) return true;
    target = target.toLowerCase();
    const engId = (r.engine_id || r.metadata?.engine_id || '').toLowerCase();
    const eng = (r.engine || '').toLowerCase();
    const cat = (r.category || '').toLowerCase();

    if (engId === target || eng === target) return true;
    if (r.metadata?.engine_ids && r.metadata.engine_ids.includes(target)) return true;

    // Clean prefix comparison
    const cleanTarget = target.replace(/^(clear_|media_|dark_|osint_)/, '');
    const cleanEng = eng.replace(/^(ddgs:|rss:|torch:|ahmia:|haystak:|osint:)/, '');

    if (cleanTarget === cleanEng) return true;
    if (eng.includes(cleanTarget) || cleanEng.includes(cleanTarget)) return true;
    if (engId && (engId.includes(cleanTarget) || cleanTarget.includes(engId))) return true;

    // Special category / engine mappings
    if (target === 'clear_news' && (cat === 'news' || eng.includes('news'))) return true;
    if (target === 'clear_ddgs' && (eng.includes('ddgs') || eng.includes('clearnet'))) return true;
    if (target === 'media_images' && (cat === 'images' || eng.includes('image') || eng.includes('commons'))) return true;
    if (target === 'media_videos' && (cat === 'videos' || eng.includes('video') || eng.includes('yt-dlp') || eng.includes('youtube') || eng.includes('archive_org:video'))) return true;
    if (target === 'media_audio' && (cat === 'audio' || eng.includes('audio') || eng.includes('podcast') || eng.includes('archive_org:audio'))) return true;
    if (target === 'files_dorks' && (cat === 'files' || eng.includes('dork') || eng.includes('file') || eng.includes('archive_org:texts'))) return true;
    if (target === 'clear_searxng' && (eng.includes('searx') || eng.includes('searxng'))) return true;
    if (target === 'osint_sherlock' && (cat === 'osint' || eng.includes('sherlock'))) return true;
    if (target.startsWith('dark_')) {
      const darkName = target.replace(/^dark_/, '');
      if (engId === target || eng === darkName || eng.includes(darkName) || engId.includes(darkName)) return true;
      if (r.network === 'tor' || (r.url && r.url.includes('.onion'))) return true;
    }

    return false;
  }

  function getFilteredResults() {
    let filtered = [...state.results];

    // 1. Engine Filter
    if (state.activeEngine) {
      filtered = filtered.filter(r => engineMatches(r, state.activeEngine));
    }

    // 2. Category Tab Filter
    if (state.activeFilter && state.activeFilter !== 'all') {
      if (state.activeFilter === 'images') {
        filtered = filtered.filter(r => r.category === 'images' || (r.engine_id === 'media_images') || (r.engine && r.engine.includes('image')) || (r.thumbnail_url && r.category !== 'videos'));
      } else if (state.activeFilter === 'videos') {
        filtered = filtered.filter(r => r.category === 'videos' || (r.engine_id === 'media_videos') || (r.engine && (r.engine.includes('video') || r.engine.includes('youtube') || r.engine.includes('yt-dlp'))));
      } else if (state.activeFilter === 'audio') {
        filtered = filtered.filter(r => r.category === 'audio' || (r.engine_id === 'media_audio') || (r.engine && (r.engine.includes('audio') || r.engine.includes('podcast'))));
      } else if (state.activeFilter === 'files') {
        filtered = filtered.filter(r => r.category === 'files' || (r.engine_id === 'files_dorks') || (r.engine && r.engine.includes('dork')) || (r.metadata && r.metadata.extension));
      } else if (state.activeFilter === 'dark') {
        filtered = filtered.filter(r => 
          r.network === 'tor' || 
          r.category === 'onion' || 
          r.category === 'dark' || 
          (r.engine_id && r.engine_id.startsWith('dark_')) ||
          (r.url && r.url.includes('.onion')) ||
          (r.engine && (r.engine.includes('tor') || r.engine.includes('onion') || r.engine.includes('ahmia') || r.engine.includes('torch') || r.engine.includes('haystak') || r.engine.includes('onionland') || r.engine.includes('excavator') || r.engine.includes('phobos') || r.engine.includes('tor66') || r.engine.includes('danieltore') || r.engine.includes('custom')))
        );
      } else if (state.activeFilter === 'osint') {
        filtered = filtered.filter(r => r.category === 'osint' || (r.engine_id === 'osint_sherlock') || (r.engine && r.engine.includes('sherlock')));
      }
    }
    return filtered;
  }

  function renderCurrentView() {
    const filtered = getFilteredResults();
    const infiniteFooter = document.getElementById('infinite-scroll-footer');
    const infiniteStatus = document.getElementById('infinite-scroll-status');
    const paginationFooter = document.getElementById('pagination-footer');

    updateViewModeButtons();

    // If empty results
    if (filtered.length === 0) {
      if (infiniteFooter) infiniteFooter.style.display = 'none';
      if (paginationFooter) paginationFooter.style.display = 'none';
      resultsRenderer.render([], 'results-list', state.currentMode, state.activeFilter);
      const filterText = state.activeFilter !== 'all' ? ` (Filter: ${state.activeFilter})` : '';
      const engineText = state.activeEngine ? ` • Engine: ${state.activeEngine}` : '';
      resultsCountEl.innerText = state.results.length === 0 ? 'No results found' : `0 of ${state.results.length} results match filter${filterText}${engineText}`;
      return;
    }

    if (state.viewMode === 'scroll') {
      // ── Infinite Scroll Mode ──────────────────────────────────────────────
      if (paginationFooter) paginationFooter.style.display = 'none';
      if (infiniteFooter) infiniteFooter.style.display = 'flex';

      const visibleCount = Math.min(state.scrollRenderCount, filtered.length);
      const visibleItems = filtered.slice(0, visibleCount);
      resultsRenderer.render(visibleItems, 'results-list', state.currentMode, state.activeFilter);

      if (infiniteStatus) {
        if (visibleCount < filtered.length) {
          infiniteStatus.innerHTML = `<i class="fas fa-circle-notch fa-spin"></i> Showing ${visibleCount} of ${filtered.length} results (scroll down for more)`;
        } else {
          infiniteStatus.innerHTML = `<i class="fas fa-check-circle" style="color:var(--accent-emerald);"></i> All ${filtered.length} results loaded`;
        }
      }
    } else {
      // ── Pagination Mode ───────────────────────────────────────────────────
      if (infiniteFooter) infiniteFooter.style.display = 'none';
      if (paginationFooter) paginationFooter.style.display = 'flex';

      const totalPages = Math.max(1, Math.ceil(filtered.length / state.pageSize));
      if (state.currentPage > totalPages) state.currentPage = totalPages;
      if (state.currentPage < 1) state.currentPage = 1;

      const startIndex = (state.currentPage - 1) * state.pageSize;
      const visibleItems = filtered.slice(startIndex, startIndex + state.pageSize);
      resultsRenderer.render(visibleItems, 'results-list', state.currentMode, state.activeFilter);

      // Update badge page info
      const badgePage = document.getElementById('badge-page-info');
      if (badgePage) {
        badgePage.innerText = `Page ${state.currentPage} of ${totalPages} (${filtered.length} items)`;
      }

      // Update nav buttons
      const btnFirst = document.getElementById('btn-page-first');
      const btnPrev = document.getElementById('btn-page-prev');
      const btnNext = document.getElementById('btn-page-next');
      const btnLast = document.getElementById('btn-page-last');
      if (btnFirst) btnFirst.disabled = (state.currentPage === 1);
      if (btnPrev) btnPrev.disabled = (state.currentPage === 1);
      if (btnNext) btnNext.disabled = (state.currentPage === totalPages);
      if (btnLast) btnLast.disabled = (state.currentPage === totalPages);

      // Build smart page numbers list
      const pagePills = document.getElementById('page-pills');
      if (pagePills) {
        pagePills.innerHTML = '';
        const maxPagesToShow = 5;
        let startPage = Math.max(1, state.currentPage - Math.floor(maxPagesToShow / 2));
        let endPage = Math.min(totalPages, startPage + maxPagesToShow - 1);
        if (endPage - startPage < maxPagesToShow - 1) {
          startPage = Math.max(1, endPage - maxPagesToShow + 1);
        }

        function createPageBtn(p) {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'page-num-btn' + (p === state.currentPage ? ' active' : '');
          btn.innerText = p;
          btn.onclick = () => window.gotoPage(p);
          return btn;
        }

        if (startPage > 1) {
          pagePills.appendChild(createPageBtn(1));
          if (startPage > 2) {
            const dots = document.createElement('span');
            dots.innerText = '…';
            dots.style.cssText = 'color:var(--muted); padding:0 3px; font-size:12px;';
            pagePills.appendChild(dots);
          }
        }

        for (let p = startPage; p <= endPage; p++) {
          pagePills.appendChild(createPageBtn(p));
        }

        if (endPage < totalPages) {
          if (endPage < totalPages - 1) {
            const dots = document.createElement('span');
            dots.innerText = '…';
            dots.style.cssText = 'color:var(--muted); padding:0 3px; font-size:12px;';
            pagePills.appendChild(dots);
          }
          pagePills.appendChild(createPageBtn(totalPages));
        }
      }
    }

    // Update Counter text
    const filterText = state.activeFilter !== 'all' ? ` (Filter: ${state.activeFilter})` : '';
    const engineText = state.activeEngine ? ` • Engine: ${state.activeEngine}` : '';
    resultsCountEl.innerText = `${filtered.length} of ${state.results.length} results found${filterText}${engineText}`;
  }

  // ── Search Execution with Streaming ────────────────────────────────────────
  function executeSearch(queryStr, mode = 'clear') {
    if (!queryStr || !queryStr.trim()) return;
    queryStr = queryStr.trim();
    state.currentQuery = queryStr;
    state.currentMode = mode;

    // Ensure filter tab matches mode if it's a specialized mode and current filter is mismatched
    if (mode === 'dark' && state.activeFilter !== 'dark') {
      window.setFilter('dark', false, true);
    } else if (mode === 'media' && !['images', 'videos', 'audio'].includes(state.activeFilter)) {
      window.setFilter('images', false, true);
    } else if (mode === 'files' && state.activeFilter !== 'files') {
      window.setFilter('files', false, true);
    } else if (mode === 'osint' && state.activeFilter !== 'osint') {
      window.setFilter('osint', false, true);
    } else if ((mode === 'clear' || mode === 'deep') && state.activeFilter === 'dark') {
      window.setFilter('all', false, true);
    }

    state.resetResults();
    updateFilterCounts();

    resultsRenderer.render([], 'results-list', mode, state.activeFilter);
    resultsCountEl.innerText = 'Searching across engines...';
    resultsDurationEl.innerText = '';
    
    // Setup persistent engine stream bar
    streamBadges.innerHTML = '';
    streamBar.classList.add('active');
    if (streamStatusIcon) {
      streamStatusIcon.className = 'fas fa-satellite fa-spin';
      streamStatusIcon.style.color = 'var(--accent-cyan)';
    }
    if (streamStatusText) {
      streamStatusText.innerText = 'Real-time engine query:';
    }
    if (btnClearEngine) {
      btnClearEngine.style.display = 'none';
    }

    // Show Stop button
    const btnStop = document.getElementById('search-stop');
    if (btnStop) btnStop.style.display = 'inline-flex';

    const params = {
      query: queryStr,
      mode: mode,
      limit: state.searchLimit,
      safe_search: state.safeSearch,
      dark_bypass: state.darkBypass !== false
    };

    state.activeEventSource = api.queryStream(
      params,
      // On Engine Event
      (evt) => {
        if (evt.type === 'start') {
          streamBadges.innerHTML = evt.engines.map(e => `
            <button class="engine-chip running" id="chip-${e}" data-engine="${e}" onclick="window.filterByEngine('${e}')" title="Running engine: ${e}">
              <i class="fas fa-spinner fa-spin"></i> ${e}
            </button>
          `).join('');
        } else if (evt.type === 'engine_done') {
          const newCnt = evt.new_results ? evt.new_results.length : 0;
          state.engineStats[evt.engine] = {
            count: newCnt,
            duration_ms: evt.duration_ms,
            status: 'done'
          };

          let chip = document.getElementById(`chip-${evt.engine}`);
          if (!chip) {
            chip = document.createElement('button');
            chip.id = `chip-${evt.engine}`;
            chip.dataset.engine = evt.engine;
            streamBadges.appendChild(chip);
          }
          chip.className = 'engine-chip done' + (state.activeEngine === evt.engine ? ' selected-engine' : '');
          chip.dataset.engine = evt.engine;
          chip.title = `Filter results by ${evt.engine} (${newCnt} found)`;
          chip.innerHTML = `<i class="fas fa-check"></i> ${evt.engine} <span class="chip-count">(${newCnt})</span>`;
          chip.onclick = (e) => {
            if (e) { e.preventDefault(); e.stopPropagation(); }
            window.filterByEngine(evt.engine);
          };

          if (evt.new_results && evt.new_results.length > 0) {
            state.addResults(evt.new_results, evt.engine);
            updateFilterCounts();
            renderCurrentView();
            copilot.update(state.results, queryStr, mode);
          }
        } else if (evt.type === 'fallback') {
          streamBadges.innerHTML += `
            <button class="engine-chip" style="border-color:var(--accent-purple); color:var(--accent-purple);" title="Tor Fallback">
              <i class="fas fa-random"></i> Tor Fallback
            </button>
          `;
        } else if (evt.type === 'error') {
          const btnStop = document.getElementById('search-stop');
          if (btnStop) btnStop.style.display = 'none';

          resultsCountEl.innerText = 'Search unavailable';
          const container = document.getElementById('results-list');
          if (container) {
            container.innerHTML = `
              <div style="text-align:center; padding: 48px 20px; color: var(--accent-rose, #f43f5e);">
                <div style="font-size: 36px; margin-bottom: 12px;"><i class="fas fa-exclamation-triangle"></i></div>
                <div style="font-size: 15px; font-weight:600; margin-bottom:6px;">Search Error</div>
                <div style="font-size: 13px; max-width: 500px; margin: 0 auto; color:var(--text-muted); line-height:1.6;">${escapeHtml(evt.error || 'Requested search mode is currently unavailable.')}</div>
              </div>
            `;
          }
        }
      },
      // On Complete
      (completeEvt) => {
        const btnStop = document.getElementById('search-stop');
        if (btnStop) btnStop.style.display = 'none';

        // PERSISTENCE: Do NOT hide streamBar! It stays visible with clickable engine filter buttons!
        streamBar.classList.add('active');
        if (streamStatusIcon) {
          streamStatusIcon.className = 'fas fa-circle-check';
          streamStatusIcon.style.color = 'var(--accent-emerald)';
        }
        if (streamStatusText) {
          streamStatusText.innerText = 'Engines completed (click to filter):';
        }
        resultsDurationEl.innerText = `(${completeEvt.duration_ms}ms)`;
        updateFilterCounts();
        renderCurrentView();
        copilot.update(state.results, queryStr, mode);
        loadHistory();
      },
      // On Error
      (err) => {
        const btnStop = document.getElementById('search-stop');
        if (btnStop) btnStop.style.display = 'none';
        console.error('[SearchMain] Stream error:', err);
      }
    );
  }

  // ── Form Submit ────────────────────────────────────────────────────────────
  searchBtn.addEventListener('click', () => {
    executeSearch(searchInput.value, state.currentMode);
  });

  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      executeSearch(searchInput.value, state.currentMode);
    }
  });

  // ── Keyboard Shortcuts ─────────────────────────────────────────────────────
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey && e.key === 'k') || (e.key === '/' && document.activeElement !== searchInput)) {
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
    }
    if (e.key === 'Escape') {
      closeAllModals();
    }
  });

  // ── History List ───────────────────────────────────────────────────────────
  async function loadHistory() {
    try {
      const res = await api.getSessions(30);
      if (res.ok && res.sessions) {
        historyListEl.innerHTML = res.sessions.map(s => `
          <div class="history-item ${s.id === state.activeSessionId ? 'active' : ''}" onclick="loadSession('${s.id}')">
            <div class="history-query">${escapeHtml(s.query)}</div>
            <div class="history-meta">
              <span>${s.mode.toUpperCase()}</span>
              <span>•</span>
              <span>${s.total_results} res.</span>
              <span>•</span>
              <span>${s.created_at.split(' ')[1] || ''}</span>
            </div>
          </div>
        `).join('');
      }
    } catch (e) {
      console.error('[SearchMain] Failed to load history:', e);
    }
  }

  window.loadSession = async function(sessionId) {
    try {
      const res = await api.getSessionDetail(sessionId);
      if (res.ok && res.session) {
        const s = res.session;
        state.activeSessionId = s.id;
        state.currentQuery = s.query;
        state.currentMode = s.mode;
        state.results = s.results || [];
        state.activeEngine = null;
        searchInput.value = s.query;

        // Set active mode pill
        modePills.forEach(p => {
          p.classList.toggle('active', p.dataset.mode === s.mode);
        });

        // Rebuild persistent engine chips from saved session
        const engineCounts = {};
        state.results.forEach(r => {
          const eng = r.engine_id || r.metadata?.engine_id || r.engine || 'web';
          engineCounts[eng] = (engineCounts[eng] || 0) + 1;
        });

        streamBar.classList.add('active');
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

        streamBadges.innerHTML = Object.entries(engineCounts).map(([eng, count]) => `
          <button class="engine-chip done" id="chip-${eng}" data-engine="${eng}" onclick="window.filterByEngine('${eng}')" title="Filter by ${eng} (${count} results)">
            <i class="fas fa-check"></i> ${eng} <span class="chip-count">(${count})</span>
          </button>
        `).join('');

        updateFilterCounts();
        renderCurrentView();
        copilot.update(state.results, s.query, s.mode);

        document.querySelectorAll('.history-item').forEach(it => it.classList.remove('active'));
      }
    } catch (e) {
      console.error('[SearchMain] Load session detail error:', e);
    }
  };

  // ── Tor Status & Refresh ───────────────────────────────────────────────────
  async function refreshTorStatus() {
    try {
      const res = await api.getTorStatus();
      state.torOnline = res.ok;
      state.torIp = res.ip;
      state.torPort = res.port;

      if (res.ok) {
        if (torDot) {
          torDot.className = 'dot val-ok';
          torDot.style.background = 'var(--green)';
        }
        torLabel.innerText = `Tor Online (${res.port || 9055})`;
        if (torStatusPill) {
          torStatusPill.className = 'badge-pill badge-ok';
          torStatusPill.title = `Tor IP: ${res.ip} (Port ${res.port})`;
        }
      } else {
        if (torDot) {
          torDot.className = 'dot';
          torDot.style.background = 'var(--muted)';
        }
        torLabel.innerText = 'Tor Offline';
        if (torStatusPill) {
          torStatusPill.className = 'badge-pill badge-neutral';
          torStatusPill.title = res.error || 'Tor daemon not running';
        }
      }
    } catch (e) {
      if (torDot) {
        torDot.className = 'dot';
        torDot.style.background = 'var(--muted)';
      }
      torLabel.innerText = 'Tor Offline';
      if (torStatusPill) {
        torStatusPill.className = 'badge-pill badge-neutral';
      }
    }
  }

  // ── Modals & Components Management ─────────────────────────────────────────
  const componentsModal = document.getElementById('components-modal');
  const readerModal = document.getElementById('page-reader-modal');

  window.openComponentsModal = async function() {
    componentsModal.classList.add('open');
    const tabEndp = document.getElementById('modal-tab-endpoints');
    if (tabEndp && tabEndp.classList.contains('active')) {
      loadEndpointsList();
    } else {
      loadComponentsList();
    }
  };

  window.switchComponentsModalTab = function(tab) {
    const tabComp = document.getElementById('modal-tab-components');
    const tabEndp = document.getElementById('modal-tab-endpoints');
    const listComp = document.getElementById('components-list');
    const listEndp = document.getElementById('endpoints-list');
    if (!tabComp || !tabEndp || !listComp || !listEndp) return;

    if (tab === 'endpoints') {
      tabComp.classList.remove('active');
      tabEndp.classList.add('active');
      listComp.style.display = 'none';
      listEndp.style.display = 'flex';
      loadEndpointsList();
    } else {
      tabEndp.classList.remove('active');
      tabComp.classList.add('active');
      listEndp.style.display = 'none';
      listComp.style.display = 'flex';
      loadComponentsList();
    }
  };

  window.closeAllModals = function() {
    if (componentsModal) componentsModal.classList.remove('open');
    if (readerModal) readerModal.classList.remove('open');
  };

  async function loadComponentsList() {
    const listEl = document.getElementById('components-list');
    if (!listEl) return;
    listEl.innerHTML = '<div style="text-align:center; padding:20px;"><i class="fas fa-spinner fa-spin"></i> Loading components...</div>';

    try {
      const res = await api.getComponents();
      if (res.ok && res.components) {
        listEl.innerHTML = res.components.map(c => {
          const isSearxng = c.id === 'searxng';
          return `
            <div class="component-item">
              <div class="component-info">
                <h4>${escapeHtml(c.name)} <span style="font-size:10px; opacity:0.6;">(${c.category})</span></h4>
                <p>${escapeHtml(c.description)}</p>
                <div style="margin-top:6px; font-size:11px;">
                  Status: <strong style="color:${c.is_installed ? 'var(--accent-emerald)' : 'var(--text-dim)'};">${c.is_installed ? (isSearxng ? 'Installed (Pure Python)' : 'Installed') : 'Not installed'}</strong>
                  ${c.is_running ? ` • <span style="color:var(--accent-cyan); font-weight:600;"><i class="fas fa-circle" style="font-size:8px;"></i> Running${isSearxng ? ' (127.0.0.1:8888)' : ''}</span>` : ''}
                </div>
                ${isSearxng ? `
                  <div style="margin-top:5px; font-size:11px; color:var(--accent-cyan); line-height:1.4;">
                    <i class="fas fa-bolt"></i> Pure-Python native meta-search (Docker-free). Auto-starts on demand.
                  </div>
                ` : ''}
              </div>
              <div style="display:flex; gap:8px; align-items:center;">
                ${!c.is_installed ? `
                  <button class="btn btn-sm btn-primary" onclick="installComponent('${c.id}')">
                    <i class="fas fa-download"></i> Install
                  </button>
                ` : `
                  ${c.category === 'tor' || c.id === 'searxng' ? `
                    <button class="btn btn-sm btn-secondary" onclick="${c.is_running ? `stopComponent('${c.id}')` : `startComponent('${c.id}')`}">
                      <i class="fas fa-${c.is_running ? 'stop' : 'play'}"></i> ${c.is_running ? 'Stop' : 'Start'}
                    </button>
                  ` : ''}
                  <button class="btn btn-sm btn-danger" onclick="uninstallComponent('${c.id}')" title="Uninstall">
                    <i class="fas fa-trash"></i>
                  </button>
                `}
              </div>
            </div>
          `;
        }).join('');
      }
    } catch (e) {
      listEl.innerHTML = `<div style="color:var(--accent-rose); padding:20px;">Error loading components: ${e.message}</div>`;
    }
  }

  window.installComponent = async function(id) {
    alert(`Starting installation of ${id}... Please wait.`);
    const res = await api.installComponent(id);
    if (res.ok) {
      alert(`Installation of ${id} completed.`);
      loadComponentsList();
      refreshTorStatus();
    } else {
      alert(`Installation error: ${res.message || res.error}`);
    }
  };

  window.uninstallComponent = async function(id) {
    if (!confirm(`Are you sure you want to uninstall ${id}?`)) return;
    const res = await api.uninstallComponent(id);
    alert(res.ok ? 'Component uninstalled.' : `Error: ${res.message}`);
    loadComponentsList();
    refreshTorStatus();
  };

  window.startComponent = async function(id) {
    const res = await api.startComponent(id);
    alert(res.ok ? 'Component started successfully.' : `Error: ${res.message}`);
    loadComponentsList();
    refreshTorStatus();
  };

  window.stopComponent = async function(id) {
    const res = await api.stopComponent(id);
    alert(res.ok ? 'Component stopped.' : `Error: ${res.message}`);
    loadComponentsList();
    refreshTorStatus();
  };

  window.torNewCircuit = async function() {
    const res = await api.torNewCircuit();
    alert(res.ok ? 'New Tor identity requested successfully!' : `Error: ${res.message}`);
    refreshTorStatus();
  };

  // ── Resilient Endpoints & Search Nodes UI ──────────────────────────────────
  async function loadEndpointsList() {
    const el = document.getElementById('endpoints-list');
    if (!el) return;
    el.innerHTML = '<div style="text-align:center; padding:20px;"><i class="fas fa-spinner fa-spin"></i> Loading endpoints configuration...</div>';

    try {
      const [res, cfgRes] = await Promise.all([api.getEndpoints(), api.getConfig()]);
      if (!res.ok || !res.endpoints) {
        el.innerHTML = '<div style="color:var(--accent-rose); padding:20px;">Failed to load endpoints configuration.</div>';
        return;
      }
      const ep = res.endpoints;
      const torCfg = (cfgRes && cfgRes.ok && cfgRes.config) ? (cfgRes.config.tor || {}) : {};
      const sx = ep.searxng || {};
      const ahmia = ep.dark_ahmia || {};
      const torch = ep.dark_torch || {};
      const haystak = ep.dark_haystak || {};
      const onionland = ep.dark_onionland || {};
      const excavator = ep.dark_excavator || {};
      const phobos = ep.dark_phobos || {};
      const tor66 = ep.dark_tor66 || {};
      const daniel = ep.dark_danieltore || {};
      const archives = ep.archives || {};
      const customTorEngines = Array.isArray(ep.custom_onion_engines) ? ep.custom_onion_engines : [];
      const customNodes = Array.isArray(ep.custom_nodes) ? ep.custom_nodes : [];
      const fallbacks = Array.isArray(sx.fallbacks) ? sx.fallbacks : [];
      const SE = window.SearchEndpoints;

      el.innerHTML = `
        <div style="font-size:12px; color:var(--muted); margin-bottom:14px; line-height:1.5;">
          <i class="fas fa-info-circle" style="color:var(--accent-cyan);"></i>
          Configure dynamic search engine endpoints, Tor .onion links, and resilient SearXNG fallback nodes. Edit Name, Protocol, Host/Domain, Port, and Path freely. All changes persist automatically to Hecos configuration.
        </div>

        <!-- 1. SearXNG Instance (Local Daemon) -->
        <div class="endpoint-group">
          <div class="endpoint-group-header">
            <span class="endpoint-group-title"><i class="fas fa-server" style="color:var(--accent-cyan);"></i> SearXNG Primary Daemon</span>
            <span class="badge-pill badge-neutral">Pure Python / Docker-Free</span>
          </div>
          <p style="font-size:11px; color:var(--muted); margin-bottom:8px;">Primary local or remote SearXNG meta-search instance.</p>
          <div id="endp-searxng-local-wrap"></div>
        </div>

        <!-- 2. SearXNG Resilient Fallbacks (Mirror Pool) -->
        <div class="endpoint-group">
          <div class="endpoint-group-header">
            <span class="endpoint-group-title"><i class="fas fa-network-wired" style="color:var(--accent-cyan);"></i> SearXNG Fallback Instances (Mirror Pool)</span>
            <button type="button" class="btn btn-sm btn-secondary" style="border-radius:6px; font-size:11px; padding:4px 10px;" onclick="window.addSearxngFallbackNode()">
              <i class="fas fa-plus"></i> Add Fallback Node
            </button>
          </div>
          <p style="font-size:11px; color:var(--muted); margin-bottom:8px;">Pre-configured resilient SearXNG mirrors with auto-failover if the local daemon is unavailable or rate-limited. Fully editable names, protocols, and ports.</p>
          <div id="endp-searxng-fallbacks-wrap" style="display:flex; flex-direction:column; gap:10px;"></div>
        </div>

        <!-- 3. Dark Web (.onion & Gateways) Built-in & Custom Engines -->
        <div class="endpoint-group">
          <div class="endpoint-group-header">
            <span class="endpoint-group-title"><i class="fas fa-user-secret" style="color:var(--accent-purple, #a855f7);"></i> Dark Web (.onion) Search Engines</span>
            <button type="button" class="btn btn-sm btn-secondary" style="border-radius:6px; font-size:11px; padding:4px 10px;" onclick="window.addCustomTorEngineNode()">
              <i class="fas fa-plus"></i> Add Tor Engine
            </button>
          </div>
          <p style="font-size:11px; color:var(--muted); margin-bottom:8px;">Configure onion search engines and clearnet gateways routed through SOCKS5h Tor proxy. Names, hosts, ports, and protocols are 100% customizable.</p>
          <div id="endp-tor-engines-wrap" style="display:flex; flex-direction:column; gap:10px;"></div>
        </div>

        <!-- Dark Web (.onion) Link Action -->
        <div class="endpoint-group">
          <div class="endpoint-group-header">
            <span class="endpoint-group-title"><i class="fas fa-external-link-alt" style="color:var(--accent-purple, #a855f7);"></i> Dark Web (.onion) Link Action</span>
            <span class="badge-pill badge-neutral">Tor SOCKS5h Routing</span>
          </div>
          <p style="font-size:11px; color:var(--muted); margin-bottom:8px;">
            Choose how .onion links are opened in standard browsers. Hecos can render them cross-browser in the Live Viewer or launch desktop Tor Browser.
          </p>
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:10px;">
            <div>
              <label style="font-size:11px; color:var(--muted); display:block; margin-bottom:3px; font-weight:600;">Default Action</label>
              <select id="endp-tor-onion-action" class="endpoint-proto-select" style="width:100%;">
                <option value="hecos_viewer" ${(torCfg.onion_action === 'hecos_viewer' || !torCfg.onion_action) ? 'selected' : ''}>Hecos Tor Live Viewer (In-App Cross-Browser)</option>
                <option value="tor_browser" ${torCfg.onion_action === 'tor_browser' ? 'selected' : ''}>External Tor Browser</option>
                <option value="ask_menu" ${torCfg.onion_action === 'ask_menu' ? 'selected' : ''}>Always Show Choices Menu</option>
              </select>
            </div>
            <div>
              <label style="font-size:11px; color:var(--muted); display:block; margin-bottom:3px; font-weight:600;">Tor Browser Executable Path</label>
              <div style="display:flex; gap:6px;">
                <input type="text" id="endp-tor-browser-path" class="endpoint-host-input" value="${escapeHtml(torCfg.tor_browser_path || '')}" placeholder="C:\\Users\\...\\Tor Browser\\Browser\\firefox.exe" style="flex:1;">
                <button type="button" class="btn btn-sm btn-secondary" style="border-radius:6px; font-size:11px; padding:4px 10px;" onclick="window.autoDetectTorBrowser()">
                  <i class="fas fa-search"></i> Detect
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 4. Open Archives & Media Discovery -->
        <div class="endpoint-group">
          <div class="endpoint-group-header">
            <span class="endpoint-group-title"><i class="fas fa-archive" style="color:var(--accent-amber, #f59e0b);"></i> Open Archives &amp; Repositories</span>
          </div>
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:10px;">
            <div>
              <label style="font-size:11px; color:var(--muted); display:block; margin-bottom:3px; font-weight:600;">Internet Archive API Endpoint</label>
              <input type="text" id="endp-archive-org" class="endpoint-input" value="${escapeHtml(archives.archive_org || 'https://archive.org/advancedsearch.php')}">
            </div>
            <div>
              <label style="font-size:11px; color:var(--muted); display:block; margin-bottom:3px; font-weight:600;">Wikimedia Commons API Endpoint</label>
              <input type="text" id="endp-wikimedia" class="endpoint-input" value="${escapeHtml(archives.wikimedia_commons || 'https://commons.wikimedia.org/w/api.php')}">
            </div>
          </div>
        </div>

        <!-- 5. Custom Search Nodes -->
        <div class="endpoint-group">
          <div class="endpoint-group-header">
            <span class="endpoint-group-title"><i class="fas fa-cube" style="color:var(--accent-cyan);"></i> Custom Search Nodes</span>
            <button type="button" class="btn btn-sm btn-secondary" style="border-radius:6px; font-size:11px; padding:4px 10px;" onclick="window.addCustomSearchNode()">
              <i class="fas fa-plus"></i> Add Custom Node
            </button>
          </div>
          <p style="font-size:11px; color:var(--muted); margin-bottom:8px;">Add custom SearXNG or compatible instances with customizable protocol and port to the search pool.</p>
          <div id="endp-custom-nodes-wrap" style="display:flex; flex-direction:column; gap:10px;"></div>
        </div>

        <!-- Bottom Action Bar -->
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:16px; padding-top:12px; border-top:1px solid var(--border);">
          <button type="button" class="btn btn-secondary" style="border-radius:6px; padding:8px 16px;" onclick="window.resetEndpointsFromUI()">
            <i class="fas fa-undo"></i> Reset to Defaults
          </button>
          <button type="button" class="btn btn-primary" style="border-radius:6px; padding:8px 18px;" onclick="window.saveEndpointsFromUI()">
            <i class="fas fa-save"></i> Save Endpoints
          </button>
        </div>
      `;

      if (!SE) return;

      // Populate SearXNG local daemon
      const localWrap = document.getElementById('endp-searxng-local-wrap');
      if (localWrap) {
        const localInst = sx.local_instance || SE.decomposeUrl(sx.local_url || 'http://127.0.0.1:8888', 'SearXNG Local Daemon', 'http');
        localInst.id = 'endp_sx_local';
        localWrap.innerHTML = SE.renderCard(localInst, {
          typeBadge: 'LOCAL DAEMON',
          isDeletable: false,
          key: 'searxng_local',
          category: 'searxng'
        });
      }

      // Populate SearXNG fallbacks
      const fbWrap = document.getElementById('endp-searxng-fallbacks-wrap');
      if (fbWrap) {
        fallbacks.forEach(f => {
          const item = (typeof f === 'string') ? SE.decomposeUrl(f, '', 'https') : f;
          SE.addEndpoint('endp-searxng-fallbacks-wrap', item, {
            typeBadge: 'SEARXNG MIRROR',
            isDeletable: true,
            key: 'searxng_fallback',
            category: 'searxng'
          });
        });
      }

      // Populate Dark Web Built-in Engines
      const torWrap = document.getElementById('endp-tor-engines-wrap');
      if (torWrap) {
        const torEnginesDef = [
          {
            key: 'ahmia_onion',
            badge: 'TOR ONION',
            data: ahmia.onion || SE.decomposeUrl(ahmia.onion_url || 'http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion', 'Ahmia (.onion)', 'http')
          },
          {
            key: 'ahmia_clear',
            badge: 'CLEARNET GATEWAY',
            data: ahmia.clearnet || SE.decomposeUrl(ahmia.clearnet_url || 'https://ahmia.fi', 'Ahmia Clearnet Gateway', 'https')
          },
          {
            key: 'ddg_onion',
            badge: 'TOR ONION',
            data: torch.ddg || SE.decomposeUrl(torch.ddg_onion || 'https://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion/html/', 'DuckDuckGo (.onion)', 'https')
          },
          {
            key: 'torch_onion',
            badge: 'TOR ONION',
            data: torch.torch || SE.decomposeUrl(torch.torch_onion || 'http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion/cgi-bin/omega/omega', 'Torch (.onion)', 'http')
          },
          {
            key: 'haystak_onion',
            badge: 'TOR ONION',
            data: haystak.onion || SE.decomposeUrl(haystak.onion_url || 'http://haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion', 'Haystak (.onion)', 'http')
          },
          {
            key: 'onionland_clear',
            badge: 'CLEARNET GATEWAY',
            data: onionland.clearnet || SE.decomposeUrl(onionland.clearnet_url || 'https://onionsearchengine.com/search.php', 'Onion Search Engine', 'https')
          },
          {
            key: 'excavator_onion',
            badge: 'TOR ONION',
            data: excavator.onion || SE.decomposeUrl(excavator.onion_url || 'http://2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion/search', 'Excavator (.onion)', 'http')
          },
          {
            key: 'phobos_onion',
            badge: 'TOR ONION',
            data: phobos.onion || SE.decomposeUrl(phobos.onion_url || 'http://phobosxilamwcg75xt22id7aywkzol6q6rfl2flipcqoc4e4ahima5id.onion/search', 'Phobos (.onion)', 'http')
          },
          {
            key: 'tor66_onion',
            badge: 'TOR ONION',
            data: tor66.onion || SE.decomposeUrl(tor66.onion_url || 'http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search', 'Tor66 (.onion)', 'http')
          },
          {
            key: 'daniel_onion',
            badge: 'TOR ONION',
            data: daniel.onion || SE.decomposeUrl(daniel.onion_url || 'http://tordexu73joywapk2txdr54jed4imqledpcvcuf75qsas2gwdgksvnyd.onion/search', 'TorDex Directory (.onion)', 'http')
          }
        ];

        torEnginesDef.forEach(ted => {
          ted.data.id = 'endp_' + ted.key;
          torWrap.insertAdjacentHTML('beforeend', SE.renderCard(ted.data, {
            typeBadge: ted.badge,
            isDeletable: false,
            key: ted.key,
            category: 'tor'
          }));
        });

        // Add custom tor engines
        customTorEngines.forEach(cte => {
          SE.addEndpoint('endp-tor-engines-wrap', cte, {
            typeBadge: 'CUSTOM TOR',
            isDeletable: true,
            key: 'custom_tor',
            category: 'tor'
          });
        });
      }

      // Populate Custom Nodes
      const customWrap = document.getElementById('endp-custom-nodes-wrap');
      if (customWrap) {
        customNodes.forEach(cn => {
          SE.addEndpoint('endp-custom-nodes-wrap', cn, {
            typeBadge: 'CUSTOM NODE',
            isDeletable: true,
            key: 'custom_node',
            category: 'custom'
          });
        });
      }

    } catch (err) {
      el.innerHTML = `<div style="color:var(--accent-rose); padding:20px;">Error loading endpoints: ${err.message}</div>`;
    }
  }

  window.addSearxngFallbackNode = function() {
    if (!window.SearchEndpoints) return;
    window.SearchEndpoints.addEndpoint('endp-searxng-fallbacks-wrap', {
      name: 'Custom Fallback Node',
      protocol: 'https',
      host: '',
      port: '',
      path: '',
      enabled: true
    }, {
      typeBadge: 'SEARXNG MIRROR',
      isDeletable: true,
      key: 'searxng_fallback',
      category: 'searxng'
    });
  };
  window.addSearxngFallback = window.addSearxngFallbackNode;

  window.addCustomTorEngineNode = function() {
    if (!window.SearchEndpoints) return;
    window.SearchEndpoints.addEndpoint('endp-tor-engines-wrap', {
      name: 'Custom Onion Engine',
      protocol: 'http',
      host: '',
      port: '',
      path: '/search?q={q}',
      enabled: true
    }, {
      typeBadge: 'CUSTOM TOR',
      isDeletable: true,
      key: 'custom_tor',
      category: 'tor'
    });
  };
  window.addCustomTorEngine = window.addCustomTorEngineNode;

  window.addCustomSearchNode = function() {
    if (!window.SearchEndpoints) return;
    window.SearchEndpoints.addEndpoint('endp-custom-nodes-wrap', {
      name: 'Custom Search Node',
      protocol: 'https',
      host: '',
      port: '',
      path: '',
      enabled: true
    }, {
      typeBadge: 'CUSTOM NODE',
      isDeletable: true,
      key: 'custom_node',
      category: 'custom'
    });
  };

  window.saveEndpointsFromUI = async function() {
    const SE = window.SearchEndpoints;
    if (!SE) return;

    // SearXNG local
    const localCard = document.querySelector('#endp-searxng-local-wrap .endpoint-card');
    const localItem = SE.collectCard(localCard);

    // SearXNG fallbacks
    const fallbackCards = document.querySelectorAll('#endp-searxng-fallbacks-wrap .endpoint-card');
    const fallbacks = [];
    fallbackCards.forEach(c => {
      const item = SE.collectCard(c);
      if (item && (item.host || item.url)) fallbacks.push(item);
    });

    // Built-in Tor engines by key
    function getTorItem(key) {
      const card = document.querySelector(`#endp-tor-engines-wrap .endpoint-card[data-key="${key}"]`);
      return SE.collectCard(card);
    }

    const ahmiaOnion = getTorItem('ahmia_onion');
    const ahmiaClear = getTorItem('ahmia_clear');
    const ddgOnion = getTorItem('ddg_onion');
    const torchOnion = getTorItem('torch_onion');
    const haystakOnion = getTorItem('haystak_onion');
    const onionlandClear = getTorItem('onionland_clear');
    const excavatorOnion = getTorItem('excavator_onion');
    const phobosOnion = getTorItem('phobos_onion');
    const tor66Onion = getTorItem('tor66_onion');
    const danielOnion = getTorItem('daniel_onion');

    // Custom Tor engines
    const customTorCards = document.querySelectorAll('#endp-tor-engines-wrap .endpoint-card[data-key="custom_tor"]');
    const customTorEngines = [];
    customTorCards.forEach(c => {
      const item = SE.collectCard(c);
      if (item && (item.host || item.url)) {
        customTorEngines.push({
          name: item.name || 'Custom Onion',
          onion_url: item.url,
          protocol: item.protocol,
          host: item.host,
          port: item.port,
          path: item.path,
          search_template: item.path || '/search?q={q}',
          enabled: item.enabled,
          use_api_key: item.use_api_key,
          api_key: item.api_key
        });
      }
    });

    // Custom Nodes
    const customNodeCards = document.querySelectorAll('#endp-custom-nodes-wrap .endpoint-card');
    const customNodes = [];
    customNodeCards.forEach(c => {
      const item = SE.collectCard(c);
      if (item && (item.host || item.url)) customNodes.push(item);
    });

    // Archives
    const archiveOrg = (document.getElementById('endp-archive-org')?.value || '').trim();
    const wikimedia = (document.getElementById('endp-wikimedia')?.value || '').trim();

    const payload = {
      searxng: {
        local_instance: localItem,
        local_url: localItem?.url || 'http://127.0.0.1:8888',
        fallbacks: fallbacks
      },
      dark_ahmia: {
        onion: ahmiaOnion,
        onion_url: ahmiaOnion?.url || '',
        clearnet: ahmiaClear,
        clearnet_url: ahmiaClear?.url || ''
      },
      dark_torch: {
        torch: torchOnion,
        torch_onion: torchOnion?.url || '',
        ddg: ddgOnion,
        ddg_onion: ddgOnion?.url || ''
      },
      dark_haystak: {
        onion: haystakOnion,
        onion_url: haystakOnion?.url || ''
      },
      dark_onionland: {
        clearnet: onionlandClear,
        clearnet_url: onionlandClear?.url || ''
      },
      dark_excavator: {
        onion: excavatorOnion,
        onion_url: excavatorOnion?.url || ''
      },
      dark_phobos: {
        onion: phobosOnion,
        onion_url: phobosOnion?.url || ''
      },
      dark_tor66: {
        onion: tor66Onion,
        onion_url: tor66Onion?.url || ''
      },
      dark_danieltore: {
        onion: danielOnion,
        onion_url: danielOnion?.url || ''
      },
      archives: {
        archive_org: archiveOrg || 'https://archive.org/advancedsearch.php',
        wikimedia_commons: wikimedia || 'https://commons.wikimedia.org/w/api.php'
      },
      custom_nodes: customNodes,
      custom_onion_engines: customTorEngines
    };

    try {
      const res = await api.saveEndpoints(payload);
      if (res.ok) {
        const onionAction = document.getElementById('endp-tor-onion-action')?.value || 'hecos_viewer';
        const torBrowserPath = (document.getElementById('endp-tor-browser-path')?.value || '').trim();
        window.currentTorAction = onionAction;
        window.torBrowserPath = torBrowserPath;
        try {
          await api.saveConfig({
            tor: {
              onion_action: onionAction,
              tor_browser_path: torBrowserPath
            }
          });
        } catch (errCfg) {
          console.warn('Failed to save tor config from endpoints modal:', errCfg);
        }

        alert('Search endpoints & Dark Web settings saved successfully!');
        loadEndpointsList();
      } else {
        alert('Failed to save endpoints: ' + (res.error || 'Unknown error'));
      }
    } catch (e) {
      alert('Error saving endpoints: ' + e.message);
    }
  };

  window.autoDetectTorBrowser = async function() {
    try {
      const res = await window.SearchAPI.detectTorBrowser();
      if (res.ok && res.path) {
        const inp = document.getElementById('endp-tor-browser-path');
        if (inp) inp.value = res.path;
        window.torBrowserPath = res.path;
        alert('Detected Tor Browser:\n' + res.path);
      } else {
        alert('Tor Browser not automatically detected in standard folders. You can enter the path to firefox.exe manually.');
      }
    } catch (e) {
      alert('Error detecting Tor Browser: ' + e.message);
    }
  };

  window.resetEndpointsFromUI = async function() {
    if (!confirm('Are you sure you want to reset all endpoints and fallbacks to default values?')) return;
    try {
      const res = await api.resetEndpoints();
      if (res.ok) {
        alert('Endpoints reset to factory defaults.');
        loadEndpointsList();
      } else {
        alert('Failed to reset: ' + (res.error || 'Unknown error'));
      }
    } catch (e) {
      alert('Error resetting endpoints: ' + e.message);
    }
  };

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ── Initial Boot ───────────────────────────────────────────────────────────
  updateViewModeButtons();
  initInfiniteScroll();
  loadHistory();
  refreshTorStatus();

  // If query passed in URL parameter on load
  const urlParams = new URLSearchParams(window.location.search);
  const qParam = urlParams.get('q');
  const modeParam = urlParams.get('mode');
  if (qParam) {
    searchInput.value = qParam;
    if (modeParam) {
      modePills.forEach(p => p.classList.toggle('active', p.dataset.mode === modeParam));
      state.currentMode = modeParam;
      if (modeParam === 'media') {
        window.setFilter('images', false);
      } else if (modeParam === 'files') {
        window.setFilter('files', false);
      } else if (modeParam === 'dark') {
        window.setFilter('dark', false);
      } else if (modeParam === 'osint') {
        window.setFilter('osint', false);
      } else {
        window.setFilter('all', false);
      }
    }
    executeSearch(qParam, modeParam || 'clear');
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSearchMain);
} else {
  initSearchMain();
}
