/**
 * stream_hunter_ui.js
 * Main UI controller for Hecos NetSearch "Stream Hunter" (Live TV, Radio, Webcams & Raw Streams).
 * Integrates with SearchState, SearchStream, CyberMapBus, and VLC Desktop / In-Page Player Dock.
 */
(function () {
  let currentSubfilter = 'all';
  let currentCountry = 'ALL';
  let currentStreams = [];
  let isSearching = false;
  let vlcCapabilities = { has_vlc_desktop: true, has_libvlc: true };
  let _previewMgr = null;
  let _actions = null;

  function _getPreviewMgr() {
    if (!_previewMgr && window.StreamPreviewManager) {
      _previewMgr = window.StreamPreviewManager.create({ findStreamById });
    }
    return _previewMgr;
  }

  function _getVisibleStreams() {
    return currentStreams.filter(st => {
      if (currentSubfilter !== 'all' && st.category !== currentSubfilter) return false;
      if (currentCountry !== 'ALL' && st.country !== currentCountry) return false;
      return true;
    });
  }

  function buildSnapshotUrl(st, force = false) {
    const pm = _getPreviewMgr();
    return pm ? pm.buildSnapshotUrl(st, force) : '';
  }

  function refreshPreviewById(id, force = true, ev = null) {
    _getPreviewMgr()?.refreshPreviewById(id, force, ev);
  }

  function setupPreviewObserver() {
    _getPreviewMgr()?.setupPreviewObserver(currentStreams);
  }

  function toggleAutoPreviewRefresh(btnEl) {
    _getPreviewMgr()?.toggleAutoPreviewRefresh(btnEl);
  }

  function openHubConfig() {
    window.location.href = '/hecos/config/ui?tab=streams#netsearch';
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function fetchCapabilities() {
    fetch('/api/hsearch/streams/capabilities')
      .then(r => r.json())
      .then(data => {
        if (data && data.ok) {
          vlcCapabilities = data;
        }
      })
      .catch(() => {});
  }

  function syncToolbarVisibility(mode) {
    const toolbar = document.getElementById('stream-hunter-toolbar');
    const filterBar = document.getElementById('search-filter-bar');
    const streamLiveBar = document.getElementById('stream-live-bar');
    const infiniteFooter = document.getElementById('infinite-scroll-footer');
    const paginationFooter = document.getElementById('pagination-footer');
    const isStreamsMode = (mode === 'streams');

    if (toolbar) {
      toolbar.classList.toggle('is-visible', isStreamsMode);
    }
    if (filterBar) {
      filterBar.style.display = isStreamsMode ? 'none' : '';
    }
    if (isStreamsMode) {
      if (streamLiveBar) streamLiveBar.classList.remove('active');
      if (infiniteFooter) infiniteFooter.style.display = 'none';
      if (paginationFooter) paginationFooter.style.display = 'none';
    }
    if (window.StreamRemoteController && typeof window.StreamRemoteController.setRemoteModeVisible === 'function') {
      window.StreamRemoteController.setRemoteModeVisible(isStreamsMode);
    }
  }

  function getCategoryIcon(cat) {
    const c = (cat || '').toLowerCase();
    if (c === 'tv') return 'fa-tv';
    if (c === 'radio') return 'fa-broadcast-tower';
    if (c === 'webcam') return 'fa-video';
    return 'fa-satellite-dish';
  }

  function renderStatusPill(st) {
    if (st.is_live === true) {
      const lat = st.latency_ms ? ` (${st.latency_ms}ms)` : '';
      return `<span class="sh-pill sh-pill-live" id="sh-status-${escapeHtml(st.id)}">● LIVE${escapeHtml(lat)}</span>`;
    }
    if (st.is_live === false) {
      return `<span class="sh-pill sh-pill-offline" id="sh-status-${escapeHtml(st.id)}">● OFFLINE</span>`;
    }
    return `<span class="sh-pill sh-pill-ready" id="sh-status-${escapeHtml(st.id)}">● STREAM</span>`;
  }

  function updateSubfilterCounts(counts) {
    if (!counts) return;
    ['all', 'tv', 'radio', 'webcam', 'raw'].forEach(k => {
      const el = document.getElementById(`sh-count-${k}`);
      if (el && counts[k] !== undefined) {
        el.textContent = counts[k];
      }
    });
  }

  function renderStreamsGrid(streams) {
    const container = document.getElementById('results-list');
    const countEl = document.getElementById('results-count');
    const infiniteFooter = document.getElementById('infinite-scroll-footer');
    const paginationFooter = document.getElementById('pagination-footer');
    if (infiniteFooter) infiniteFooter.style.display = 'none';
    if (paginationFooter) paginationFooter.style.display = 'none';
    if (!container) return;

    const filtered = (streams || []).filter(st => {
      if (currentSubfilter && currentSubfilter !== 'all') {
        if ((st.category || 'raw') !== currentSubfilter) return false;
      }
      if (currentCountry && currentCountry !== 'ALL') {
        if ((st.country || 'INT').toUpperCase() !== currentCountry) return false;
      }
      return true;
    });

    if (countEl) {
      countEl.textContent = `${filtered.length} Live Streams ready (TV, Radio, Webcams & Raw Feeds)`;
    }

    if (filtered.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding: 48px 20px; color: var(--text-muted, #94a3b8);">
          <div style="font-size: 34px; margin-bottom: 10px; color:#38bdf8;"><i class="fas fa-tower-broadcast"></i></div>
          <div style="font-size: 15px; font-weight: 700; color:#e2e8f0; margin-bottom: 6px;">No matching live streams found</div>
          <div style="font-size: 12.5px;">Try searching for a country (<b>italia</b>, <b>usa</b>), genre (<b>news</b>, <b>rock</b>, <b>jazz</b>, <b>space</b>), or paste a direct <code>.m3u8</code> / <code>.m3u</code> URL.</div>
        </div>
      `;
      return;
    }

    const cardsHtml = filtered.map((st, idx) => {
      const iconClass = getCategoryIcon(st.category);
      const logoHtml = st.logo
        ? `<img src="${escapeHtml(st.logo)}" alt="" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline-block';"><i class="fas ${iconClass}" style="display:none;"></i>`
        : `<i class="fas ${iconClass}"></i>`;

      const metaParts = [];
      if (st.resolution) metaParts.push(st.resolution);
      if (st.codec) metaParts.push(st.codec);
      if (st.bitrate && st.bitrate > 0) metaParts.push(`${st.bitrate} kbps`);
      const metaLabel = metaParts.join(' • ');

      const isM3uPlaylist = (st.protocol === 'M3U' || st.protocol === 'PLS' || (st.stream_url || '').toLowerCase().endsWith('.m3u'));
      const snapUrl = buildSnapshotUrl(st, false);
      const chNum = idx + 1;
      const chBadge = chNum < 10 ? `CH 0${chNum}` : `CH ${chNum}`;

      return `
        <div class="sh-card" id="sh-card-${escapeHtml(st.id)}" data-stream-id="${escapeHtml(st.id)}" data-stream-url="${escapeHtml(st.stream_url)}" data-idx="${idx}" data-ch-num="${chNum}">
          <div>
            <div class="sh-preview-top-bar">
              <button type="button" class="sh-preview-live-btn" id="sh-prev-ts-${escapeHtml(st.id)}" onclick="window.StreamHunterUI.playInAppById('${escapeHtml(st.id)}')" title="Open live preview stream in Hecos Dock">
                ● LIVE PREVIEW
              </button>
              <button type="button" class="sh-preview-refresh-btn" id="sh-prev-btn-${escapeHtml(st.id)}" onclick="window.StreamHunterUI.refreshPreviewById('${escapeHtml(st.id)}', true, event)" title="Refresh live preview frame now">
                <i class="fas fa-sync-alt"></i> Frame
              </button>
            </div>
            <div class="sh-card-preview" onclick="window.StreamHunterUI.playInAppById('${escapeHtml(st.id)}')" title="Click to play live stream in Hecos Dock">
              <img class="sh-preview-img" id="sh-prev-img-${escapeHtml(st.id)}" src="${escapeHtml(snapUrl)}" alt="${escapeHtml(st.title)}" loading="lazy">
              <div class="sh-preview-play-overlay">
                <div class="sh-preview-play-circle"><i class="fas fa-play"></i></div>
              </div>
            </div>
            <div class="sh-card-header" style="margin-top:9px;">
              <div class="sh-card-icon">${logoHtml}</div>
              <div class="sh-card-title-wrap">
                <div class="sh-card-title"><span class="sh-ch-badge" title="Channel ${chNum} — Press ${chNum} on TV Remote or Keyboard">${chBadge}</span>${escapeHtml(st.title)}</div>
                <div class="sh-card-pills">
                  ${renderStatusPill(st)}
                  <span class="sh-pill sh-pill-proto">${escapeHtml(st.protocol || 'HLS')}</span>
                  <span class="sh-pill sh-pill-country">${escapeHtml(st.country || 'INT')}</span>
                  ${metaLabel ? `<span class="sh-pill sh-pill-meta" id="sh-meta-${escapeHtml(st.id)}">${escapeHtml(metaLabel)}</span>` : `<span class="sh-pill sh-pill-meta" id="sh-meta-${escapeHtml(st.id)}" style="display:none;"></span>`}
                </div>
              </div>
            </div>
            <div class="sh-card-url" style="margin-top:8px;" title="${escapeHtml(st.stream_url)}">${escapeHtml(st.stream_url)}</div>
            <div class="sh-card-nowplaying" id="sh-np-${escapeHtml(st.id)}" style="${st.now_playing ? 'margin-top:6px;' : 'display:none; margin-top:6px;'}">
              <i class="fas fa-wave-square"></i> <span>${escapeHtml(st.now_playing || '')}</span>
            </div>
          </div>
          <div class="sh-card-actions">
            <button type="button" class="sh-btn is-play" onclick="window.StreamHunterUI.playInAppById('${escapeHtml(st.id)}')" title="Play inside Hecos Floating Stream Dock">
              <i class="fas fa-play"></i> Play In-App
            </button>
            <button type="button" class="sh-btn is-vlc" onclick="window.StreamHunterUI.openInVlcById('${escapeHtml(st.id)}', this)" title="Launch stream in VLC Media Player Desktop">
              <i class="fas fa-tv"></i> Open in VLC
            </button>
            <button type="button" class="sh-btn is-probe" onclick="window.StreamHunterUI.probeSingleById('${escapeHtml(st.id)}')" title="Check live status, latency & ICY metadata">
              <i class="fas fa-bolt"></i> Probe
            </button>
            ${isM3uPlaylist ? `
            <button type="button" class="sh-btn" onclick="window.StreamHunterUI.expandM3uById('${escapeHtml(st.id)}')" title="Parse and expand channels inside this M3U playlist">
              <i class="fas fa-list-ul"></i> Expand M3U
            </button>` : ''}
            <button type="button" class="sh-btn" onclick="window.StreamHunterUI.copyUrlById('${escapeHtml(st.id)}', this)" title="Copy direct stream URL">
              <i class="fas fa-copy"></i> Copy
            </button>
          </div>
        </div>
      `;
    }).join('');

    container.innerHTML = `<div class="sh-grid">${cardsHtml}</div>`;
    setupPreviewObserver();
    if (window.StreamRemoteController && typeof window.StreamRemoteController.syncLineup === 'function') {
      const qInput = document.getElementById('search-input');
      window.StreamRemoteController.syncLineup(filtered, {
        category: currentSubfilter,
        query: qInput ? qInput.value.trim() : '',
      });
    }
  }

  function findStreamById(id) {
    return currentStreams.find(s => s.id === id) || null;
  }

  async function runStreamSearch(queryStr, subfilterOverride = null) {
    if (isSearching) return;
    isSearching = true;

    const st = window.SearchState || {};
    const q = (queryStr !== undefined && queryStr !== null) ? String(queryStr).trim() : (st.currentQuery || '');
    if (subfilterOverride) {
      currentSubfilter = subfilterOverride;
    }

    syncToolbarVisibility('streams');

    const container = document.getElementById('results-list');
    const countEl = document.getElementById('results-count');
    const durationEl = document.getElementById('results-duration');
    if (countEl) countEl.textContent = 'Scanning live TV, Radio, Webcams & M3U8 feeds...';
    if (durationEl) durationEl.textContent = '';
    if (container) {
      container.innerHTML = `
        <div style="text-align:center; padding: 48px 20px; color: #38bdf8;">
          <i class="fas fa-satellite-dish fa-spin" style="font-size: 30px; margin-bottom: 10px;"></i>
          <div style="font-size: 14px; font-weight: 600; color:#e2e8f0;">Scanning Global Live Streams...</div>
        </div>
      `;
    }

    if (window.CyberMapBus) {
      window.CyberMapBus.emit('SEARCH_STARTED', {
        query: q || 'Live Streams',
        mode: 'streams',
        sessionId: `streams_${Date.now()}`,
        localOnly: Boolean(st.localOnly),
      });
    }

    try {
      const resp = await fetch('/api/hsearch/streams/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: q,
          subfilter: 'all',
          country: currentCountry === 'ALL' ? '' : currentCountry,
          limit: 100,
          local_only: st.localOnly,
        }),
      });
      const data = await resp.json();
      isSearching = false;

      if (!data || !data.ok) {
        if (countEl) countEl.textContent = 'Stream scan failed';
        return;
      }

      currentStreams = data.streams || [];
      updateSubfilterCounts(data.counts || {});
      if (durationEl && data.duration_sec !== undefined) {
        durationEl.textContent = `(${data.duration_sec}s)`;
      }

      // Sync with global SearchState & Cyber Map so discovered stream servers plot on the 3D/2D map!
      if (window.SearchState) {
        window.SearchState.results = data.search_results || [];
        window.SearchState.currentQuery = q;
        window.SearchState.currentMode = 'streams';
        window.SearchState.scrollRenderCount = Math.max(window.SearchState.scrollRenderCount || 40, currentStreams.length + 10);
      }
      if (window.CyberMapBus && Array.isArray(data.search_results)) {
        window.CyberMapBus.emit('SEARCH_RESULTS', {
          results: data.search_results,
          engine: 'streams_hunter',
          localOnly: Boolean(st.localOnly),
        });
        window.CyberMapBus.emit('SEARCH_COMPLETED', {});
      }

      renderStreamsGrid(currentStreams);
    } catch (err) {
      isSearching = false;
      console.warn('[StreamHunterUI] Search error:', err);
      if (countEl) countEl.textContent = 'Error scanning streams';
    }
  }

  function setSubfilter(sub) {
    currentSubfilter = sub || 'all';
    document.querySelectorAll('.sh-subfilter-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.subfilter === currentSubfilter);
    });
    renderStreamsGrid(currentStreams);
  }

  function setCountryFilter(cc) {
    currentCountry = (cc || 'ALL').toUpperCase();
    const input = document.getElementById('search-input');
    runStreamSearch(input ? input.value : '');
  }

  function quickSearch(term, sub = 'all') {
    const input = document.getElementById('search-input');
    if (input) input.value = term;
    currentSubfilter = sub;
    document.querySelectorAll('.sh-subfilter-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.subfilter === currentSubfilter);
    });
    runStreamSearch(term, sub);
  }

  function playInAppById(id) {
    const st = findStreamById(id);
    if (st && window.StreamPlayerDock) {
      window.StreamPlayerDock.playStream(st, false);
      if (window.StreamRemoteController && typeof window.StreamRemoteController.setActiveStream === 'function') {
        window.StreamRemoteController.setActiveStream(st);
      }
    }
  }

  function _getActions() {
    if (!_actions && window.StreamHunterActions) {
      _actions = window.StreamHunterActions.create({
        findStreamById,
        escapeHtml,
        replaceExpandedStream: (id, newStreams) => {
          currentStreams = [...newStreams, ...currentStreams.filter(x => x.id !== id)];
          renderStreamsGrid(currentStreams);
        },
      });
    }
    return _actions;
  }

  function openInVlc(streamUrl, title, btnEl = null) { return _getActions()?.openInVlc(streamUrl, title, btnEl); }
  function openInVlcById(id, btnEl = null) { return _getActions()?.openInVlcById(id, btnEl); }
  function openAllInVlcPlaylist(btnEl = null) { return _getActions()?.openAllInVlcPlaylist(_getVisibleStreams(), btnEl); }
  function downloadM3uPlaylist() { return _getActions()?.downloadM3uPlaylist(currentSubfilter, currentCountry); }
  function probeSingleById(id) { return _getActions()?.probeSingleById(id); }
  function probeVisibleStreams() { return _getActions()?.probeVisibleStreams(_getVisibleStreams()); }
  function expandM3uById(id) { return _getActions()?.expandM3uById(id); }
  function copyUrlById(id, btnEl) { return _getActions()?.copyUrlById(id, btnEl); }

  function initStreamHunter() {
    fetchCapabilities();

    // Hook into SearchStream.executeSearch so submitting a query in 'streams' mode delegates here
    if (window.SearchStream && window.SearchStream.executeSearch && !window.SearchStream._shWrapped) {
      const origExec = window.SearchStream.executeSearch;
      const wrappedExec = function (queryStr, mode) {
        const effectiveMode = mode || (window.SearchState && window.SearchState.currentMode) || 'clear';
        syncToolbarVisibility(effectiveMode);
        if (effectiveMode === 'streams') {
          runStreamSearch(queryStr);
          return;
        }
        return origExec.apply(this, arguments);
      };
      wrappedExec._shWrapped = true;
      window.SearchStream.executeSearch = wrappedExec;
      window.executeSearch = wrappedExec;
    }

    // Hook mode-pill clicks to toggle toolbar & auto-load initial stream catalog when switching to 'streams'
    document.querySelectorAll('.mode-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        const m = pill.dataset.mode;
        syncToolbarVisibility(m);
        if (m === 'streams') {
          const input = document.getElementById('search-input');
          const q = input ? input.value.trim() : '';
          runStreamSearch(q);
        }
      });
    });

    // If page booted directly into mode=streams
    if (window.SearchState && window.SearchState.currentMode === 'streams') {
      syncToolbarVisibility('streams');
      const input = document.getElementById('search-input');
      runStreamSearch(input ? input.value.trim() : '');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(initStreamHunter, 50));
  } else {
    setTimeout(initStreamHunter, 50);
  }

  function renderCurrentStreams() {
    renderStreamsGrid(currentStreams);
  }

  window.StreamHunterUI = {
    runStreamSearch,
    renderCurrentStreams,
    setSubfilter,
    setCountryFilter,
    quickSearch,
    playInAppById,
    openInVlc,
    openInVlcById,
    openAllInVlcPlaylist,
    downloadM3uPlaylist,
    probeSingleById,
    probeVisibleStreams,
    expandM3uById,
    copyUrlById,
    refreshPreviewById,
    toggleAutoPreviewRefresh,
    openHubConfig,
  };
})();
