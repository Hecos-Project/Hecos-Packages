/**
 * cyber_map_bus.js
 * Decoupled real-time event bridge between Net Search (/search) and detached Cyber Map windows (/search/cyber_map).
 * Uses DOM CustomEvent + BroadcastChannel with localStorage fallback.
 */
(function () {
  const CHANNEL_NAME = 'hecos_cyber_map_channel';
  const STORAGE_KEY = 'hecos_cyber_map_sync_msg';
  const listeners = new Set();
  const _seenRemoteTs = new Set();
  let _msgSeq = 0;

  let bc = null;
  if (typeof BroadcastChannel !== 'undefined') {
    try {
      bc = new BroadcastChannel(CHANNEL_NAME);
      bc.onmessage = (ev) => {
        if (ev && ev.data) {
          _dispatchLocal(ev.data, true);
        }
      };
    } catch (_e) {
      bc = null;
    }
  }

  window.addEventListener('storage', (ev) => {
    if (ev.key === STORAGE_KEY && ev.newValue) {
      try {
        const parsed = JSON.parse(ev.newValue);
        if (parsed && parsed.payload) {
          _dispatchLocal(parsed.payload, true);
        }
      } catch (_e) { /* ignore */ }
    }
  });

  window.addEventListener('hecos:cybermap:event', (ev) => {
    if (ev && ev.detail) {
      publish(ev.detail, false);
    }
  });

  function _dispatchLocal(msg, fromRemote) {
    if (fromRemote && msg && msg._ts) {
      if (_seenRemoteTs.has(msg._ts)) return;
      _seenRemoteTs.add(msg._ts);
      if (_seenRemoteTs.size > 100) _seenRemoteTs.clear();
    }
    // Handle snapshot request from a detached Cyber Map window when running on /search
    if (fromRemote && msg && msg.type === 'REQUEST_SNAPSHOT' && window.SearchState) {
      const st = window.SearchState;
      const snapshot = {
        type: 'SYNC_SNAPSHOT',
        query: st.currentQuery || '',
        mode: st.currentMode || 'clear',
        sessionId: st.activeSessionId || st.currentSessionId || null,
        localOnly: Boolean(st.localOnly),
        results: Array.isArray(st.results) ? st.results.slice(0, 500) : [],
        engineStats: st.engineStats || {}
      };
      publish(snapshot, true);
      return;
    }

    // Handle reverse command: standalone Cyber Map wants /search to filter by a host
    if (fromRemote && msg && msg.type === 'FILTER_HOST_IN_SEARCH' && window.SearchState) {
      const host = String(msg.host || '').trim();
      const refineInput = document.getElementById('results-refine-input');
      if (refineInput && host) {
        refineInput.value = `domain:${host}`;
        refineInput.dispatchEvent(new Event('input', { bubbles: true }));
        window.focus();
      }
      return;
    }

    listeners.forEach((cb) => {
      try {
        cb(msg, fromRemote);
      } catch (err) {
        console.warn('[CyberMapBus] Listener error:', err);
      }
    });
  }

  function publish(msg, broadcast = true) {
    if (!msg || typeof msg !== 'object') return;
    if (!msg._ts) msg._ts = `${Date.now()}_${++_msgSeq}`;
    _dispatchLocal(msg, false);
    if (!broadcast) return;

    if (bc) {
      try {
        bc.postMessage(msg);
      } catch (_e) { /* ignore oversized / clone error */ }
    }
    try {
      // Compact summary fallback for storage event
      const compact = msg.type === 'SYNC_SNAPSHOT'
        ? Object.assign({}, msg, { results: (msg.results || []).slice(0, 150) })
        : msg;
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ ts: Date.now(), payload: compact }));
    } catch (_e) { /* ignore quota */ }
  }

  function emit(type, data) {
    publish(Object.assign({ type }, data || {}), true);
  }

  function subscribe(cb) {
    if (typeof cb === 'function') listeners.add(cb);
    return () => listeners.delete(cb);
  }

  function requestSnapshot() {
    publish({ type: 'REQUEST_SNAPSHOT' }, true);
  }

  window.CyberMapBus = {
    emit,
    publish,
    subscribe,
    requestSnapshot
  };
})();
