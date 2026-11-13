/**
 * netsearch_panel.js
 * Central Hub panel logic for Hecos Net Search System App.
 * Manages Net Search settings, Tor network status, and Resilient Search Endpoints, Nodes & Fallbacks.
 */
(function () {
  let _endpointsLoading = false;

  function _notify(msg, type = 'info') {
    if (typeof window.showToast === 'function') {
      window.showToast(msg, type);
    } else {
      console.log(`[NetSearch] [${type}] ${msg}`);
    }
  }

  function _ensureSearchEndpoints(cb) {
    if (window.SearchEndpoints) {
      return cb(window.SearchEndpoints);
    }
    // Try to load search_endpoints.js dynamically if not present
    let script = document.querySelector('script[src*="search_endpoints.js"]');
    if (!script) {
      script = document.createElement('script');
      script.src = '/hpm_plugin/net_search/web/static/js/search/search_endpoints.js';
      script.onload = () => {
        if (window.SearchEndpoints) cb(window.SearchEndpoints);
      };
      document.head.appendChild(script);
    } else {
      setTimeout(() => _ensureSearchEndpoints(cb), 100);
    }
  }

  function _ensureSearchSources(cb) {
    if (window.SearchSources) {
      return cb(window.SearchSources);
    }
    let script = document.querySelector('script[src*="search_sources.js"]');
    if (!script) {
      script = document.createElement('script');
      script.src = '/hpm_plugin/net_search/web/static/js/search/search_sources.js';
      script.onload = () => {
        if (window.SearchSources) cb(window.SearchSources);
      };
      document.head.appendChild(script);
    } else {
      setTimeout(() => _ensureSearchSources(cb), 100);
    }
  }

  window.updateNetSearchConfig = async function (keyPath, value) {
    try {
      const parts = keyPath.split('.');
      const payload = {};
      let curr = payload;
      for (let i = 0; i < parts.length - 1; i++) {
        curr[parts[i]] = {};
        curr = curr[parts[i]];
      }
      curr[parts[parts.length - 1]] = value;

      const res = await fetch('/hecos/api/plugins/net_search/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(r => r.json());

      if (res.ok) {
        _notify('Net Search setting saved', 'success');
        if (keyPath === 'local_only') {
          try {
            if (typeof localStorage !== 'undefined') {
              localStorage.setItem('hecos_netsearch_local_only', value ? 'true' : 'false');
            }
          } catch (e) { }
        }
        if (keyPath === 'tor.onion_action') {
          const a = document.getElementById('search-tor-onion-action');
          const b = document.getElementById('endp-tor-onion-action');
          if (a) a.value = value;
          if (b) b.value = value;
        } else if (keyPath === 'tor.tor_browser_path') {
          const a = document.getElementById('search-tor-browser-path');
          const b = document.getElementById('endp-tor-browser-path');
          if (a) a.value = value;
          if (b) b.value = value;
        }
      } else {
        _notify('Failed to save Net Search setting: ' + (res.error || 'Unknown'), 'error');
      }
    } catch (e) {
      console.error('[NetSearchPanel] update error:', e);
    }
  };

  window.loadNetSearchPanelConfig = async function () {
    if (_endpointsLoading) return;
    _endpointsLoading = true;
    try {
      // 1. Fetch plugin config
      const cfgRes = await fetch('/hecos/api/plugins/net_search/config').then(r => r.json()).catch(() => null);
      const cfg = (cfgRes && cfgRes.config) ? cfgRes.config : {};

      // Master switch
      const masterSw = document.getElementById('search-master-enabled');
      if (masterSw) masterSw.checked = cfg.enabled !== false;

      // Privacy Shield (Local-Only Mode)
      const localOnlySw = document.getElementById('search-local-only-enabled');
      if (localOnlySw) localOnlySw.checked = cfg.local_only === true;

      // Tor settings
      const tor = cfg.tor || {};
      const torSw = document.getElementById('search-tor-enabled');
      if (torSw) torSw.checked = tor.enabled !== false;
      const socksInput = document.getElementById('search-tor-socks-port');
      if (socksInput) socksInput.value = tor.socks_port || 9055;
      const ctrlInput = document.getElementById('search-tor-control-port');
      if (ctrlInput) ctrlInput.value = tor.control_port || 9056;
      const onionAct = document.getElementById('search-tor-onion-action');
      if (onionAct) onionAct.value = tor.onion_action || 'hecos_viewer';
      const endpOnionAct = document.getElementById('endp-tor-onion-action');
      if (endpOnionAct) endpOnionAct.value = tor.onion_action || 'hecos_viewer';

      const torPath = document.getElementById('search-tor-browser-path');
      if (torPath) torPath.value = tor.tor_browser_path || '';
      const endpTorPath = document.getElementById('endp-tor-browser-path');
      if (endpTorPath) endpTorPath.value = tor.tor_browser_path || '';

      // SearXNG settings
      const sx = cfg.searxng || {};
      const sxSw = document.getElementById('search-searxng-enabled');
      if (sxSw) sxSw.checked = sx.enabled !== false;
      const sxUrl = document.getElementById('search-searxng-url');
      if (sxUrl) sxUrl.value = sx.url || 'http://127.0.0.1:8889';

      // Brave API key
      const braveKeyInput = document.getElementById('search-brave-api-key');
      if (braveKeyInput) braveKeyInput.value = cfg.brave_api_key || '';

      // File Hunter config (scope switches + 11 built-in source toggles)
      const fh = cfg.file_hunter || {};
      const fhSrc = fh.sources || {};
      const swClear = document.getElementById('fh-sw-include-clear');
      if (swClear) swClear.checked = fh.include_all_clear !== false;
      const swDark = document.getElementById('fh-sw-include-dark');
      if (swDark) swDark.checked = fh.include_all_dark !== false;
      const swDir = document.getElementById('fh-sw-include-directory');
      if (swDir) swDir.checked = fh.include_domain_directory !== false;

      const fhSourceKeys = [
        'dorks_web', 'arxiv', 'openalex', 'zenodo', 'openlibrary',
        'doaj', 'huggingface', 'github', 'npm', 'archive_org', 'wikimedia'
      ];
      fhSourceKeys.forEach(k => {
        const el = document.getElementById(`fh-src-${k}`);
        if (el) el.checked = fhSrc[k] !== false;
      });
      if (typeof window.refreshFileHunterCountBadge === 'function') {
        window.refreshFileHunterCountBadge();
      }

      // OSINT config (scope switches + 11 built-in source toggles)
      const os = cfg.osint || {};
      const osSrc = os.sources || {};
      const osClear = document.getElementById('osint-sw-include-clear');
      if (osClear) osClear.checked = os.include_all_clear !== false;
      const osDark = document.getElementById('osint-sw-include-dark');
      if (osDark) osDark.checked = os.include_all_dark !== false;
      const osDir = document.getElementById('osint-sw-include-directory');
      if (osDir) osDir.checked = os.include_domain_directory !== false;
      const osSherlockDb = document.getElementById('osint-sw-sherlock-db');
      if (osSherlockDb) osSherlockDb.checked = os.use_sherlock_db !== false;

      const osSourceKeys = [
        'people_dorks', 'github', 'gitlab', 'reddit', 'hackernews',
        'wikipedia', 'wikidata', 'gravatar', 'keybase', 'archive_org', 'crtsh'
      ];
      osSourceKeys.forEach(k => {
        const el = document.getElementById(`osint-src-${k}`);
        if (el) el.checked = osSrc[k] !== false;
      });
      if (typeof window.refreshOsintCountBadge === 'function') {
        window.refreshOsintCountBadge();
      }

      // Defaults
      const timeoutInput = document.getElementById('search-timeout');
      if (timeoutInput) timeoutInput.value = cfg.timeout || 10;
      const limitInput = document.getElementById('search-limit');
      if (limitInput) limitInput.value = cfg.limit || 25;

      // Check Tor status badge
      window.checkTorStatusBadge();

      // 2. Fetch endpoints and populate full card editor
      const epRes = await fetch('/api/hsearch/endpoints').then(r => r.json()).catch(() => null);
      if (epRes && epRes.ok && epRes.endpoints) {
        _ensureSearchEndpoints((SE) => {
          window.renderNetSearchEndpointsUI(epRes.endpoints, tor);
        });
      }

      // 3. Load automated/manual source compilations list
      _ensureSearchSources((SS) => {
        SS.load();
      });
    } catch (err) {
      console.warn('[NetSearchPanel] load error:', err);
    } finally {
      _endpointsLoading = false;
    }
  };

  window.renderNetSearchEndpointsUI = function (ep, torCfg = {}) {
    _ensureSearchEndpoints((SE) => {
      const sx = ep.searxng || {};
      const archives = ep.archives || {};
      const customTorEngines = Array.isArray(ep.custom_onion_engines) ? ep.custom_onion_engines : [];
      const customClearEngines = Array.isArray(ep.custom_clear_engines) ? ep.custom_clear_engines : [];
      const customNodes = Array.isArray(ep.custom_nodes) ? ep.custom_nodes : [];
      const fallbacks = Array.isArray(sx.fallbacks) ? sx.fallbacks : [];

      SE.populateSearxngLocal('endp-searxng-local-wrap', sx);
      const sxEngines = SE.populateSearxngEngines('endp-searxng-engines-wrap', sx);
      SE.populateFallbacks('endp-searxng-fallbacks-wrap', fallbacks, customNodes);
      SE.populateTorEngines('endp-tor-engines-wrap', ep, true);

      // 4. Open Archives & Repositories (structured built-in + custom archives)
      const customArchives = Array.isArray(archives.custom_archives) ? archives.custom_archives : [];
      const archWrap = document.getElementById('endp-archives-wrap');
      if (archWrap) {
        archWrap.innerHTML = '';
        const aoNode = (archives.archive_org_node && typeof archives.archive_org_node === 'object')
          ? archives.archive_org_node
          : SE.decomposeUrl(archives.archive_org || 'https://archive.org/advancedsearch.php', 'Internet Archive', 'https');
        aoNode.id = 'endp_archive_org';
        aoNode.enabled = archives.archive_org_enabled !== false && aoNode.enabled !== false;
        archWrap.insertAdjacentHTML('beforeend', SE.renderCard(aoNode, {
          typeBadge: 'ARCHIVE ADAPTER',
          isDeletable: false,
          key: 'archive_org',
          category: 'files'
        }));

        const wmNode = (archives.wikimedia_node && typeof archives.wikimedia_node === 'object')
          ? archives.wikimedia_node
          : SE.decomposeUrl(archives.wikimedia_commons || 'https://commons.wikimedia.org/w/api.php', 'Wikimedia Commons', 'https');
        wmNode.id = 'endp_wikimedia_commons';
        wmNode.enabled = archives.wikimedia_enabled !== false && wmNode.enabled !== false;
        archWrap.insertAdjacentHTML('beforeend', SE.renderCard(wmNode, {
          typeBadge: 'ARCHIVE ADAPTER',
          isDeletable: false,
          key: 'wikimedia_commons',
          category: 'images'
        }));

        customArchives.forEach(ca => {
          SE.addEndpoint('endp-archives-wrap', ca, {
            typeBadge: 'CUSTOM ARCHIVE',
            isDeletable: true,
            key: 'custom_archive',
            showCategory: true,
            category: ca.category || 'general'
          });
        });
      }

      // 5. Legacy Custom Nodes wrapper support (merged into SearXNG fallback list in 4-Tab UI)
      const customWrap = document.getElementById('endp-custom-nodes-wrap');
      if (customWrap) {
        customWrap.innerHTML = '';
        customNodes.forEach(cn => {
          SE.addEndpoint('endp-custom-nodes-wrap', cn, {
            typeBadge: 'CUSTOM NODE',
            isDeletable: true,
            key: 'custom_node',
            category: 'custom'
          });
        });
      }

      // 5b. Populate Custom Clearnet / OpenSearch Engines
      const customClearWrap = document.getElementById('endp-custom-clear-wrap');
      if (customClearWrap) {
        customClearWrap.innerHTML = '';
        customClearEngines.forEach(cce => {
          SE.addEndpoint('endp-custom-clear-wrap', cce, {
            typeBadge: 'OPENSEARCH / WEB',
            isDeletable: true,
            key: 'custom_clear',
            showCategory: true,
            category: cce.category || 'general'
          });
        });
      }

      // 6. Update counts on section badges & tab headers
      const fbCount = document.getElementById('badge-searxng-fallbacks-count');
      const totalFallbackNodes = fallbacks.length + customNodes.length;
      if (fbCount) fbCount.textContent = `${totalFallbackNodes} Nodes`;

      const torCount = document.getElementById('badge-tor-engines-count');
      const totalTor = 10 + customTorEngines.length;
      if (torCount) torCount.textContent = `${totalTor} Engines`;

      const customCount = document.getElementById('badge-custom-nodes-count');
      if (customCount) customCount.textContent = `${customNodes.length} Nodes`;

      const customClearCount = document.getElementById('badge-custom-clear-count');
      if (customClearCount) customClearCount.textContent = `${customClearEngines.length} Engines`;

      const archivesCount = document.getElementById('badge-archives-count');
      const totalArchives = 2 + customArchives.length;
      if (archivesCount) archivesCount.textContent = `${totalArchives} Archives`;

      window.updateNetSearchTabCounts && window.updateNetSearchTabCounts({
        searxng: sxEngines.length + totalFallbackNodes,
        web: customClearEngines.length + totalArchives,
        dark: totalTor
      });
    });
  };

  window.updateNetSearchTabCounts = function (epCounts) {
    const counts = epCounts || {};
    if (typeof counts.searxng === 'number') {
      const el = document.getElementById('badge-tab-searxng-count');
      if (el) el.textContent = String(counts.searxng);
    }
    if (typeof counts.web === 'number') {
      const el = document.getElementById('badge-tab-web-count');
      if (el) el.textContent = String(counts.web);
    }
    if (typeof counts.dark === 'number') {
      const el = document.getElementById('badge-tab-dark-count');
      if (el) el.textContent = String(counts.dark);
    }
  };

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

  window.switchNetSearchEndpointTab = function (tabName) {
    const valid = ['searxng', 'web', 'dark', 'files', 'osint', 'domains'];
    const target = valid.includes(tabName) ? tabName : 'searxng';
    document.querySelectorAll('#netsearch-endpoints-manager-container .ns-tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.nsTab === target);
    });
    document.querySelectorAll('#netsearch-endpoints-manager-container .ns-tab-pane').forEach(pane => {
      pane.classList.toggle('active', pane.id === `ns-tab-pane-${target}`);
    });
    if (window.SearchSources && typeof window.SearchSources.setActiveTab === 'function') {
      window.SearchSources.setActiveTab(target);
    }
  };

  window.toggleEndpointSection = function (triggerEl, bodyId, forceExpand) {
    const body = document.getElementById(bodyId);
    if (!body) return;
    const isCurrentlyHidden = (body.style.display === 'none');
    const shouldShow = (typeof forceExpand === 'boolean') ? forceExpand : isCurrentlyHidden;

    body.style.display = shouldShow ? '' : 'none';

    // Find corresponding toggle button in the group
    const group = body.closest('.endpoint-group');
    const btn = group ? group.querySelector('.btn-group-toggle') : null;
    if (btn) {
      btn.innerHTML = shouldShow ? '<i class="fas fa-minus"></i>' : '<i class="fas fa-plus"></i>';
      btn.title = shouldShow ? 'Collapse Section (-)' : 'Expand Section (+)';
      btn.setAttribute('aria-expanded', shouldShow ? 'true' : 'false');
    }
  };

  window.toggleAllEndpointSections = function (expand = true) {
    const activePane = document.querySelector('#netsearch-endpoints-manager-container .ns-tab-pane.active');
    const root = activePane || document.getElementById('netsearch-endpoints-manager-container');
    if (!root) return;
    const groups = root.querySelectorAll('.endpoint-group');
    groups.forEach(g => {
      const body = g.querySelector('.endpoint-group-body');
      const btn = g.querySelector('.btn-group-toggle');
      if (body) {
        body.style.display = expand ? '' : 'none';
        if (btn) {
          btn.innerHTML = expand ? '<i class="fas fa-minus"></i>' : '<i class="fas fa-plus"></i>';
          btn.title = expand ? 'Collapse Section (-)' : 'Expand Section (+)';
          btn.setAttribute('aria-expanded', expand ? 'true' : 'false');
        }
      }
    });
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

  window.addSearxngFallbackNode = function () {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('searxng');
    window.toggleEndpointSection(null, 'endp-searxng-fallbacks-body', true);
    _ensureSearchEndpoints((SE) => SE.addPresetEndpoint('searxng_fallback'));
  };

  window.addCustomTorEngineNode = function () {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('dark');
    window.toggleEndpointSection(null, 'endp-tor-engines-body', true);
    _ensureSearchEndpoints((SE) => SE.addPresetEndpoint('custom_tor'));
  };

  window.addCustomSearchNode = function () {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('searxng');
    window.toggleEndpointSection(null, 'endp-searxng-fallbacks-body', true);
    _ensureSearchEndpoints((SE) => SE.addPresetEndpoint('custom_node', 'endp-searxng-fallbacks-wrap'));
  };

  window.addCustomClearEngineNode = function () {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('web');
    window.toggleEndpointSection(null, 'endp-custom-clear-body', true);
    _ensureSearchEndpoints((SE) => SE.addPresetEndpoint('custom_clear'));
  };

  window.addCustomArchiveNode = function () {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('web');
    window.toggleEndpointSection(null, 'endp-archives-body', true);
    _ensureSearchEndpoints((SE) => SE.addPresetEndpoint('custom_archive'));
  };

  window.updateSearxngEnginesCount = function () {
    const countBadge = document.getElementById('badge-searxng-engines-count');
    if (!countBadge) return;
    const cards = document.querySelectorAll('#endp-searxng-engines-wrap .searxng-engine-card');
    let active = 0;
    cards.forEach(c => {
      if (c.querySelector('.engine-enabled-checkbox')?.checked) active++;
    });
    countBadge.textContent = `${cards.length} Engines (${active} Active)`;
  };

  window.addSearxngEngineNode = function (presetData) {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('searxng');
    window.toggleEndpointSection(null, 'endp-searxng-engines-body', true);
    _ensureSearchEndpoints((SE) => {
      SE.addSearxngEngine('endp-searxng-engines-wrap', presetData || {
        name: '',
        label: '',
        category: 'general',
        enabled: true
      });
    });
  };

  window.quickAddSearxngEngine = function (name, label, category) {
    window.toggleEndpointSection(null, 'endp-searxng-engines-body', true);
    // Check if engine with this name already exists in wrap
    const existing = document.querySelector(`#endp-searxng-engines-wrap .searxng-engine-card input.engine-name-input[value="${name}"]`);
    if (existing) {
      const card = existing.closest('.searxng-engine-card');
      const cb = card.querySelector('.engine-enabled-checkbox');
      if (cb && !cb.checked) {
        cb.checked = true;
        _ensureSearchEndpoints(SE => SE.syncEngineCard(card.dataset.id));
        _notify(`Activated existing engine: ${label}`, 'info');
      } else {
        _notify(`Engine ${label} is already configured and active.`, 'info');
      }
      card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      return;
    }
    window.addSearxngEngineNode({ name, label, category, enabled: true });
    _notify(`Added ${label} to aggregated engines. Click 'Save Endpoints' to apply.`, 'success');
  };

  window.saveEndpointsFromUI = async function () {
    _ensureSearchEndpoints(async (SE) => {
      const { localItem, payload } = SE.collectTorAndSearxngPayload();

      // Custom Clearnet / OpenSearch Engines
      const customClearEngines = [];
      document.querySelectorAll('#endp-custom-clear-wrap .endpoint-card').forEach(c => {
        const item = SE.collectCard(c);
        if (item && (item.host || item.url)) {
          if (!item.search_template) {
            item.search_template = (item.url && item.url.includes('{q}')) ? item.url : ((item.url || '').replace(/\/$/, '') + '/search?q={q}');
          }
          customClearEngines.push(item);
        }
      });

      // Open Archives & Repositories (built-in cards + custom archives)
      let archiveOrgNode = null;
      let wikimediaNode = null;
      const customArchives = [];
      document.querySelectorAll('#endp-archives-wrap .endpoint-card').forEach(c => {
        const item = SE.collectCard(c);
        if (!item) return;
        if (item.key === 'archive_org') {
          archiveOrgNode = item;
        } else if (item.key === 'wikimedia_commons') {
          wikimediaNode = item;
        } else if (item.host || item.url) {
          if (!item.search_template) {
            item.search_template = (item.url && item.url.includes('{q}')) ? item.url : ((item.url || '').replace(/\/$/, '') + '?q={q}');
          }
          customArchives.push(item);
        }
      });

      payload.archives = {
        archive_org: archiveOrgNode?.url || 'https://archive.org/advancedsearch.php',
        archive_org_enabled: archiveOrgNode ? archiveOrgNode.enabled !== false : true,
        archive_org_node: archiveOrgNode,
        wikimedia_commons: wikimediaNode?.url || 'https://commons.wikimedia.org/w/api.php',
        wikimedia_enabled: wikimediaNode ? wikimediaNode.enabled !== false : true,
        wikimedia_node: wikimediaNode,
        custom_archives: customArchives
      };
      payload.custom_clear_engines = customClearEngines;

      try {
        const res = await fetch('/api/hsearch/endpoints', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }).then(r => r.json());

        if (res.ok) {
          _notify('Search endpoints saved successfully!', 'success');
          // Also persist primary SearXNG URL if modified
          if (localItem && localItem.url) {
            window.updateNetSearchConfig('searxng.url', localItem.url);
          }
          // Also persist Tor onion action and Tor browser path if present
          const curAction = document.getElementById('endp-tor-onion-action')?.value || document.getElementById('search-tor-onion-action')?.value;
          if (curAction) window.updateNetSearchConfig('tor.onion_action', curAction);
          const curPath = (document.getElementById('endp-tor-browser-path')?.value || document.getElementById('search-tor-browser-path')?.value || '').trim();
          if (curPath) window.updateNetSearchConfig('tor.tor_browser_path', curPath);
        } else {
          _notify('Failed to save endpoints: ' + (res.error || 'Unknown error'), 'error');
        }
      } catch (e) {
        _notify('Error saving endpoints: ' + e.message, 'error');
      }
    });
  };

  window.resetEndpointsFromUI = async function () {
    if (!confirm('Reset all search endpoints and fallback pools to factory defaults?')) return;
    try {
      const res = await fetch('/api/hsearch/endpoints/reset', { method: 'POST' }).then(r => r.json());
      if (res.ok) {
        _notify('Endpoints reset to factory defaults', 'success');
        window.loadNetSearchPanelConfig();
      } else {
        _notify('Reset failed: ' + (res.error || 'Unknown error'), 'error');
      }
    } catch (e) {
      _notify('Error resetting endpoints: ' + e.message, 'error');
    }
  };

  window.reloadNetSearchEndpoints = function () {
    window.loadNetSearchPanelConfig();
  };

  window.populateNetSearchPanelUI = window.loadNetSearchPanelConfig;

  // React to hashchange (Central Hub navigation)
  window.addEventListener('hashchange', () => {
    if (window.location.hash === '#netsearch' || window.location.hash === '#tab-netsearch') {
      window.loadNetSearchPanelConfig();
    }
  });

  // Run on DOM ready or immediate if already loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', window.loadNetSearchPanelConfig);
  } else {
    window.loadNetSearchPanelConfig();
  }
})();
