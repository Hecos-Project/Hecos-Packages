/**
 * search_filters.js
 * Category subtabs, moderation toggles, result filtering/pagination, and infinite scroll for Deep Search.
 * Delegates Engine/Provider chips (search_engine_chips.js) and Refine/Sort (search_refine.js).
 */
(function () {
  const state = window.SearchState;

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // ── Contextual Mode Subtabs Architecture ──────────────────────────────────
  const MODE_SUBTABS = {
    clear: [
      { id: 'all', label: 'All', icon: 'fa-layer-group' },
      { id: 'web', label: 'Web & News', icon: 'fa-newspaper' },
      { id: 'images', label: 'Images', icon: 'fa-image' },
      { id: 'videos', label: 'Videos', icon: 'fa-video' },
      { id: 'audio', label: 'Audio', icon: 'fa-music' },
      { id: 'files', label: 'Files & Dorks', icon: 'fa-file-shield' }
    ],
    dark: [
      { id: 'all', label: 'All (.onion)', icon: 'fa-user-secret' },
      { id: 'dark_directories', label: 'Wiki & Directory', icon: 'fa-compass' },
      { id: 'dark_forums', label: 'Forum & Board', icon: 'fa-comments' },
      { id: 'dark_leaks', label: 'Leaks & Dumps', icon: 'fa-shield-halved' },
      { id: 'dark_market', label: 'Markets & Services', icon: 'fa-store' }
    ],
    files: [
      { id: 'all', label: 'All Files', icon: 'fa-file-shield' },
      { id: 'files_docs', label: 'Documents (PDF/DOC)', icon: 'fa-file-pdf' },
      { id: 'files_data', label: 'Data & Sheets (XLS/CSV)', icon: 'fa-file-excel' },
      { id: 'files_archives', label: 'Archives (ZIP/ISO)', icon: 'fa-file-zipper' },
      { id: 'files_code', label: 'Code & Config', icon: 'fa-file-code' }
    ],
    osint: [
      { id: 'all', label: 'All Profiles', icon: 'fa-id-badge' },
      { id: 'osint_social', label: 'Social Networks', icon: 'fa-users' },
      { id: 'osint_dev', label: 'Dev & Tech', icon: 'fa-code-branch' },
      { id: 'osint_media', label: 'Gaming & Media', icon: 'fa-gamepad' }
    ],
    deep: [
      { id: 'all', label: 'All Aggregated', icon: 'fa-layer-group' },
      { id: 'deep_clear', label: 'Clearnet (Web)', icon: 'fa-globe' },
      { id: 'deep_dark', label: 'Darknet (.onion)', icon: 'fa-user-secret' },
      { id: 'deep_media', label: 'Media (Img/Vid/Audio)', icon: 'fa-photo-film' },
      { id: 'deep_files', label: 'Files & Documents', icon: 'fa-file-shield' }
    ]
  };

  function renderFilterTabsForMode(mode, preserveFilter = true) {
    const container = document.getElementById('filter-categories');
    if (!container) return;
    const subtabs = MODE_SUBTABS[mode] || MODE_SUBTABS.clear;
    const validIds = subtabs.map(s => s.id);

    if (!preserveFilter || !validIds.includes(state.activeFilter)) {
      state.activeFilter = 'all';
    }
    if (state.activeFilter !== 'deep_media') {
      state.mediaSubFilter = 'all';
    }

    container.innerHTML = subtabs.map(tab => `
      <button class="filter-tab ${state.activeFilter === tab.id ? 'active' : ''}" data-filter="${tab.id}" id="filter-tab-${tab.id}" onclick="window.setFilter('${tab.id}')">
        <i class="fas ${tab.icon}"></i> <span>${tab.label}</span> <span class="filter-count" id="count-${tab.id}">0</span>
      </button>
    `).join('');

    updateFilterCounts();
    syncRefineToolbarUI();
  }

  // ── Filter Controls ────────────────────────────────────────────────────────
  function setFilter(filterName, shouldRender = true, clearEngine = true) {
    state.activeFilter = filterName || 'all';
    if (state.activeFilter !== 'deep_media') {
      state.mediaSubFilter = 'all';
    }
    state.currentPage = 1;
    state.scrollRenderCount = 40;
    if (clearEngine) {
      if (state.activeEngine || state.activeProvider) {
        state.activeEngine = null;
        state.activeProvider = null;
        updateEngineChipsSelection();
      }
    }
    document.querySelectorAll('.filter-tab').forEach(tab => {
      tab.classList.toggle('active', tab.dataset.filter === state.activeFilter);
    });
    syncRefineToolbarUI();
    if (shouldRender) {
      renderCurrentView();
    }
  }

  // ── Helper Module Bridges ────────────────────────────────────────────────
  const chips = () => window.SearchEngineChips || {};
  const refine = () => window.SearchRefine || {};

  const getEngineDisplayInfo = (e) => chips().getEngineDisplayInfo?.(e);
  const extractProvider = (r) => chips().extractProvider?.(r);
  const providerMatches = (r, t) => Boolean(chips().providerMatches?.(r, t));
  const filterByProvider = (id) => chips().filterByProvider?.(id);
  const clearProviderFilter = () => chips().clearProviderFilter?.();
  const toggleExcludeProvider = (id) => chips().toggleExcludeProvider?.(id);
  const clearAllExclusions = () => chips().clearAllExclusions?.();
  const getProviderDisplayName = (id) => chips().getProviderDisplayName?.(id) || '';
  const updateExclusionBar = () => chips().updateExclusionBar?.();
  const filterByEngine = (id) => chips().filterByEngine?.(id);
  const clearEngineFilter = () => chips().clearEngineFilter?.();
  const updateEngineChipsSelection = () => chips().updateEngineChipsSelection?.();
  const toggleStreamBarCollapse = (ev, val) => chips().toggleStreamBarCollapse?.(ev, val);
  const updateCollapsedPill = () => chips().updateCollapsedPill?.();
  const renderGranularProviderChips = () => chips().renderGranularProviderChips?.();
  const engineMatches = (r, t) => Boolean(chips().engineMatches?.(r, t));

  const isTorItem = (i) => Boolean(refine().isTorItem?.(i));
  const classifyItemType = (i) => refine().classifyItemType?.(i) || 'web';
  const parseRefineQuery = (raw) => refine().parseRefineQuery?.(raw) || {};
  const hasActiveRefineFilters = (p) => Boolean(refine().hasActiveRefineFilters?.(p));
  const itemMatchesRefineQuery = (i, p) => refine().itemMatchesRefineQuery?.(i, p) ?? true;
  const SORT_DISPLAY_LABELS = (window.SearchRefine && window.SearchRefine.SORT_DISPLAY_LABELS) || {};
  const sortResultsList = (items, sb) => (refine().sortResultsList ? refine().sortResultsList(items, sb) : items);
  const syncRefineToolbarUI = () => refine().syncRefineToolbarUI?.();
  const setRefineQuery = (q, sr) => refine().setRefineQuery?.(q, sr);
  const setSortBy = (sb, sr) => refine().setSortBy?.(sb, sr);
  const setMediaSubFilter = (sf, sr) => refine().setMediaSubFilter?.(sf, sr);
  const resetPostSearchFilters = (sr) => refine().resetPostSearchFilters?.(sr);
  const initRefineToolbar = () => refine().initRefineToolbar?.();

  function toggleContentFilter() {
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
  }

  function toggleDarkFilter() {
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
  }

  function toggleLocalOnly(explicitVal) {
    if (typeof explicitVal === 'boolean') {
      state.localOnly = explicitVal;
    } else {
      state.localOnly = !state.localOnly;
    }
    const badge = document.getElementById('badge-local-only');
    const btn = document.getElementById('btn-local-only');
    if (badge) {
      if (state.localOnly) {
        badge.innerText = 'LOCAL ONLY';
        badge.className = 'badge-pill badge-ok';
        if (btn) btn.title = 'Privacy Shield: LOCAL ONLY (Strictly querying local private SearXNG and Tor onion circuits)';
      } else {
        badge.innerText = 'ALL ENGINES';
        badge.className = 'badge-pill badge-neutral';
        if (btn) btn.title = 'Privacy Shield: ALL ENGINES (Querying all active local and cloud search engines)';
      }
    }
  }

  function setSearchDepth(val) {
    let num = parseInt(val);
    if (isNaN(num) || num < 0) num = 0;
    state.searchLimit = num;
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('hecos_netsearch_depth', String(num));
      }
    } catch (e) { }
    const presetSel = document.getElementById('search-depth-presets');
    if (presetSel) {
      const matchingOpt = Array.from(presetSel.options).find(o => parseInt(o.value) === num);
      presetSel.value = matchingOpt ? matchingOpt.value : "";
    }
  }

  function setSearchDepthPreset(val) {
    const num = parseInt(val) || 0;
    state.searchLimit = num;
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('hecos_netsearch_depth', String(num));
      }
    } catch (e) { }
    const input = document.getElementById('search-depth-input');
    if (input) input.value = num;
  }

  // ── View Mode & Pagination ────────────────────────────────────────────────
  function setViewMode(mode) {
    state.viewMode = mode;
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('hecos_search_view_mode', mode);
      }
    } catch (e) { }
    updateViewModeButtons();
    renderCurrentView();
  }

  function updateViewModeButtons() {
    const btnScroll = document.getElementById('btn-view-scroll');
    const btnPaging = document.getElementById('btn-view-paging');
    if (btnScroll) btnScroll.classList.toggle('active', state.viewMode === 'scroll');
    if (btnPaging) btnPaging.classList.toggle('active', state.viewMode === 'paging');
  }

  function gotoPage(p) {
    state.currentPage = p;
    renderCurrentView();
    const list = document.getElementById('results-list');
    if (list) list.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function prevPage() {
    if (state.currentPage > 1) {
      gotoPage(state.currentPage - 1);
    }
  }

  function nextPage() {
    const filtered = getFilteredResults();
    const totalPages = Math.max(1, Math.ceil(filtered.length / state.pageSize));
    if (state.currentPage < totalPages) {
      gotoPage(state.currentPage + 1);
    }
  }

  function gotoLastPage() {
    const filtered = getFilteredResults();
    const totalPages = Math.max(1, Math.ceil(filtered.length / state.pageSize));
    gotoPage(totalPages);
  }

  function setPageSize(size) {
    state.pageSize = parseInt(size) || 25;
    state.currentPage = 1;
    renderCurrentView();
  }

  // ── Infinite Scroll Observer ───────────────────────────────────────────────
  let infiniteScrollObserver = null;
  let stageScrollListenerBound = false;

  function initInfiniteScroll() {
    const sentinel = document.getElementById('infinite-scroll-sentinel');
    const stage = document.querySelector('.search-stage');
    if (!sentinel) return;

    if (infiniteScrollObserver) {
      infiniteScrollObserver.disconnect();
    }

    // Explicitly observe scrolling relative to .search-stage scroll container
    infiniteScrollObserver = new IntersectionObserver((entries) => {
      const entry = entries[0];
      if (entry && entry.isIntersecting && state.viewMode === 'scroll') {
        const filtered = getFilteredResults();
        if (state.scrollRenderCount < filtered.length) {
          state.scrollRenderCount += 35;
          renderCurrentView();
        } else if (state.autoFetchMore && state.hasMorePages !== false && !state.isFetchingMore && !state.activeEventSource && state.currentQuery && state.results.length >= 20 && state.currentMode !== 'dark') {
          if (window.fetchMoreFromWeb) window.fetchMoreFromWeb();
        }
      }
    }, {
      root: stage || null,
      rootMargin: '350px'
    });

    infiniteScrollObserver.observe(sentinel);

    // Complementary scroll listener on .search-stage for 100% reliability
    if (stage && !stageScrollListenerBound) {
      stageScrollListenerBound = true;
      stage.addEventListener('scroll', () => {
        if (state.viewMode !== 'scroll') return;
        const remaining = stage.scrollHeight - stage.scrollTop - stage.clientHeight;
        if (remaining < 400) {
          const filtered = getFilteredResults();
          if (state.scrollRenderCount < filtered.length) {
            state.scrollRenderCount += 35;
            renderCurrentView();
          } else if (remaining < 150 && state.autoFetchMore && state.hasMorePages !== false && !state.isFetchingMore && !state.activeEventSource && state.currentQuery && state.results.length >= 20 && state.currentMode !== 'dark') {
            if (window.fetchMoreFromWeb) window.fetchMoreFromWeb();
          }
        }
      }, { passive: true });
    }
  }

  // ── Matching & Filtering Predicates ───────────────────────────────────────
  function itemMatchesFilter(item, filterId, currentMode) {
    if (!filterId || filterId === 'all') return true;

    // 1. Clear Web subtabs
    if (filterId === 'web') {
      return item.network === 'clearnet' && (
        item.category === 'web' || item.category === 'news' || item.category === 'general' ||
        item.category === 'social media' || item.category === 'it' || item.category === 'science' ||
        ['clear_ddgs', 'clear_news', 'clear_searxng'].includes(item.engine_id) ||
        (!['images', 'videos', 'audio', 'music', 'files'].includes(item.category) && !item.metadata?.extension)
      );
    }
    if (filterId === 'images') {
      return item.category === 'images' || (item.engine_id === 'media_images') || (item.engine && (item.engine.includes('image') || item.engine.includes('flickr') || item.engine.includes('deviantart') || item.engine.includes('wallhaven') || item.engine.includes('pinterest') || item.engine.includes('unsplash') || item.engine.includes('openverse'))) || (item.thumbnail_url && item.category !== 'videos');
    }
    if (filterId === 'videos') {
      return item.category === 'videos' || (item.engine_id === 'media_videos') || (item.engine && (item.engine.includes('video') || item.engine.includes('youtube') || item.engine.includes('dailymotion') || item.engine.includes('peertube') || item.engine.includes('vimeo') || item.engine.includes('rumble') || item.engine.includes('piped') || item.engine.includes('odysee') || item.engine.includes('bitchute')));
    }
    if (filterId === 'audio') {
      return item.category === 'audio' || item.category === 'music' || (item.engine_id === 'media_audio') || (item.engine && (item.engine.includes('audio') || item.engine.includes('podcast') || item.engine.includes('soundcloud') || item.engine.includes('music') || item.engine.includes('itunes') || item.engine.includes('deezer') || item.engine.includes('bandcamp') || item.engine.includes('radio') || item.engine.includes('mixcloud') || item.engine.includes('genius')));
    }
    if (filterId === 'files') {
      return item.category === 'files' || item.category === 'packages' || (item.engine_id === 'files_dorks') || (item.engine && (item.engine.includes('dork') || item.engine.includes('torrent') || item.engine.includes('piratebay') || item.engine.includes('kickass') || item.engine.includes('solidtorrent') || item.engine.includes('bt4g') || item.engine.includes('archive') || item.engine.includes('zlibrary'))) || Boolean(item.metadata && item.metadata.extension);
    }

    // 2. Dark Web subtabs
    if (filterId === 'dark_directories') {
      const text = `${item.title || ''} ${item.snippet || ''} ${item.url || ''}`.toLowerCase();
      return /wiki|directory|tordir|hidden\s*wiki|index|portal|catalog|onion\s*links|dark\s*dir|links\s*list/.test(text);
    }
    if (filterId === 'dark_forums') {
      const text = `${item.title || ''} ${item.snippet || ''} ${item.url || ''}`.toLowerCase();
      return /forum|board|chan|talk|community|dread|discuss|chat|thread|post/.test(text);
    }
    if (filterId === 'dark_leaks') {
      const text = `${item.title || ''} ${item.snippet || ''} ${item.url || ''}`.toLowerCase();
      return /leak|dump|whistle|paste|archive|breach|database|vault|hack|exfiltrat|secret|expose/.test(text);
    }
    if (filterId === 'dark_market') {
      const text = `${item.title || ''} ${item.snippet || ''} ${item.url || ''}`.toLowerCase();
      return /market|shop|store|vendor|service|escrow|crypto|exchange|wallet|drug|carding|counterfeit|buy|sell/.test(text);
    }

    // 3. File Hunter subtabs
    const ext = (item.metadata?.extension || (item.url ? item.url.split('.').pop().split(/[?#]/)[0] : '') || '').toLowerCase();
    const engLower = (item.engine || '').toLowerCase();
    if (filterId === 'files_docs') {
      return ['pdf', 'docx', 'doc', 'epub', 'odt', 'txt', 'rtf', 'djvu', 'mobi', 'md'].includes(ext)
        || /\[(pdf|doc|docx|epub|odt|djvu|txt|md)\]/i.test(item.title || '')
        || /openalex|arxiv|annas|zlibrary/.test(engLower);
    }
    if (filterId === 'files_data') {
      return ['xlsx', 'xls', 'csv', 'sql', 'json', 'jsonl', 'xml', 'sqlite', 'db', 'tsv', 'parquet'].includes(ext)
        || /\[(xlsx|csv|sql|json|jsonl|parquet|xml|sqlite)\]/i.test(item.title || '')
        || engLower.includes('huggingface')
        || item.metadata?.mediatype === 'data';
    }
    if (filterId === 'files_archives') {
      return ['zip', 'rar', '7z', 'tar', 'gz', 'tgz', 'iso', 'bz2', 'xz', 'img', 'dmg'].includes(ext)
        || /\[(zip|rar|7z|iso|tar|gz)\]/i.test(item.title || '')
        || item.metadata?.mediatype === 'software';
    }
    if (filterId === 'files_code') {
      return ['py', 'js', 'ts', 'sh', 'bat', 'c', 'cpp', 'h', 'html', 'css', 'yaml', 'yml', 'env', 'rs', 'go', 'php', 'toml', 'ini', 'whl', 'jar'].includes(ext)
        || /\[(py|js|ts|sh|yaml|rs|go|c|cpp|php)\]/i.test(item.title || '')
        || /github|npm|pypi/.test(engLower);
    }

    // 4. OSINT subtabs
    const platform = (item.metadata?.platform || item.title || '').toLowerCase();
    if (filterId === 'osint_social') {
      return /reddit|telegram|medium|pinterest|producthunt|twitter|instagram|facebook|tiktok|threads/.test(platform);
    }
    if (filterId === 'osint_dev') {
      return /github|gitlab|dev\.to|hackernews|keybase|bitbucket|stackoverflow/.test(platform);
    }
    if (filterId === 'osint_media') {
      return /steam|twitch|spotify|soundcloud|flickr|vimeo|youtube/.test(platform);
    }

    // 5. Global Sweep (Deep) subtabs
    if (filterId === 'deep_clear') {
      return !isTorItem(item) && !['images', 'videos', 'audio', 'music'].includes((item.category || '').toLowerCase());
    }
    if (filterId === 'deep_dark') {
      return isTorItem(item) || (item.engine_id && item.engine_id.startsWith('dark_'));
    }
    if (filterId === 'deep_media') {
      const mType = classifyItemType(item);
      return mType === 'images' || mType === 'videos' || mType === 'audio';
    }
    if (filterId === 'deep_files') {
      return item.category === 'files' || Boolean(item.metadata?.extension);
    }

    return true;
  }


  function updateFilterCounts() {
    const currentMode = state.currentMode || 'clear';
    const subtabs = MODE_SUBTABS[currentMode] || MODE_SUBTABS.clear;
    let baseResults = state.results || [];

    if (state.excludedProviders && state.excludedProviders.length > 0) {
      baseResults = baseResults.filter(r => {
        const rawEng = (r.engine || r.engine_id || '').trim().toLowerCase();
        return !state.excludedProviders.includes(rawEng);
      });
    }

    const parsedRefine = parseRefineQuery(state.refineQuery);
    if (hasActiveRefineFilters(parsedRefine)) {
      baseResults = baseResults.filter(r => itemMatchesRefineQuery(r, parsedRefine));
    }

    subtabs.forEach(tab => {
      let count = 0;
      if (tab.id === 'all') {
        count = baseResults.length;
      } else {
        count = baseResults.filter(r => itemMatchesFilter(r, tab.id, currentMode)).length;
      }
      const el = document.getElementById(`count-${tab.id}`);
      if (el) el.innerText = count;
      const tabEl = document.getElementById(`filter-tab-${tab.id}`);
      if (tabEl) {
        tabEl.classList.toggle('has-results', count > 0);
      }
    });

    // Keep deep_media subtype breakdown counts synchronized
    const mediaItems = baseResults.filter(r => {
      const t = classifyItemType(r);
      return t === 'videos' || t === 'images' || t === 'audio';
    });
    let videoCount = 0;
    let imageCount = 0;
    let audioCount = 0;
    mediaItems.forEach(r => {
      const t = classifyItemType(r);
      if (t === 'videos') videoCount++;
      else if (t === 'images') imageCount++;
      else if (t === 'audio') audioCount++;
    });
    const elAll = document.getElementById('media-subcount-all');
    const elVid = document.getElementById('media-subcount-videos');
    const elImg = document.getElementById('media-subcount-images');
    const elAud = document.getElementById('media-subcount-audio');
    if (elAll) elAll.innerText = mediaItems.length;
    if (elVid) elVid.innerText = videoCount;
    if (elImg) elImg.innerText = imageCount;
    if (elAud) elAud.innerText = audioCount;
  }



  function getFilteredResults() {
    let filtered = [...state.results];
    // Apply exclusions first — match on raw r.engine (same key as provider chips)
    if (state.excludedProviders && state.excludedProviders.length > 0) {
      filtered = filtered.filter(r => {
        const rawEng = (r.engine || r.engine_id || '').trim().toLowerCase();
        return !state.excludedProviders.includes(rawEng);
      });
    }
    if (state.activeProvider) {
      filtered = filtered.filter(r => providerMatches(r, state.activeProvider));
    } else if (state.activeEngine) {
      filtered = filtered.filter(r => engineMatches(r, state.activeEngine));
    }
    if (state.activeFilter && state.activeFilter !== 'all') {
      filtered = filtered.filter(r => itemMatchesFilter(r, state.activeFilter, state.currentMode));
    }
    if (state.activeFilter === 'deep_media' && state.mediaSubFilter && state.mediaSubFilter !== 'all') {
      filtered = filtered.filter(r => classifyItemType(r) === state.mediaSubFilter);
    }
    const parsedRefine = parseRefineQuery(state.refineQuery);
    if (hasActiveRefineFilters(parsedRefine)) {
      filtered = filtered.filter(r => itemMatchesRefineQuery(r, parsedRefine));
    }
    if (state.sortBy && state.sortBy !== 'default') {
      filtered = sortResultsList(filtered, state.sortBy);
    }
    return filtered;
  }


  function renderCurrentView() {
    const resultsRenderer = window.SearchResults;
    syncRefineToolbarUI();
    const filtered = getFilteredResults();
    const infiniteFooter = document.getElementById('infinite-scroll-footer');
    const infiniteStatus = document.getElementById('infinite-scroll-status');
    const paginationFooter = document.getElementById('pagination-footer');
    const resultsCountEl = document.getElementById('results-count');

    updateViewModeButtons();

    const buildMetaSuffix = () => {
      const parts = [];
      if (state.activeFilter && state.activeFilter !== 'all') {
        const sub = (state.activeFilter === 'deep_media' && state.mediaSubFilter && state.mediaSubFilter !== 'all')
          ? ` / ${state.mediaSubFilter}`
          : '';
        parts.push(`Filter: ${state.activeFilter}${sub}`);
      }
      if (state.refineQuery && state.refineQuery.trim()) {
        parts.push(`Refine: "${state.refineQuery.trim()}"`);
      }
      if (state.sortBy && state.sortBy !== 'default') {
        parts.push(`Order: ${SORT_DISPLAY_LABELS[state.sortBy] || state.sortBy}`);
      }
      let sourceText = '';
      if (state.activeProvider) {
        sourceText = ` • Provider: ${getProviderDisplayName(state.activeProvider)}`;
      } else if (state.activeEngine) {
        sourceText = ` • Engine: ${state.activeEngine}`;
      }
      return (parts.length ? ` (${parts.join(' • ')})` : '') + sourceText;
    };

    if (filtered.length === 0) {
      if (infiniteFooter) infiniteFooter.style.display = 'none';
      if (paginationFooter) paginationFooter.style.display = 'none';
      if (resultsRenderer) resultsRenderer.render([], 'results-list', state.currentMode, state.activeFilter);
      if (resultsCountEl) {
        resultsCountEl.innerText = state.results.length === 0 ? 'No results found' : `0 of ${state.results.length} results match active filter${buildMetaSuffix()}`;
      }
      return;
    }

    if (state.viewMode === 'scroll') {
      if (paginationFooter) paginationFooter.style.display = 'none';
      if (infiniteFooter) infiniteFooter.style.display = 'flex';

      const visibleCount = Math.min(state.scrollRenderCount, filtered.length);
      const visibleItems = filtered.slice(0, visibleCount);
      if (resultsRenderer) resultsRenderer.render(visibleItems, 'results-list', state.currentMode, state.activeFilter);

      if (infiniteStatus) {
        if (state.isFetchingMore) {
          infiniteStatus.innerHTML = `
            <div class="fetch-more-status loading">
              <i class="fas fa-satellite fa-spin" style="color:var(--accent-cyan);"></i>
              <span>Fetching Page ${(state.backendPage || 1) + 1} from web across engines...</span>
            </div>
          `;
        } else if (visibleCount < filtered.length) {
          infiniteStatus.innerHTML = `
            <div class="fetch-more-status in-memory">
              <i class="fas fa-circle-notch fa-spin"></i>
              <span>Showing ${visibleCount} of ${filtered.length} in-memory results (scroll down for more)</span>
            </div>
          `;
        } else {
          const nextPage = (state.backendPage || 1) + 1;
          infiniteStatus.innerHTML = `
            <div class="fetch-more-container">
              <div class="fetch-more-info">
                <i class="fas fa-check-circle" style="color:var(--accent-emerald);"></i>
                <span>All <strong>${filtered.length}</strong> results in current pool displayed.</span>
              </div>
              <div class="fetch-more-controls">
                <button type="button" class="btn-fetch-more-web" id="btn-fetch-more-web" onclick="window.fetchMoreFromWeb()">
                  <i class="fas fa-globe"></i>
                  <span>Fetch More from Web (Page ${nextPage})</span>
                </button>
                <label class="auto-fetch-toggle" title="Automatically query web engines for subsequent pages when you reach the bottom">
                  <input type="checkbox" id="chk-auto-fetch-more" ${state.autoFetchMore ? 'checked' : ''} onchange="window.toggleAutoFetchMore(this.checked)">
                  <span class="toggle-box"></span>
                  <span class="toggle-label">Auto-fetch on scroll</span>
                </label>
              </div>
            </div>
          `;
        }
      }
      initInfiniteScroll();
    } else {
      if (infiniteFooter) infiniteFooter.style.display = 'none';
      if (paginationFooter) paginationFooter.style.display = 'flex';

      const totalPages = Math.max(1, Math.ceil(filtered.length / state.pageSize));
      if (state.currentPage > totalPages) state.currentPage = totalPages;
      if (state.currentPage < 1) state.currentPage = 1;

      const startIndex = (state.currentPage - 1) * state.pageSize;
      const visibleItems = filtered.slice(startIndex, startIndex + state.pageSize);
      if (resultsRenderer) resultsRenderer.render(visibleItems, 'results-list', state.currentMode, state.activeFilter);

      const badgePage = document.getElementById('badge-page-info');
      if (badgePage) {
        badgePage.innerText = `Page ${state.currentPage} of ${totalPages} (${filtered.length} items)`;
      }

      const btnFirst = document.getElementById('btn-page-first');
      const btnPrev = document.getElementById('btn-page-prev');
      const btnNext = document.getElementById('btn-page-next');
      const btnLast = document.getElementById('btn-page-last');
      if (btnFirst) btnFirst.disabled = (state.currentPage === 1);
      if (btnPrev) btnPrev.disabled = (state.currentPage === 1);
      if (btnNext) btnNext.disabled = (state.currentPage === totalPages);
      if (btnLast) btnLast.disabled = (state.currentPage === totalPages);

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

    const metaParts = [];
    if (state.activeFilter && state.activeFilter !== 'all') {
      const sub = (state.activeFilter === 'deep_media' && state.mediaSubFilter && state.mediaSubFilter !== 'all')
        ? ` / ${state.mediaSubFilter}`
        : '';
      metaParts.push(`Filter: ${state.activeFilter}${sub}`);
    }
    if (state.refineQuery && state.refineQuery.trim()) {
      metaParts.push(`Refine: "${state.refineQuery.trim()}"`);
    }
    if (state.sortBy && state.sortBy !== 'default') {
      metaParts.push(`Order: ${SORT_DISPLAY_LABELS[state.sortBy] || state.sortBy}`);
    }
    let sourceText = '';
    if (state.activeProvider) {
      sourceText = ` • Provider: ${getProviderDisplayName(state.activeProvider)}`;
    } else if (state.activeEngine) {
      sourceText = ` • Engine: ${state.activeEngine}`;
    }
    const suffixText = (metaParts.length ? ` (${metaParts.join(' • ')})` : '') + sourceText;
    if (resultsCountEl) {
      resultsCountEl.innerText = `${filtered.length} of ${state.results.length} results found${suffixText}`;
    }
  }

  // ── Export Interface and Global Aliases ─────────────────────────────────────
  window.SearchFilters = {
    MODE_SUBTABS,
    renderFilterTabsForMode,
    setFilter,
    filterByEngine,
    clearEngineFilter,
    updateFilterCounts,
    updateEngineChipsSelection,
    toggleContentFilter,
    toggleDarkFilter,
    toggleLocalOnly,
    setSearchDepth,
    setSearchDepthPreset,
    setViewMode,
    updateViewModeButtons,
    gotoPage,
    prevPage,
    nextPage,
    gotoLastPage,
    setPageSize,
    initInfiniteScroll,
    getFilteredResults,
    renderCurrentView,
    itemMatchesFilter,
    classifyItemType,
    isTorItem,
    parseRefineQuery,
    itemMatchesRefineQuery,
    sortResultsList,
    setRefineQuery,
    setSortBy,
    setMediaSubFilter,
    resetPostSearchFilters,
    syncRefineToolbarUI,
    engineMatches,
    extractProvider,
    providerMatches,
    filterByProvider,
    clearProviderFilter,
    toggleExcludeProvider,
    clearAllExclusions,
    updateExclusionBar,
    renderGranularProviderChips,
    getEngineDisplayInfo,
    toggleStreamBarCollapse,
    updateCollapsedPill
  };

  // Global window bindings for backward compatibility and HTML onclick handlers
  window.setFilter = setFilter;
  window.setRefineQuery = setRefineQuery;
  window.setResultsSort = setSortBy;
  window.setMediaSubFilter = setMediaSubFilter;
  window.resetPostSearchFilters = resetPostSearchFilters;
  window.filterByEngine = filterByEngine;
  window.clearEngineFilter = clearEngineFilter;
  window.engineMatches = engineMatches;
  window.filterByProvider = filterByProvider;
  window.clearProviderFilter = clearProviderFilter;
  window.toggleExcludeProvider = toggleExcludeProvider;
  window.clearAllExclusions = clearAllExclusions;
  window.updateExclusionBar = updateExclusionBar;
  window.renderGranularProviderChips = renderGranularProviderChips;
  window.toggleStreamBarCollapse = toggleStreamBarCollapse;
  window.updateCollapsedPill = updateCollapsedPill;
  window.updateFilterCounts = updateFilterCounts;
  window.renderCurrentView = renderCurrentView;
  window.toggleContentFilter = toggleContentFilter;
  window.toggleDarkFilter = toggleDarkFilter;
  window.toggleLocalOnly = toggleLocalOnly;
  window.setSearchDepth = setSearchDepth;
  window.setSearchDepthPreset = setSearchDepthPreset;
  window.setViewMode = setViewMode;
  window.gotoPage = gotoPage;
  window.prevPage = prevPage;
  window.nextPage = nextPage;
  window.gotoLastPage = gotoLastPage;
  function toggleAutoFetchMore(val) {
    state.autoFetchMore = Boolean(val);
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('hecos_netsearch_autofetch', state.autoFetchMore ? 'true' : 'false');
      }
    } catch (e) { }
  }
  window.toggleAutoFetchMore = toggleAutoFetchMore;
  window.setPageSize = setPageSize;
  // Restore initial collapse state and bind post-search refine/sort toolbar
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      if (state.isStreamCollapsed) toggleStreamBarCollapse(null, true);
      initRefineToolbar();
    });
  } else {
    if (state.isStreamCollapsed) toggleStreamBarCollapse(null, true);
    initRefineToolbar();
  }
})();

