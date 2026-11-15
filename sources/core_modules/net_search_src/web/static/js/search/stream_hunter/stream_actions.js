/**
 * Stream Hunter Player, Probe, Playlist & Clipboard Actions
 * Extracted from stream_hunter_ui.js for modularity.
 */
window.StreamHunterActions = (function () {
  function create(ctx) {
    function _esc(str) {
      return ctx.escapeHtml ? ctx.escapeHtml(str) : String(str || '');
    }

    async function _postPlayVlc(payload, btnEl, busyHtml, okHtml, fallbackErr) {
      const origHtml = btnEl ? btnEl.innerHTML : null;
      if (btnEl) {
        btnEl.disabled = true;
        btnEl.innerHTML = busyHtml;
      }
      try {
        const resp = await fetch('/api/hsearch/streams/play_vlc', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        let data = {};
        try {
          data = await resp.json();
        } catch (_parseErr) {
          data = { ok: false, error: `${fallbackErr} (HTTP ${resp.status})` };
        }
        if (!resp.ok || !data.ok) {
          const errMsg = data.error || `${fallbackErr} (HTTP ${resp.status})`;
          console.warn('[StreamHunterUI] VLC launch failed:', errMsg);
          alert(errMsg);
          if (btnEl && origHtml !== null) btnEl.innerHTML = origHtml;
          return;
        }
        if (btnEl && origHtml !== null) {
          btnEl.innerHTML = okHtml;
          setTimeout(() => { btnEl.innerHTML = origHtml; }, 1800);
        }
      } catch (e) {
        console.warn('[StreamHunterUI] VLC launch error:', e);
        alert(`${fallbackErr}: ${e && e.message ? e.message : e}`);
        if (btnEl && origHtml !== null) btnEl.innerHTML = origHtml;
      } finally {
        if (btnEl) btnEl.disabled = false;
      }
    }

    async function openInVlc(streamUrl, title, btnEl = null) {
      await _postPlayVlc(
        { mode: 'single', stream_url: streamUrl, title: title || 'Hecos Live Stream' },
        btnEl,
        '<i class="fas fa-spinner fa-spin"></i> Launching...',
        '<i class="fas fa-check"></i> VLC Opened',
        'Could not launch VLC Desktop'
      );
    }

    function openInVlcById(id, btnEl = null) {
      const st = ctx.findStreamById(id);
      if (st) {
        openInVlc(st.stream_url, st.title, btnEl);
      }
    }

    async function openAllInVlcPlaylist(visible, btnEl = null) {
      if (!visible || !visible.length) return;
      await _postPlayVlc(
        { mode: 'playlist', streams: visible },
        btnEl,
        '<i class="fas fa-spinner fa-spin"></i> Building M3U...',
        '<i class="fas fa-check"></i> Playlist Sent',
        'Could not launch VLC playlist'
      );
    }

    function downloadM3uPlaylist(subfilter, country) {
      const input = document.getElementById('search-input');
      const q = input ? input.value.trim() : '';
      const cc = country === 'ALL' ? '' : (country || '');
      const url = `/api/hsearch/streams/playlist.m3u?q=${encodeURIComponent(q)}&subfilter=${encodeURIComponent(subfilter || 'all')}&country=${encodeURIComponent(cc)}`;
      window.open(url, '_blank');
    }

    function applyProbeToCard(st, probe) {
      if (!st || !probe) return;
      st.is_live = Boolean(probe.is_live);
      st.latency_ms = probe.latency_ms || 0;
      if (probe.bitrate && !st.bitrate) st.bitrate = probe.bitrate;
      if (probe.resolution && !st.resolution) st.resolution = probe.resolution;
      if (probe.now_playing) st.now_playing = probe.now_playing;

      const statusEl = document.getElementById(`sh-status-${st.id}`);
      if (statusEl) {
        statusEl.className = `sh-pill ${st.is_live ? 'sh-pill-live' : 'sh-pill-offline'}`;
        statusEl.textContent = st.is_live ? `● LIVE (${st.latency_ms}ms)` : '● OFFLINE';
      }
      const npEl = document.getElementById(`sh-np-${st.id}`);
      if (npEl && st.now_playing) {
        npEl.style.display = 'block';
        npEl.innerHTML = `<i class="fas fa-wave-square"></i> <span>${_esc(st.now_playing)}</span>`;
      }
    }

    async function probeSingleById(id) {
      const st = ctx.findStreamById(id);
      if (!st) return;
      const statusEl = document.getElementById(`sh-status-${st.id}`);
      if (statusEl) {
        statusEl.className = 'sh-pill sh-pill-ready';
        statusEl.textContent = '● PROBING...';
      }
      try {
        const resp = await fetch('/api/hsearch/streams/probe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: st.stream_url, timeout: 3.5 }),
        });
        const data = await resp.json();
        if (data && data.ok && data.probe) {
          applyProbeToCard(st, data.probe);
        }
      } catch (_e) {}
    }

    async function probeVisibleStreams(visible) {
      const batch = (visible || []).slice(0, 20);
      if (!batch.length) return;
      const btn = document.getElementById('sh-btn-probe-all');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Probing...';
      }

      try {
        const urls = batch.map(s => s.stream_url);
        const resp = await fetch('/api/hsearch/streams/probe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ urls, timeout: 3.0 }),
        });
        const data = await resp.json();
        if (data && data.ok && data.probes) {
          batch.forEach(st => {
            const p = data.probes[st.stream_url];
            if (p) applyProbeToCard(st, p);
          });
        }
      } catch (_e) {
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i class="fas fa-bolt"></i> Probe Online';
        }
      }
    }

    async function expandM3uById(id) {
      const st = ctx.findStreamById(id);
      if (!st) return;
      try {
        const resp = await fetch('/api/hsearch/streams/parse_m3u', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: st.stream_url }),
        });
        const data = await resp.json();
        if (data && data.ok && Array.isArray(data.streams) && data.streams.length > 0) {
          ctx.replaceExpandedStream(id, data.streams);
        }
      } catch (_e) {}
    }

    function copyUrlById(id, btnEl) {
      const st = ctx.findStreamById(id);
      if (!st) return;
      navigator.clipboard.writeText(st.stream_url).then(() => {
        if (btnEl) {
          const orig = btnEl.innerHTML;
          btnEl.innerHTML = '<i class="fas fa-check"></i> Copied';
          setTimeout(() => { btnEl.innerHTML = orig; }, 1200);
        }
      }).catch(() => {});
    }

    return {
      openInVlc,
      openInVlcById,
      openAllInVlcPlaylist,
      downloadM3uPlaylist,
      probeSingleById,
      probeVisibleStreams,
      expandM3uById,
      copyUrlById,
    };
  }

  return { create };
})();
