/**
 * search_results.js
 * Renders search results (standard cards, media grids, audio players, file dorks)
 * with interactive actions and filtering capabilities.
 */
window.SearchResults = (function () {

  function _showBanner(msg, type = 'info', duration = 3500) {
    if (window.UnifiedToast && typeof window.UnifiedToast.show === 'function') {
      const iconMap = {
        success: 'fas fa-check-circle',
        error: 'fas fa-exclamation-triangle',
        warning: 'fas fa-exclamation-circle',
        info: 'fas fa-info-circle'
      };
      window.UnifiedToast.show(msg, iconMap[type] || 'fas fa-info-circle', duration);
      return;
    }
    if (typeof window.showToast === 'function') {
      window.showToast(msg, duration, type);
      return;
    }
    let banner = document.getElementById('hecos-search-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'hecos-search-banner';
      banner.style.cssText = [
        'position:fixed', 'top:66px', 'left:50%', 'transform:translate(-50%,-12px)',
        'background:rgba(24,25,38,0.96)', 'color:#cad3f5', 'border:1px solid rgba(255,255,255,0.15)',
        'border-radius:999px', 'padding:10px 20px', 'font-size:13px', 'font-weight:500',
        'box-shadow:0 8px 28px rgba(0,0,0,0.45)', 'z-index:10050', 'opacity:0',
        'pointer-events:none', 'transition:opacity 0.25s ease,transform 0.25s ease',
        'display:inline-flex', 'align-items:center', 'gap:10px', 'max-width:min(92vw,680px)'
      ].join(';');
      document.body.appendChild(banner);
    }
    banner.textContent = msg;
    banner.style.borderColor = type === 'error' ? 'rgba(244,63,94,0.5)' : (type === 'success' ? 'rgba(16,185,129,0.45)' : 'rgba(6,182,212,0.45)');
    banner.style.opacity = '1';
    banner.style.transform = 'translate(-50%,0)';
    clearTimeout(banner._hideTimer);
    banner._hideTimer = setTimeout(() => {
      banner.style.opacity = '0';
      banner.style.transform = 'translate(-50%,-12px)';
    }, duration);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function getDomain(url) {
    try {
      return new URL(url).hostname;
    } catch {
      return url;
    }
  }

  function renderBookmarkBtn(url, title, snippet, engine, isTor, small = false) {
    const isBm = window.BookmarksManager && window.BookmarksManager.isBookmarked(url);
    const style = small ? 'padding:3px 7px; font-size:10px;' : '';
    const safeUrl = escapeHtml(url);
    const safeTitle = escapeHtml(title || '');
    const safeSnippet = escapeHtml(snippet || '');
    const safeEngine = escapeHtml(engine || 'web');
    return `
      <button type="button" class="btn-result-action btn-bookmark-action ${isBm ? 'active' : ''}" style="${style}" data-url="${safeUrl}" onclick="window.BookmarksManager.toggle('${safeUrl}', '${safeTitle}', '${safeSnippet}', '${safeEngine}', ${isTor}, this)" title="${isBm ? 'Remove from Saved Links' : 'Save to Bookmarks'}">
        <i class="${isBm ? 'fas' : 'far'} fa-star" style="${isBm ? 'color:#f59e0b;' : ''}"></i>
      </button>
    `;
  }

  function renderStandardCard(item) {
    const isTor = item.network === 'tor' || (item.url && item.url.includes('.onion'));
    const onionClass = isTor ? 'onion-card' : '';
    const netBadge = isTor
      ? '<span class="badge-network tor"><i class="fas fa-user-secret"></i> Onion</span>'
      : '<span class="badge-network clearnet"><i class="fas fa-globe"></i> Web</span>';

    const domain = getDomain(item.url);
    const safeTitle = escapeHtml(item.title);
    const safeSnippet = escapeHtml(item.snippet);
    const safeUrl = escapeHtml(item.url);
    const safeEngine = escapeHtml(item.engine || 'web');

    return `
      <div class="result-card ${onionClass}" data-url="${safeUrl}" data-category="${escapeHtml(item.category || 'web')}" data-engine="${safeEngine}">
        <div class="result-top-meta">
          ${netBadge}
          <span class="result-engine-tag">${safeEngine}</span>
          <span class="result-domain" title="${safeUrl}">${domain}</span>
        </div>
        ${isTor ? `
          <a href="javascript:void(0)" onclick="SearchResults.handleTorClick('${safeUrl}', '${safeTitle}')" class="result-title tor-title" title="Open .onion site (Click for Live Viewer / Tor Browser)">
            <i class="fas fa-shield-alt" style="color:var(--accent-purple, #a855f7); font-size:12px; margin-right:4px;"></i>${safeTitle}
          </a>
        ` : `
          <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="result-title">
            ${safeTitle}
          </a>
        `}
        <div class="result-snippet">${safeSnippet}</div>
        <div class="result-actions">
          ${isTor ? `
            <button class="btn-result-action primary" onclick="SearchResults.openInViewer('${safeUrl}')" title="Open in Hecos Tor Live Viewer (In-App Cross-Browser)">
              <i class="fas fa-desktop"></i> Live Viewer
            </button>
            <button class="btn-result-action" onclick="SearchResults.openInTorBrowser('${safeUrl}')" title="Launch link in desktop Tor Browser">
              <i class="fas fa-external-link-alt" style="color:var(--accent-purple, #a855f7);"></i> Tor Browser
            </button>
          ` : `
            <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="btn-result-action primary" style="text-decoration:none;">
              <i class="fas fa-external-link-alt"></i> Open
            </a>
          `}
          <button class="btn-result-action" onclick="SearchResults.copyLink('${safeUrl}')">
            <i class="fas fa-copy"></i> Copy Link
          </button>
          <button class="btn-result-action" onclick="SearchResults.sendToChat('${safeTitle}', '${safeUrl}')">
            <i class="fas fa-comment-dots"></i> Send to Chat
          </button>
          ${renderBookmarkBtn(item.url, item.title, item.snippet, item.engine, isTor)}
        </div>
      </div>
    `;
  }

  function renderImageCard(item) {
    const safeTitle = escapeHtml(item.title || 'Image Result');
    const safeUrl = escapeHtml(item.url);
    const imgUrl = escapeHtml(item.media_url || item.thumbnail_url || item.url);
    const thumb = escapeHtml(item.thumbnail_url || item.media_url || item.url);
    const w = item.metadata?.width || '';
    const h = item.metadata?.height || '';
    const dimBadge = (w && h) ? `<span class="media-dim-badge">${w}x${h}</span>` : '';
    const domain = getDomain(item.url);
    const safeEngine = escapeHtml(item.engine || 'media_images');

    return `
      <div class="media-card image-card" data-url="${safeUrl}" data-category="images" data-engine="${safeEngine}">
        <div class="media-thumb-box image-thumb-box">
          <img src="${thumb}" alt="${safeTitle}" class="media-thumb-img" loading="lazy" onerror="this.onerror=null; this.parentElement.innerHTML='<div class=\\'media-thumb-fallback\\'><i class=\\'fas fa-image\\'></i></div>';">
          ${dimBadge}
          <a href="${imgUrl}" target="_blank" rel="noopener noreferrer" class="media-zoom-overlay" title="Open original image">
            <i class="fas fa-expand"></i>
          </a>
        </div>
        <div class="media-card-body">
          <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="media-card-title" title="${safeTitle}">${safeTitle}</a>
          <div class="media-card-footer">
            <span class="media-source-tag"><i class="fas fa-globe"></i> ${domain}</span>
            <div class="media-card-actions">
              <button class="btn-result-action" style="padding:3px 7px; font-size:10px;" onclick="SearchResults.copyLink('${imgUrl}')" title="Copy image link">
                <i class="fas fa-copy"></i>
              </button>
              <button class="btn-result-action" style="padding:3px 8px; font-size:10px;" onclick="SearchResults.sendToChat('${safeTitle}', '${imgUrl}')" title="Send to Chat">
                <i class="fas fa-comment-dots"></i> Chat
              </button>
              ${renderBookmarkBtn(imgUrl, item.title, '', item.engine, false, true)}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderVideoCard(item) {
    const safeTitle = escapeHtml(item.title || 'Video Result');
    const safeUrl = escapeHtml(item.url);
    const thumb = escapeHtml(item.thumbnail_url || item.media_url || '');
    const dur = escapeHtml(item.metadata?.duration || '');
    const pub = escapeHtml(item.metadata?.publisher || getDomain(item.url));
    const durBadge = dur ? `<span class="video-dur-badge"><i class="fas fa-play"></i> ${dur}</span>` : '';
    const safeEngine = escapeHtml(item.engine || 'media_videos');

    // Dynamic brand icon and style
    let brandIcon = 'fas fa-video';
    const lowerEngine = safeEngine.toLowerCase();
    const lowerPub = pub.toLowerCase();
    if (lowerEngine.includes('youtube') || lowerPub.includes('youtube')) {
      brandIcon = 'fab fa-youtube" style="color:#ef4444;';
    } else if (lowerEngine.includes('dailymotion') || lowerPub.includes('dailymotion')) {
      brandIcon = 'fas fa-circle-play" style="color:#3b82f6;';
    } else if (lowerEngine.includes('peertube') || lowerPub.includes('peertube') || lowerPub.includes('sepia')) {
      brandIcon = 'fas fa-cube" style="color:#f97316;';
    } else if (lowerEngine.includes('archive') || lowerPub.includes('archive')) {
      brandIcon = 'fas fa-landmark" style="color:#eab308;';
    } else if (lowerEngine.includes('vimeo') || lowerPub.includes('vimeo')) {
      brandIcon = 'fab fa-vimeo-v" style="color:#06b6d4;';
    } else if (lowerEngine.includes('bilibili') || lowerPub.includes('bilibili')) {
      brandIcon = 'fab fa-tv" style="color:#ec4899;';
    }

    return `
      <div class="media-card video-card" data-url="${safeUrl}" data-category="videos" data-engine="${safeEngine}">
        <div class="media-thumb-box video-thumb-box">
          ${thumb ? `<img src="${thumb}" alt="${safeTitle}" class="media-thumb-img" loading="lazy" onerror="this.onerror=null; this.parentElement.innerHTML='<div class=\\'media-thumb-fallback\\'><i class=\\'fas fa-video\\'></i></div>';">` : `<div class="media-thumb-fallback"><i class="fas fa-video"></i></div>`}
          ${durBadge}
          <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="video-play-overlay" title="Watch video">
            <i class="fas fa-circle-play"></i>
          </a>
        </div>
        <div class="media-card-body">
          <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="media-card-title" title="${safeTitle}">${safeTitle}</a>
          <div class="media-card-footer">
            <span class="media-source-tag"><i class="${brandIcon}"></i> ${pub} <small style="opacity:0.75; margin-left:4px;">(${safeEngine})</small></span>
            <div class="media-card-actions">
              <button class="btn-result-action" style="padding:3px 7px; font-size:10px;" onclick="SearchResults.copyLink('${safeUrl}')" title="Copy video link">
                <i class="fas fa-copy"></i>
              </button>
              <button class="btn-result-action" style="padding:3px 8px; font-size:10px;" onclick="SearchResults.sendToChat('${safeTitle}', '${safeUrl}')" title="Send to Chat">
                <i class="fas fa-comment-dots"></i> Chat
              </button>
              ${renderBookmarkBtn(item.url, item.title, '', item.engine, false, true)}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderAudioCard(item) {
    const safeTitle = escapeHtml(item.title || 'Audio Result');
    const safeUrl = escapeHtml(item.url);
    const safeSnippet = escapeHtml(item.snippet || '');
    const domain = getDomain(item.url);
    const thumb = item.thumbnail_url || item.metadata?.artwork || item.metadata?.image || '';
    const artist = escapeHtml(item.metadata?.artist || item.metadata?.creator || '');
    const isDirectAudio = item.url.match(/\.(mp3|wav|ogg|m4a|aac)(\?.*)?$/i) ||
      (item.media_url && item.media_url.match(/\.(mp3|wav|ogg|m4a|aac)(\?.*)?$/i)) ||
      Boolean(item.metadata?.preview_url);
    const directAudioUrl = isDirectAudio ? (item.metadata?.preview_url || item.media_url || item.url) : '';
    const safeEngine = escapeHtml(item.engine || 'media_audio');

    // Brand icon resolution
    let brandIcon = 'fas fa-music';
    const engLower = (item.engine || '').toLowerCase() + ' ' + (item.url || '').toLowerCase();
    if (engLower.includes('itunes') || engLower.includes('apple')) brandIcon = 'fab fa-apple';
    else if (engLower.includes('soundcloud')) brandIcon = 'fab fa-soundcloud';
    else if (engLower.includes('bandcamp')) brandIcon = 'fab fa-bandcamp';
    else if (engLower.includes('spotify')) brandIcon = 'fab fa-spotify';
    else if (engLower.includes('archive')) brandIcon = 'fas fa-box-archive';
    else if (engLower.includes('genius')) brandIcon = 'fas fa-align-left';
    else if (engLower.includes('podcast')) brandIcon = 'fas fa-podcast';

    return `
      <div class="result-card audio-result-card" data-url="${safeUrl}" data-category="audio" data-engine="${safeEngine}">
        <div class="result-top-meta">
          <span class="badge-network audio-badge"><i class="fas fa-music"></i> Audio</span>
          <span class="result-engine-tag"><i class="${brandIcon}"></i> ${safeEngine}</span>
          ${artist ? `<span class="audio-artist-tag"><i class="fas fa-microphone-lines"></i> ${artist}</span>` : ''}
          <span class="result-domain">${domain}</span>
        </div>
        <div class="audio-main-row">
          <div class="audio-cover-box">
            ${thumb ? `
              <img src="${escapeHtml(thumb)}" alt="${safeTitle}" class="audio-cover-img" loading="lazy" onerror="this.onerror=null; this.parentElement.innerHTML='<div class=\\'audio-disc-icon\\'><i class=\\'fas fa-compact-disc\\'></i></div>';">
            ` : `
              <div class="audio-disc-icon">
                <i class="fas fa-compact-disc"></i>
              </div>
            `}
          </div>
          <div class="audio-content-col">
            <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="result-title audio-title" title="${safeTitle}">${safeTitle}</a>
            ${safeSnippet ? `<div class="result-snippet audio-snippet">${safeSnippet}</div>` : ''}
            ${directAudioUrl ? `
              <div class="audio-player-box">
                <audio controls preload="none" class="audio-inline-player">
                  <source src="${escapeHtml(directAudioUrl)}">
                  Your browser does not support audio playback.
                </audio>
              </div>
            ` : ''}
          </div>
        </div>
        <div class="result-actions audio-actions">
          <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="btn-result-action primary">
            <i class="fas fa-headphones"></i> Listen on ${domain}
          </a>
          <button class="btn-result-action" onclick="SearchResults.copyLink('${safeUrl}')">
            <i class="fas fa-copy"></i> Copy Link
          </button>
          <button class="btn-result-action" onclick="SearchResults.sendToChat('${safeTitle}', '${safeUrl}')">
            <i class="fas fa-comment-dots"></i> Send to Chat
          </button>
          ${renderBookmarkBtn(item.url, item.title, item.snippet, item.engine, false)}
        </div>
      </div>
    `;
  }

  function renderFileCard(item) {
    const safeTitle = escapeHtml(item.title || 'Document');
    const safeUrl = escapeHtml(item.url);
    const safeSnippet = escapeHtml(item.snippet);
    const domain = getDomain(item.url);
    const ext = (item.metadata?.extension || item.url.split('.').pop().split(/[?#]/)[0] || 'DOC').toUpperCase();
    const extColorClass = `ext-${ext.toLowerCase()}`;
    const safeEngine = escapeHtml(item.engine || 'files_dorks');

    return `
      <div class="result-card file-result-card" data-url="${safeUrl}" data-category="files" data-engine="${safeEngine}">
        <div class="result-top-meta">
          <span class="badge-file-ext ${extColorClass}"><i class="fas fa-file-alt"></i> ${ext}</span>
          <span class="result-engine-tag">${safeEngine}</span>
          <span class="result-domain">${domain}</span>
        </div>
        <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="result-title">${safeTitle}</a>
        <div class="result-snippet">${safeSnippet}</div>
        <div class="result-actions">
          <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="btn-result-action primary" download>
            <i class="fas fa-download"></i> Download / Open ${ext}
          </a>
          <button class="btn-result-action" onclick="SearchResults.copyLink('${safeUrl}')">
            <i class="fas fa-copy"></i> Copy Link
          </button>
          <button class="btn-result-action" onclick="SearchResults.sendToChat('${safeTitle}', '${safeUrl}')">
            <i class="fas fa-comment-dots"></i> Send to Chat
          </button>
          ${renderBookmarkBtn(item.url, item.title, item.snippet, item.engine, false)}
        </div>
      </div>
    `;
  }

  function safeRender(fn, item) {
    try {
      return fn(item);
    } catch (e) {
      console.warn('[SearchResults] Card render error:', e, item);
      try {
        return renderStandardCard(item);
      } catch (err2) {
        return `<div class="result-card"><a href="${escapeHtml(item.url)}" target="_blank">${escapeHtml(item.title || item.url)}</a></div>`;
      }
    }
  }

  function detectRenderCategory(item) {
    if (window.SearchFilters && typeof window.SearchFilters.classifyItemType === 'function') {
      return window.SearchFilters.classifyItemType(item);
    }
    const cat = (item.category || '').toLowerCase();
    const engId = (item.engine_id || '').toLowerCase();
    if (cat === 'videos' || cat === 'video' || engId === 'media_videos') return 'videos';
    if (cat === 'audio' || cat === 'music' || engId === 'media_audio') return 'audio';
    if (cat === 'images' || cat === 'image' || engId === 'media_images') return 'images';
    if (cat === 'files' || cat === 'packages' || engId === 'files_dorks' || Boolean(item.metadata?.extension)) return 'files';
    return 'web';
  }

  return {
    render(results, containerId = 'results-list', mode = 'clear', activeFilter = 'all') {
      const container = document.getElementById(containerId);
      if (!container) return;

      // Guard: keep Stream Hunter's live preview grid intact when active in streams mode
      const activeMode = mode || (window.SearchState && window.SearchState.currentMode);
      if (activeMode === 'streams' && containerId === 'results-list' && window.StreamHunterUI && typeof window.StreamHunterUI.renderCurrentStreams === 'function') {
        window.StreamHunterUI.renderCurrentStreams();
        return;
      }

      if (!results || results.length === 0) {
        container.className = 'results-list';
        const refineQuery = (window.SearchState && window.SearchState.refineQuery || '').trim();
        const mediaSub = (window.SearchState && window.SearchState.mediaSubFilter) || 'all';
        const hasRefine = Boolean(refineQuery) || (activeFilter === 'deep_media' && mediaSub !== 'all');
        const isFiltered = hasRefine || (activeFilter && activeFilter !== 'all');
        let titleText = 'No results found';
        let subText = 'Try adjusting your search terms or choosing a different mode.';
        if (hasRefine) {
          titleText = refineQuery
            ? `No results match "${escapeHtml(refineQuery)}"`
            : `No ${escapeHtml(mediaSub)} results in Media pool`;
          subText = 'Try clearing or loosening your in-results filter or reset filters below.';
        } else if (activeFilter && activeFilter !== 'all') {
          titleText = `No results match filter '${escapeHtml(activeFilter)}'`;
          subText = "Try selecting 'All' tab to view all aggregated items.";
        }
        container.innerHTML = `
          <div style="text-align:center; padding: 48px 20px; color: var(--text-dim);">
            <div style="font-size: 40px; margin-bottom: 12px; opacity:0.4;"><i class="fas fa-${isFiltered ? 'filter' : 'search'}"></i></div>
            <div style="font-size: 15px; font-weight:600; color:var(--text-main); margin-bottom:4px;">${titleText}</div>
            <div style="font-size: 12px; color:var(--text-muted); margin-bottom:${hasRefine ? '14px' : '0'};">${subText}</div>
            ${hasRefine ? `<button type="button" class="btn btn-sm btn-secondary" style="border-radius:6px;" onclick="if(window.resetPostSearchFilters) window.resetPostSearchFilters()"><i class="fas fa-rotate-left"></i> Reset In-Results Filters</button>` : ''}
          </div>
        `;
        return;
      }

      // Filter-specific rendering layouts
      if (activeFilter === 'images') {
        container.className = 'results-grid';
        container.innerHTML = results.map(r => safeRender(renderImageCard, r)).join('');
        return;
      }

      if (activeFilter === 'videos') {
        container.className = 'results-grid';
        container.innerHTML = results.map(r => safeRender(renderVideoCard, r)).join('');
        return;
      }

      if (activeFilter === 'audio') {
        container.className = 'results-list';
        container.innerHTML = results.map(r => safeRender(renderAudioCard, r)).join('');
        return;
      }

      if (activeFilter === 'files' || activeFilter.startsWith('files_') || activeFilter === 'deep_files') {
        container.className = 'results-list';
        container.innerHTML = results.map(r => safeRender(renderFileCard, r)).join('');
        return;
      }

      if (activeFilter === 'deep_media') {
        const allAudio = results.every(r => detectRenderCategory(r) === 'audio');
        container.className = allAudio ? 'results-list' : 'results-grid';
        container.innerHTML = results.map(r => {
          const kind = detectRenderCategory(r);
          if (kind === 'videos') return safeRender(renderVideoCard, r);
          if (kind === 'audio') return safeRender(renderAudioCard, r);
          return safeRender(renderImageCard, r);
        }).join('');
        return;
      }

      // 'all' or default mode rendering
      if (mode === 'media') {
        container.className = 'results-grid';
        container.innerHTML = results.map(r => {
          const kind = detectRenderCategory(r);
          if (kind === 'videos') return safeRender(renderVideoCard, r);
          if (kind === 'audio') return safeRender(renderAudioCard, r);
          return safeRender(renderImageCard, r);
        }).join('');
      } else {
        container.className = 'results-list';
        container.innerHTML = results.map(r => {
          const kind = detectRenderCategory(r);
          if (kind === 'images') return safeRender(renderImageCard, r);
          if (kind === 'videos') return safeRender(renderVideoCard, r);
          if (kind === 'audio') return safeRender(renderAudioCard, r);
          if (kind === 'files') return safeRender(renderFileCard, r);
          return safeRender(renderStandardCard, r);
        }).join('');
      }
    },

    copyLink(url) {
      navigator.clipboard.writeText(url).then(() => {
        _showBanner('Link copied to clipboard!', 'success', 2500);
      }).catch(() => {
        _showBanner('Could not copy link to clipboard.', 'error', 3000);
      });
    },

    sendToChat(title, url) {
      const markdownCitation = `[${title}](${url})`;
      navigator.clipboard.writeText(markdownCitation).then(() => {
        _showBanner(`Citation copied for chat: ${title}`, 'success', 3000);
      }).catch(() => {
        _showBanner('Could not copy citation to clipboard.', 'error', 3000);
      });
    },

    handleTorClick(url, title) {
      const action = window.currentTorAction || 'hecos_viewer';
      if (action === 'tor_browser') {
        this.openInTorBrowser(url);
      } else if (action === 'ask_menu') {
        this.showTorActionModal(url, title);
      } else {
        this.openInViewer(url);
      }
    },

    openInViewer(url) {
      window.open(`/search/viewer?url=${encodeURIComponent(url)}`, '_blank');
    },

    async openInTorBrowser(url) {
      _showBanner('Launching Tor Browser...', 'info', 2500);
      try {
        const res = await window.SearchAPI.openTorBrowser(url);
        if (res.ok) {
          _showBanner('Tor Browser launched with ' + url, 'success', 3500);
        } else {
          _showBanner('Could not launch Tor Browser: ' + (res.error || res.message || 'Unknown error'), 'error', 4500);
        }
      } catch (err) {
        _showBanner('Error launching Tor Browser: ' + err.message, 'error', 4500);
      }
    },

    showTorActionModal(url, title) {
      let modal = document.getElementById('tor-action-modal');
      if (!modal) {
        const modalHtml = `
          <div class="search-modal-backdrop" id="tor-action-modal" onclick="if(event.target===this) this.classList.remove('open')">
            <div class="search-modal" style="max-width:480px;">
              <div class="search-modal-header">
                <h3 style="margin:0; font-size:15px; font-weight:700; color:var(--text);"><i class="fas fa-user-secret" style="color:var(--accent-purple, #a855f7);"></i> Open Dark Web (.onion) Site</h3>
                <button type="button" class="search-modal-close" onclick="document.getElementById('tor-action-modal').classList.remove('open')">&times;</button>
              </div>
              <div class="search-modal-body" style="padding:18px;">
                <p style="font-size:12px; color:var(--muted); margin-top:0; margin-bottom:14px; word-break:break-all;" id="tor-modal-url"></p>
                <div style="display:flex; flex-direction:column; gap:10px;">
                  <button type="button" class="btn btn-primary" id="btn-modal-viewer" style="border-radius:6px; padding:10px 14px; font-size:12px; text-align:left; display:flex; align-items:center; gap:10px;">
                    <i class="fas fa-desktop" style="font-size:16px;"></i>
                    <div>
                      <strong>Open in Hecos Tor Live Viewer</strong>
                      <div style="font-size:10px; opacity:0.8;">Browse directly inside Chrome via Hecos SOCKS5h Tor proxy</div>
                    </div>
                  </button>
                  <button type="button" class="btn btn-secondary" id="btn-modal-browser" style="border-radius:6px; padding:10px 14px; font-size:12px; text-align:left; display:flex; align-items:center; gap:10px;">
                    <i class="fas fa-external-link-alt" style="font-size:16px; color:var(--accent-purple, #a855f7);"></i>
                    <div>
                      <strong>Launch in Desktop Tor Browser</strong>
                      <div style="font-size:10px; opacity:0.8;">Open natively in your installed Tor Browser application</div>
                    </div>
                  </button>
                  <button type="button" class="btn btn-secondary" id="btn-modal-copy" style="border-radius:6px; padding:8px 14px; font-size:12px; text-align:left; display:flex; align-items:center; gap:10px;">
                    <i class="fas fa-copy" style="font-size:14px;"></i>
                    <span>Copy .onion Address</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        modal = document.getElementById('tor-action-modal');
      }

      document.getElementById('tor-modal-url').innerText = url;
      document.getElementById('btn-modal-viewer').onclick = () => {
        modal.classList.remove('open');
        this.openInViewer(url);
      };
      document.getElementById('btn-modal-browser').onclick = () => {
        modal.classList.remove('open');
        this.openInTorBrowser(url);
      };
      document.getElementById('btn-modal-copy').onclick = () => {
        modal.classList.remove('open');
        this.copyLink(url);
      };
      modal.classList.add('open');
    }
  };
})();
