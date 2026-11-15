/**
 * Stream Hunter Live Snapshot & Auto-Preview Manager
 * Extracted from stream_hunter_ui.js for modularity.
 */
window.StreamPreviewManager = (function () {
  function create(opts = {}) {
    let autoPreviewEnabled = true;
    const previewRefreshIntervalMs = opts.refreshIntervalMs || 30000;
    let previewIntervalHandle = null;
    const visibleCardIds = new Set();
    let cardIntersectionObserver = null;

    function buildSnapshotUrl(st, force = false) {
      const params = new URLSearchParams({
        url: st.stream_url || '',
        title: st.title || 'Live Stream',
        category: st.category || 'tv',
        protocol: st.protocol || 'HLS',
        country: st.country || 'INT',
        force: force ? '1' : '0',
        t: String(Math.floor(Date.now() / (force ? 1 : 25000))),
      });
      return `/api/hsearch/streams/snapshot?${params.toString()}`;
    }

    function refreshPreviewById(id, force = true, ev = null) {
      if (ev && typeof ev.stopPropagation === 'function') {
        ev.stopPropagation();
      }
      const st = opts.findStreamById ? opts.findStreamById(id) : null;
      if (!st) return;
      const imgEl = document.getElementById(`sh-prev-img-${st.id}`);
      const btnEl = document.getElementById(`sh-prev-btn-${st.id}`);
      const badgeEl = document.getElementById(`sh-prev-ts-${st.id}`);
      if (!imgEl) return;

      if (btnEl) {
        btnEl.innerHTML = '<i class="fas fa-sync-alt fa-spin"></i>';
      }
      const nextUrl = buildSnapshotUrl(st, force);
      const preload = new Image();
      preload.onload = () => {
        imgEl.src = nextUrl;
        if (btnEl) btnEl.innerHTML = '<i class="fas fa-sync-alt"></i> Frame';
        if (badgeEl) {
          const nowStr = new Date().toLocaleTimeString([], { hour12: false });
          badgeEl.textContent = `● PREVIEW ${nowStr}`;
        }
      };
      preload.onerror = () => {
        console.warn('[StreamPreviewManager] Failed to load preview snapshot for stream id=' + sid, nextUrl);
        if (btnEl) btnEl.innerHTML = '<i class="fas fa-sync-alt"></i> Frame';
      };
      preload.src = nextUrl;
    }

    function setupPreviewObserver(streams = []) {
      if (cardIntersectionObserver) {
        cardIntersectionObserver.disconnect();
      }
      visibleCardIds.clear();
      if (typeof IntersectionObserver === 'function') {
        cardIntersectionObserver = new IntersectionObserver((entries) => {
          entries.forEach(entry => {
            const sid = entry.target.getAttribute('data-stream-id');
            if (!sid) return;
            if (entry.isIntersecting) {
              visibleCardIds.add(sid);
            } else {
              visibleCardIds.delete(sid);
            }
          });
        }, { threshold: 0.15 });

        document.querySelectorAll('.sh-card[data-stream-id]').forEach(card => {
          cardIntersectionObserver.observe(card);
        });
      } else {
        streams.slice(0, 12).forEach(st => visibleCardIds.add(st.id));
      }

      if (!previewIntervalHandle) {
        previewIntervalHandle = setInterval(() => {
          if (!autoPreviewEnabled) return;
          const mode = (window.SearchState && window.SearchState.currentMode) || '';
          if (mode !== 'streams' || document.hidden) return;
          const ids = Array.from(visibleCardIds).slice(0, 8);
          if (ids.length) {
            console.debug('[StreamPreviewManager] Periodic preview refresh for ' + ids.length + ' visible cards');
          }
          ids.forEach((id, i) => {
            setTimeout(() => refreshPreviewById(id, true), i * 350);
          });
        }, previewRefreshIntervalMs);
      }

      // Warmup refresh 4.5s after render so background ffmpeg captures appear automatically
      setTimeout(() => {
        if (!autoPreviewEnabled) return;
        const mode = (window.SearchState && window.SearchState.currentMode) || '';
        if (mode !== 'streams' || document.hidden) return;
        const ids = Array.from(visibleCardIds).slice(0, 8);
        if (ids.length) {
          console.debug('[StreamPreviewManager] Warmup snapshot refresh for ' + ids.length + ' visible cards');
        }
        ids.forEach((id, i) => {
          setTimeout(() => refreshPreviewById(id, false), i * 250);
        });
      }, 4500);
    }

    function toggleAutoPreviewRefresh(btnEl) {
      autoPreviewEnabled = !autoPreviewEnabled;
      if (btnEl) {
        btnEl.classList.toggle('active', autoPreviewEnabled);
        btnEl.innerHTML = autoPreviewEnabled
          ? '<i class="fas fa-camera"></i> Auto-Preview: ON'
          : '<i class="fas fa-camera-slash"></i> Auto-Preview: OFF';
      }
    }

    return {
      buildSnapshotUrl,
      refreshPreviewById,
      setupPreviewObserver,
      toggleAutoPreviewRefresh,
    };
  }

  return { create };
})();
