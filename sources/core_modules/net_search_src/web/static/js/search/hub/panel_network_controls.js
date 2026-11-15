/**
 * Central Hub Network Controls: Tor Diagnostics & Provider Source Toggles
 * Extracted from netsearch_panel.js for modularity.
 */
(function () {
  function _notify(msg, type = 'info') {
    if (typeof window._nsNotify === 'function') {
      window._nsNotify(msg, type);
    } else if (typeof window.showToast === 'function') {
      window.showToast(msg, type);
    } else {
      console.log(`[NetSearch] [${type}] ${msg}`);
    }
  }

  function _refreshSourceCountBadge(keys, prefix, tabBadgeId, secBadgeId) {
    let activeApis = 0;
    let totalFound = 0;
    keys.forEach(k => {
      const el = document.getElementById(`${prefix}-${k}`);
      if (el) {
        totalFound++;
        if (el.checked) activeApis++;
      }
    });
    const tabBadge = document.getElementById(tabBadgeId);
    if (tabBadge) tabBadge.textContent = String(totalFound ? activeApis : keys.length);
    const secBadge = document.getElementById(secBadgeId);
    if (secBadge) secBadge.textContent = `${totalFound ? activeApis : keys.length}/${totalFound || keys.length} Active`;
  }

  window.refreshFileHunterCountBadge = function () {
    _refreshSourceCountBadge([
      'dorks_web', 'arxiv', 'openalex', 'zenodo', 'openlibrary',
      'doaj', 'huggingface', 'github', 'npm', 'archive_org', 'wikimedia'
    ], 'fh-src', 'badge-tab-files-count', 'badge-fh-sources-active');
  };

  window.refreshOsintCountBadge = function () {
    _refreshSourceCountBadge([
      'people_dorks', 'github', 'gitlab', 'reddit', 'hackernews',
      'wikipedia', 'wikidata', 'gravatar', 'keybase', 'archive_org', 'crtsh'
    ], 'osint-src', 'badge-tab-osint-count', 'badge-osint-sources-active');
  };

  window.updateFileHunterSource = function (srcKey, enabled) {
    window.refreshFileHunterCountBadge();
    return window.updateNetSearchConfig(`file_hunter.sources.${srcKey}`, !!enabled);
  };

  window.updateOsintSource = function (srcKey, enabled) {
    window.refreshOsintCountBadge();
    return window.updateNetSearchConfig(`osint.sources.${srcKey}`, !!enabled);
  };

  window.updateStreamsTabBadgeCount = function () {
    const shKeys = [
      'iptv_builtin', 'iptv_org_api', 'radio_builtin', 'radio_browser_api',
      'webcams_builtin', 'searxng_dorks', 'sqlite_stream_store'
    ];
    let activeProviders = 0;
    shKeys.forEach(k => {
      const el = document.getElementById(`sh-src-${k}`);
      if (!el || el.checked) activeProviders++;
    });
    const manualCards = document.querySelectorAll('#endp-streams-nodes-wrap .endpoint-card').length;
    const nodesBadge = document.getElementById('badge-streams-nodes-count');
    if (nodesBadge) nodesBadge.textContent = `${manualCards} Nodes`;
    const tabBadge = document.getElementById('badge-tab-streams-count');
    if (tabBadge) tabBadge.textContent = String(activeProviders + manualCards);
  };

  window.updateStreamHunterSource = function (srcKey, enabled) {
    window.updateStreamsTabBadgeCount();
    return window.updateNetSearchConfig(`stream_hunter.sources.${srcKey}`, !!enabled);
  };

  window.checkTorStatusBadge = async function () {
    const badge = document.getElementById('tor-cfg-status-badge');
    if (!badge) return;
    try {
      const res = await fetch('/api/hsearch/tor_status').then(r => r.json());
      if (res.ok && res.tor_online) {
        badge.textContent = `Online (Port ${res.tor_port || 9055})`;
        badge.style.background = 'rgba(16, 185, 129, 0.15)';
        badge.style.color = '#34d399';
      } else {
        badge.textContent = 'Offline';
        badge.style.background = 'rgba(239, 68, 68, 0.15)';
        badge.style.color = '#f87171';
      }
    } catch (e) {
      badge.textContent = 'Check failed';
    }
  };

  window.torNewCircuit = async function () {
    try {
      const res = await fetch('/api/hsearch/tor_newnym', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
      }).then(r => r.json());
      if (res.ok) {
        _notify('New Tor identity (circuit) requested successfully!', 'success');
        window.checkTorStatusBadge();
      } else {
        _notify('Tor circuit request: ' + (res.message || res.error || 'Failed to switch identity'), 'warning');
      }
    } catch (e) {
      _notify('Error requesting new Tor circuit: ' + e.message, 'error');
    }
  };

  window.syncTorActionFromEndpoints = function (val) {
    const topSel = document.getElementById('search-tor-onion-action');
    if (topSel) topSel.value = val;
    window.updateNetSearchConfig('tor.onion_action', val);
  };

  window.syncTorPathFromEndpoints = function (val) {
    const topPath = document.getElementById('search-tor-browser-path');
    if (topPath) topPath.value = val;
    window.updateNetSearchConfig('tor.tor_browser_path', val);
  };

  window.detectTorBrowserPath = async function () {
    try {
      const res = await fetch('/api/hsearch/detect_tor_browser').then(r => r.json());
      if (res.ok && res.path) {
        const input = document.getElementById('search-tor-browser-path');
        if (input) input.value = res.path;
        const endpInput = document.getElementById('endp-tor-browser-path');
        if (endpInput) endpInput.value = res.path;
        window.updateNetSearchConfig('tor.tor_browser_path', res.path);
        _notify('Tor Browser detected: ' + res.path, 'success');
      } else {
        _notify('Tor Browser could not be detected automatically.', 'warning');
      }
    } catch (e) {
      _notify('Detection error: ' + e, 'error');
    }
  };
  window.autoDetectTorBrowser = window.detectTorBrowserPath;
})();
