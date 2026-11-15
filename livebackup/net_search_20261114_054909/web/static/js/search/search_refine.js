/**
 * search_refine.js
 * Result classification, secondary refine query parser (site:, -term, type:, sort:), multi-criteria sort, and refine toolbar UI.
 */
window.SearchRefine = (function () {
  'use strict';
  const state = window.SearchState;

  // ── Granular Classification, Secondary In-Results Filter & Multi-Sort ─────
  function isTorItem(item) {
    if (!item) return false;
    if (item.network === 'tor') return true;
    const url = (item.url || '').toLowerCase();
    return url.includes('.onion');
  }

  function classifyItemType(item) {
    if (!item) return 'web';
    const cat = (item.category || '').toLowerCase();
    const engId = (item.engine_id || item.metadata?.engine_id || '').toLowerCase();
    const eng = (item.engine || '').toLowerCase();

    if (
      cat === 'videos' || cat === 'video' || engId === 'media_videos' ||
      /(video|youtube|dailymotion|peertube|vimeo|rumble|piped|odysee|bitchute|eporner|redtube)/i.test(eng)
    ) {
      return 'videos';
    }
    if (
      cat === 'audio' || cat === 'music' || engId === 'media_audio' ||
      /(audio|music|podcast|soundcloud|itunes|deezer|bandcamp|radio|mixcloud|genius)/i.test(eng)
    ) {
      return 'audio';
    }
    if (
      cat === 'images' || cat === 'image' || engId === 'media_images' ||
      /(image|flickr|deviantart|wallhaven|pinterest|unsplash|openverse|commons)/i.test(eng) ||
      (Boolean(item.thumbnail_url) && !['web', 'news', 'general', 'onion', 'osint', 'files', 'packages'].includes(cat))
    ) {
      return 'images';
    }
    if (
      cat === 'files' || cat === 'packages' || engId === 'files_dorks' ||
      /(dork|torrent|piratebay|kickass|solidtorrent|bt4g|zlibrary)/i.test(eng) ||
      Boolean(item.metadata && item.metadata.extension)
    ) {
      return 'files';
    }
    return 'web';
  }

  function extractHostname(url) {
    if (!url) return '';
    try {
      return new URL(url).hostname.toLowerCase();
    } catch (e) {
      return String(url).replace(/^https?:\/\//i, '').split('/')[0].toLowerCase();
    }
  }

  function parseItemDateMs(item) {
    const raw = item?.metadata?.date || item?.metadata?.published || item?.metadata?.published_at || item?.metadata?.upload_date || '';
    if (!raw) return null;
    if (typeof raw === 'number' && !isNaN(raw)) {
      return raw > 1e12 ? raw : raw * 1000;
    }
    const str = String(raw).trim();
    if (!str) return null;
    // Handle YYYYMMDD compact format (e.g. yt-dlp)
    if (/^\d{8}$/.test(str)) {
      const iso = `${str.slice(0, 4)}-${str.slice(4, 6)}-${str.slice(6, 8)}T00:00:00Z`;
      const ms = Date.parse(iso);
      return isNaN(ms) ? null : ms;
    }
    const ms = Date.parse(str);
    return isNaN(ms) ? null : ms;
  }

  function parseRefineQuery(raw) {
    const parsed = {
      positives: [],
      phrases: [],
      negatives: [],
      domains: [],
      engines: [],
      exts: [],
      types: []
    };
    if (!raw || !raw.trim()) return parsed;

    // Match negative/positive quoted strings or space-separated tokens
    const tokenRegex = /(-?"[^"]+"|\S+)/g;
    const matches = raw.match(tokenRegex) || [];

    for (const tok of matches) {
      const lower = tok.toLowerCase();
      if (lower.startsWith('-"') && lower.endsWith('"') && lower.length > 3) {
        parsed.negatives.push(lower.slice(2, -1));
      } else if (lower.startsWith('"') && lower.endsWith('"') && lower.length > 2) {
        parsed.phrases.push(lower.slice(1, -1));
      } else if (lower.startsWith('-') && lower.length > 1) {
        parsed.negatives.push(lower.slice(1));
      } else if ((lower.startsWith('domain:') || lower.startsWith('site:')) && lower.includes(':')) {
        const val = lower.split(':').slice(1).join(':').trim();
        if (val) parsed.domains.push(val);
      } else if (lower.startsWith('engine:') && lower.length > 7) {
        parsed.engines.push(lower.slice(7).trim());
      } else if (lower.startsWith('ext:') && lower.length > 4) {
        parsed.exts.push(lower.slice(4).replace(/^\./, '').trim());
      } else if (lower.startsWith('type:') && lower.length > 5) {
        parsed.types.push(lower.slice(5).trim());
      } else {
        parsed.positives.push(lower);
      }
    }
    return parsed;
  }

  function hasActiveRefineFilters(parsed) {
    return (
      parsed.positives.length > 0 ||
      parsed.phrases.length > 0 ||
      parsed.negatives.length > 0 ||
      parsed.domains.length > 0 ||
      parsed.engines.length > 0 ||
      parsed.exts.length > 0 ||
      parsed.types.length > 0
    );
  }

  function itemMatchesRefineQuery(item, parsed) {
    if (!parsed || !hasActiveRefineFilters(parsed)) return true;

    const url = (item.url || '').toLowerCase();
    const host = extractHostname(item.url);
    const engineStr = `${item.engine || ''} ${item.engine_id || ''} ${(item.metadata?.engine_ids || []).join(' ')}`.toLowerCase();
    const ext = (item.metadata?.extension || (url ? url.split('.').pop().split(/[?#]/)[0] : '') || '').toLowerCase();
    const itemType = classifyItemType(item);
    const isOnion = isTorItem(item);

    const haystack = [
      item.title || '',
      item.snippet || '',
      item.url || '',
      item.engine || '',
      item.engine_id || '',
      item.category || '',
      item.metadata?.publisher || '',
      item.metadata?.artist || '',
      item.metadata?.creator || '',
      item.metadata?.source || '',
      item.metadata?.extension || '',
      item.metadata?.date || ''
    ].join(' ').toLowerCase();

    for (const phrase of parsed.phrases) {
      if (!haystack.includes(phrase)) return false;
    }
    for (const term of parsed.positives) {
      if (!haystack.includes(term)) return false;
    }
    for (const neg of parsed.negatives) {
      if (haystack.includes(neg)) return false;
    }
    for (const dom of parsed.domains) {
      if (!host.includes(dom) && !url.includes(dom)) return false;
    }
    for (const eng of parsed.engines) {
      if (!engineStr.includes(eng)) return false;
    }
    for (const e of parsed.exts) {
      if (ext !== e && !url.includes(`.${e}`)) return false;
    }
    for (const t of parsed.types) {
      if (t === 'onion' || t === 'tor' || t === 'dark') {
        if (!isOnion) return false;
      } else if (t === 'clear' || t === 'clearnet') {
        if (isOnion) return false;
      } else if (t === 'video' || t === 'videos') {
        if (itemType !== 'videos') return false;
      } else if (t === 'image' || t === 'images' || t === 'photo' || t === 'photos') {
        if (itemType !== 'images') return false;
      } else if (t === 'audio' || t === 'music') {
        if (itemType !== 'audio') return false;
      } else if (t === 'file' || t === 'files' || t === 'doc' || t === 'docs') {
        if (itemType !== 'files') return false;
      } else if (t === 'web' || t === 'news' || t === 'article') {
        if (itemType !== 'web') return false;
      } else if (itemType !== t && (item.category || '').toLowerCase() !== t) {
        return false;
      }
    }
    return true;
  }

  const SORT_PRIORITY_MAPS = {
    videos_first: { videos: 0, images: 1, audio: 2, files: 3, web: 4 },
    images_first: { images: 0, videos: 1, audio: 2, files: 3, web: 4 },
    audio_first:  { audio: 0, videos: 1, images: 2, files: 3, web: 4 },
    files_first:  { files: 0, web: 1, images: 2, videos: 3, audio: 4 },
    web_first:    { web: 0, files: 1, videos: 2, images: 3, audio: 4 }
  };

  const SORT_DISPLAY_LABELS = {
    default: 'Default',
    videos_first: 'Videos First',
    images_first: 'Images First',
    audio_first: 'Audio First',
    files_first: 'Files First',
    web_first: 'Web First',
    onion_first: 'Dark Web (.onion) First',
    clear_first: 'Clearnet First',
    score_desc: 'Highest Score',
    date_desc: 'Newest Date',
    date_asc: 'Oldest Date',
    engine_asc: 'Source / Engine (A-Z)',
    domain_asc: 'Domain (A-Z)',
    title_asc: 'Title (A-Z)'
  };

  function sortResultsList(items, sortBy) {
    if (!sortBy || sortBy === 'default' || !Array.isArray(items) || items.length < 2) {
      return items;
    }

    const indexed = items.map((item, idx) => ({
      item,
      idx,
      type: classifyItemType(item),
      isTor: isTorItem(item),
      dateMs: (sortBy === 'date_desc' || sortBy === 'date_asc') ? parseItemDateMs(item) : null
    }));

    indexed.sort((a, b) => {
      if (SORT_PRIORITY_MAPS[sortBy]) {
        const prio = SORT_PRIORITY_MAPS[sortBy];
        const ra = prio[a.type] ?? 99;
        const rb = prio[b.type] ?? 99;
        if (ra !== rb) return ra - rb;
        return a.idx - b.idx;
      }

      if (sortBy === 'onion_first') {
        const ra = a.isTor ? 0 : 1;
        const rb = b.isTor ? 0 : 1;
        if (ra !== rb) return ra - rb;
        return a.idx - b.idx;
      }

      if (sortBy === 'clear_first') {
        const ra = a.isTor ? 1 : 0;
        const rb = b.isTor ? 1 : 0;
        if (ra !== rb) return ra - rb;
        return a.idx - b.idx;
      }

      if (sortBy === 'score_desc') {
        const sa = Number(a.item.score ?? 1);
        const sb = Number(b.item.score ?? 1);
        if (sb !== sa) return sb - sa;
        return a.idx - b.idx;
      }

      if (sortBy === 'engine_asc') {
        const ea = (a.item.engine || a.item.engine_id || '').toLowerCase();
        const eb = (b.item.engine || b.item.engine_id || '').toLowerCase();
        const cmp = ea.localeCompare(eb);
        return cmp !== 0 ? cmp : (a.idx - b.idx);
      }

      if (sortBy === 'domain_asc') {
        const da = extractHostname(a.item.url);
        const db = extractHostname(b.item.url);
        const cmp = da.localeCompare(db);
        return cmp !== 0 ? cmp : (a.idx - b.idx);
      }

      if (sortBy === 'title_asc') {
        const ta = (a.item.title || a.item.url || '').trim().toLowerCase();
        const tb = (b.item.title || b.item.url || '').trim().toLowerCase();
        const cmp = ta.localeCompare(tb);
        return cmp !== 0 ? cmp : (a.idx - b.idx);
      }

      if (sortBy === 'date_desc' || sortBy === 'date_asc') {
        const aHas = a.dateMs !== null;
        const bHas = b.dateMs !== null;
        if (aHas && !bHas) return -1;
        if (!aHas && bHas) return 1;
        if (aHas && bHas && a.dateMs !== b.dateMs) {
          return sortBy === 'date_desc' ? (b.dateMs - a.dateMs) : (a.dateMs - b.dateMs);
        }
        return a.idx - b.idx;
      }

      return a.idx - b.idx;
    });

    return indexed.map(entry => entry.item);
  }


  function syncRefineToolbarUI() {
    const refineInput = document.getElementById('results-refine-input');
    const clearBtn = document.getElementById('results-refine-clear');
    const sortSelect = document.getElementById('results-sort-select');
    const resetBtn = document.getElementById('btn-reset-post-filters');
    const mediaSubBar = document.getElementById('media-subtype-bar');

    const curRefine = state.refineQuery || '';
    if (refineInput && refineInput.value !== curRefine) {
      refineInput.value = curRefine;
    }
    if (clearBtn) {
      clearBtn.style.display = curRefine.trim() ? 'inline-flex' : 'none';
    }
    if (sortSelect && sortSelect.value !== (state.sortBy || 'default')) {
      sortSelect.value = state.sortBy || 'default';
    }

    const showMediaSubBar = state.activeFilter === 'deep_media';
    if (mediaSubBar) {
      mediaSubBar.style.display = showMediaSubBar ? 'flex' : 'none';
      const activeSub = state.mediaSubFilter || 'all';
      mediaSubBar.querySelectorAll('.media-subtab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mediaSubfilter === activeSub);
      });
    }

    const hasAnyPostFilter = Boolean(curRefine.trim()) ||
      (state.sortBy && state.sortBy !== 'default') ||
      (showMediaSubBar && state.mediaSubFilter && state.mediaSubFilter !== 'all');
    if (resetBtn) {
      resetBtn.style.display = hasAnyPostFilter ? 'inline-flex' : 'none';
    }
  }

  function setRefineQuery(rawQuery, shouldRender = true) {
    state.refineQuery = rawQuery != null ? String(rawQuery) : '';
    state.currentPage = 1;
    state.scrollRenderCount = 40;
    syncRefineToolbarUI();
    window.updateFilterCounts?.();
    if (shouldRender) {
      window.renderCurrentView?.();
    }
  }

  function setSortBy(sortBy, shouldRender = true) {
    state.sortBy = sortBy || 'default';
    state.currentPage = 1;
    state.scrollRenderCount = 40;
    syncRefineToolbarUI();
    if (shouldRender) {
      window.renderCurrentView?.();
    }
  }

  function setMediaSubFilter(subFilter, shouldRender = true) {
    state.mediaSubFilter = subFilter || 'all';
    state.currentPage = 1;
    state.scrollRenderCount = 40;
    syncRefineToolbarUI();
    if (shouldRender) {
      window.renderCurrentView?.();
    }
  }

  function resetPostSearchFilters(shouldRender = true) {
    state.refineQuery = '';
    state.sortBy = 'default';
    state.mediaSubFilter = 'all';
    state.currentPage = 1;
    state.scrollRenderCount = 40;
    syncRefineToolbarUI();
    window.updateFilterCounts?.();
    if (shouldRender) {
      window.renderCurrentView?.();
    }
  }

  let _refineTimer = null;
  function initRefineToolbar() {
    const refineInput = document.getElementById('results-refine-input');
    const clearBtn = document.getElementById('results-refine-clear');
    const sortSelect = document.getElementById('results-sort-select');

    if (refineInput && !refineInput.dataset.boundRefine) {
      refineInput.dataset.boundRefine = '1';
      refineInput.addEventListener('input', () => {
        clearTimeout(_refineTimer);
        const val = refineInput.value;
        if (clearBtn) clearBtn.style.display = val.trim() ? 'inline-flex' : 'none';
        _refineTimer = setTimeout(() => {
          setRefineQuery(val, true);
        }, 120);
      });
      refineInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          clearTimeout(_refineTimer);
          setRefineQuery(refineInput.value, true);
        } else if (e.key === 'Escape') {
          if (refineInput.value) {
            e.preventDefault();
            e.stopPropagation();
            clearTimeout(_refineTimer);
            setRefineQuery('', true);
          }
        }
      });
    }

    if (clearBtn && !clearBtn.dataset.boundClear) {
      clearBtn.dataset.boundClear = '1';
      clearBtn.addEventListener('click', () => {
        clearTimeout(_refineTimer);
        setRefineQuery('', true);
        if (refineInput) refineInput.focus();
      });
    }

    if (sortSelect && !sortSelect.dataset.boundSort) {
      sortSelect.dataset.boundSort = '1';
      sortSelect.value = state.sortBy || 'default';
    }

    syncRefineToolbarUI();
  }


  const api = {
    isTorItem,
    classifyItemType,
    extractHostname,
    parseItemDateMs,
    parseRefineQuery,
    hasActiveRefineFilters,
    itemMatchesRefineQuery,
    SORT_PRIORITY_MAPS,
    SORT_DISPLAY_LABELS,
    sortResultsList,
    syncRefineToolbarUI,
    setRefineQuery,
    setSortBy,
    setMediaSubFilter,
    resetPostSearchFilters,
    initRefineToolbar
  };

  window.setRefineQuery = setRefineQuery;
  window.setResultsSort = setSortBy;
  window.setMediaSubFilter = setMediaSubFilter;
  window.resetPostSearchFilters = resetPostSearchFilters;

  return api;
})();
