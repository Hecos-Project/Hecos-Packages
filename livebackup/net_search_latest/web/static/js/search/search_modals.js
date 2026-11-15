/**
 * search_modals.js
 * Modals controller for Components management, Tor circuit control, and Search Endpoints editor in Deep Search.
 */
(function() {
  const state = window.SearchState;
  const api = window.SearchAPI;

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ── Tor Status & Refresh ───────────────────────────────────────────────────
  async function refreshTorStatus() {
    const torDot = document.getElementById('tor-dot');
    const torLabel = document.getElementById('tor-label');
    const torStatusPill = document.getElementById('tor-status-pill');
    if (!api || !api.getTorStatus) return;

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
        if (torLabel) torLabel.innerText = `Tor Online (${res.port || 9055})`;
        if (torStatusPill) {
          torStatusPill.className = 'badge-pill badge-ok';
          torStatusPill.title = `Tor IP: ${res.ip} (Port ${res.port})`;
        }
      } else {
        if (torDot) {
          torDot.className = 'dot';
          torDot.style.background = 'var(--muted)';
        }
        if (torLabel) torLabel.innerText = 'Tor Offline';
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
      if (torLabel) torLabel.innerText = 'Tor Offline';
      if (torStatusPill) {
        torStatusPill.className = 'badge-pill badge-neutral';
      }
    }
  }

  // ── Modals & Components Management ─────────────────────────────────────────
  const componentsModal = document.getElementById('components-modal');

  function openComponentsModal() {
    const modal = document.getElementById('components-modal');
    if (modal) modal.classList.add('open');
    loadComponentsList();
  }

  function switchComponentsModalTab(tab) {
    loadComponentsList();
  }

  function closeAllModals() {
    const cModal = document.getElementById('components-modal');
    const bModal = document.getElementById('bookmarks-modal');
    if (cModal) cModal.classList.remove('open');
    if (bModal) bModal.classList.remove('open');
  }

  async function loadComponentsList() {
    const listEl = document.getElementById('components-list');
    if (!listEl || !api || !api.getComponents) return;
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
                  ${c.is_running ? ` • <span style="color:var(--accent-cyan); font-weight:600;"><i class="fas fa-circle" style="font-size:8px;"></i> Running${isSearxng ? ' (127.0.0.1:8889)' : ''}</span>` : ''}
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

  async function installComponent(id) {
    alert(`Starting installation of ${id}... Please wait.`);
    const res = await api.installComponent(id);
    if (res.ok) {
      alert(`Installation of ${id} completed.`);
      loadComponentsList();
      refreshTorStatus();
    } else {
      alert(`Installation error: ${res.message || res.error}`);
    }
  }

  async function uninstallComponent(id) {
    if (!confirm(`Are you sure you want to uninstall ${id}?`)) return;
    const res = await api.uninstallComponent(id);
    alert(res.ok ? 'Component uninstalled.' : `Error: ${res.message}`);
    loadComponentsList();
    refreshTorStatus();
  }

  async function startComponent(id) {
    const res = await api.startComponent(id);
    alert(res.ok ? 'Component started successfully.' : `Error: ${res.message}`);
    loadComponentsList();
    refreshTorStatus();
  }

  async function stopComponent(id) {
    const res = await api.stopComponent(id);
    alert(res.ok ? 'Component stopped.' : `Error: ${res.message}`);
    loadComponentsList();
    refreshTorStatus();
  }

  async function torNewCircuit() {
    const res = await api.torNewCircuit();
    alert(res.ok ? 'New Tor identity requested successfully!' : `Error: ${res.message}`);
    refreshTorStatus();
  }

  // ── Resilient Endpoints & Search Nodes UI ──────────────────────────────────
  async function loadEndpointsList() {
    const el = document.getElementById('endpoints-list');
    if (!el || !api || !api.getEndpoints) return;
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
      const archives = ep.archives || {};
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

        <!-- 2b. SearXNG Aggregated Search Engines Registry -->
        <div class="endpoint-group" id="searxng-engine-registry-group">
          <div class="endpoint-group-header">
            <span class="endpoint-group-title"><i class="fas fa-layer-group" style="color:var(--accent-cyan);"></i> SearXNG Engine Registry</span>
            <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
              <button type="button" class="btn btn-sm btn-secondary" style="border-radius:6px; font-size:11px; padding:3px 9px;" onclick="window.addSearxngEngineNode()">
                <i class="fas fa-plus"></i> Add Engine
              </button>
              <button type="button" class="btn btn-sm btn-secondary" style="border-radius:6px; font-size:11px; padding:3px 9px;" onclick="window.openEngineImportModal()">
                <i class="fas fa-file-import"></i> Import List
              </button>
              <button type="button" class="btn btn-sm btn-secondary" style="border-radius:6px; font-size:11px; padding:3px 9px;" onclick="window.exportEnginesList()">
                <i class="fas fa-file-export"></i> Export
              </button>
              <button type="button" class="btn btn-sm btn-secondary" style="border-radius:6px; font-size:11px; padding:3px 9px;" onclick="window.syncEnginesWithDaemon()" title="Re-sync settings.yml with SearXNG daemon">
                <i class="fas fa-sync-alt"></i> Sync Daemon
              </button>
            </div>
          </div>
          <p style="font-size:11px; color:var(--muted); margin-bottom:8px;">
            Configure and enable/disable individual search engines aggregated by the local SearXNG daemon across ClearWeb, News, Media, Science, IT, and Torrents.
          </p>
          
          <!-- Category Filter Bar & Search Input -->
          <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:10px; flex-wrap:wrap; background:var(--bg3); padding:8px 12px; border-radius:8px; border:1px solid var(--border);">
            <div style="display:flex; align-items:center; gap:5px; flex-wrap:wrap;" id="engine-cat-filter-chips">
              <button type="button" class="btn btn-sm btn-primary engine-cat-chip" data-cat="all" onclick="window.filterEngineRegistryCat('all', this)" style="padding:2px 8px; font-size:10.5px; border-radius:12px;">All</button>
              <button type="button" class="btn btn-sm btn-secondary engine-cat-chip" data-cat="general" onclick="window.filterEngineRegistryCat('general', this)" style="padding:2px 8px; font-size:10.5px; border-radius:12px;">Web</button>
              <button type="button" class="btn btn-sm btn-secondary engine-cat-chip" data-cat="news" onclick="window.filterEngineRegistryCat('news', this)" style="padding:2px 8px; font-size:10.5px; border-radius:12px;">News</button>
              <button type="button" class="btn btn-sm btn-secondary engine-cat-chip" data-cat="images" onclick="window.filterEngineRegistryCat('images', this)" style="padding:2px 8px; font-size:10.5px; border-radius:12px;">Images</button>
              <button type="button" class="btn btn-sm btn-secondary engine-cat-chip" data-cat="videos" onclick="window.filterEngineRegistryCat('videos', this)" style="padding:2px 8px; font-size:10.5px; border-radius:12px;">Videos</button>
              <button type="button" class="btn btn-sm btn-secondary engine-cat-chip" data-cat="music" onclick="window.filterEngineRegistryCat('music', this)" style="padding:2px 8px; font-size:10.5px; border-radius:12px;">Music</button>
              <button type="button" class="btn btn-sm btn-secondary engine-cat-chip" data-cat="science" onclick="window.filterEngineRegistryCat('science', this)" style="padding:2px 8px; font-size:10.5px; border-radius:12px;">Science</button>
              <button type="button" class="btn btn-sm btn-secondary engine-cat-chip" data-cat="it" onclick="window.filterEngineRegistryCat('it', this)" style="padding:2px 8px; font-size:10.5px; border-radius:12px;">IT / Code</button>
              <button type="button" class="btn btn-sm btn-secondary engine-cat-chip" data-cat="social media" onclick="window.filterEngineRegistryCat('social media', this)" style="padding:2px 8px; font-size:10.5px; border-radius:12px;">Social</button>
              <button type="button" class="btn btn-sm btn-secondary engine-cat-chip" data-cat="files" onclick="window.filterEngineRegistryCat('files', this)" style="padding:2px 8px; font-size:10.5px; border-radius:12px;">Files &amp; Dorks</button>
            </div>
            <div style="display:flex; align-items:center; gap:6px;">
              <input type="text" id="engine-registry-search" placeholder="Search engine..." style="height:26px; font-size:11px; padding:0 8px; border-radius:6px; border:1px solid var(--border); background:var(--bg0); color:var(--text); width:120px;" oninput="window.filterEngineRegistrySearch(this.value)">
              <button type="button" class="btn btn-sm btn-secondary" style="font-size:10.5px; padding:2px 7px;" onclick="window.toggleAllEnginesInRegistry(true)">Enable All</button>
              <button type="button" class="btn btn-sm btn-secondary" style="font-size:10.5px; padding:2px 7px;" onclick="window.toggleAllEnginesInRegistry(false)">Disable All</button>
            </div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; font-size:11px; color:var(--muted); margin-bottom:6px;">
            <span id="engine-registry-stats"><i class="fas fa-layer-group"></i> Loading engines...</span>
          </div>

          <!-- Engines Scroll Container -->
          <div id="endp-searxng-engines-wrap" style="display:flex; flex-direction:column; gap:6px; max-height:280px; overflow-y:auto; padding-right:4px;"></div>
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

      SE.populateSearxngLocal('endp-searxng-local-wrap', sx);
      SE.populateFallbacks('endp-searxng-fallbacks-wrap', fallbacks);
      SE.populateSearxngEngines('endp-searxng-engines-wrap', sx);
      SE.populateTorEngines('endp-tor-engines-wrap', ep, true);

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

  function addSearxngFallbackNode() {
    window.SearchEndpoints?.addPresetEndpoint('searxng_fallback');
  }

  function addCustomTorEngineNode() {
    window.SearchEndpoints?.addPresetEndpoint('custom_tor');
  }

  function addCustomSearchNode() {
    window.SearchEndpoints?.addPresetEndpoint('custom_node');
  }

  async function saveEndpointsFromUI() {
    const SE = window.SearchEndpoints;
    if (!SE) return;

    const { payload } = SE.collectTorAndSearxngPayload();
    const archiveOrg = (document.getElementById('endp-archive-org')?.value || '').trim();
    const wikimedia = (document.getElementById('endp-wikimedia')?.value || '').trim();
    payload.archives = {
      archive_org: archiveOrg || 'https://archive.org/advancedsearch.php',
      wikimedia_commons: wikimedia || 'https://commons.wikimedia.org/w/api.php'
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
  }

  async function autoDetectTorBrowser() {
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
  }

  async function resetEndpointsFromUI() {
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
  }

  function updateSearxngEnginesCount() {
    const cards = document.querySelectorAll('#endp-searxng-engines-wrap .searxng-engine-card');
    let total = cards.length;
    let active = 0;
    cards.forEach(c => {
      const chk = c.querySelector('.engine-enabled-checkbox');
      if (chk && chk.checked) active++;
    });
    const statsEl = document.getElementById('engine-registry-stats');
    if (statsEl) {
      statsEl.innerHTML = `<i class="fas fa-layer-group" style="color:var(--accent-cyan);"></i> <strong>${active}</strong> active / <strong>${total}</strong> configured engines`;
    }
  }

  function addSearxngEngineNode() {
    if (!window.SearchEndpoints) return;
    window.SearchEndpoints.addSearxngEngine('endp-searxng-engines-wrap', {
      name: '',
      label: '',
      category: 'general',
      enabled: true
    });
    updateSearxngEnginesCount();
  }

  function filterEngineRegistryCat(cat, chipEl) {
    document.querySelectorAll('#engine-cat-filter-chips .engine-cat-chip').forEach(ch => {
      ch.className = 'btn btn-sm btn-secondary engine-cat-chip';
    });
    if (chipEl) chipEl.className = 'btn btn-sm btn-primary engine-cat-chip';

    const cards = document.querySelectorAll('#endp-searxng-engines-wrap .searxng-engine-card');
    const term = (document.getElementById('engine-registry-search')?.value || '').toLowerCase().trim();

    cards.forEach(c => {
      const cardCat = (c.querySelector('.engine-category-select')?.value || 'general').toLowerCase();
      const name = (c.querySelector('.engine-name-input')?.value || '').toLowerCase();
      const label = (c.querySelector('.engine-label-input')?.value || '').toLowerCase();

      const matchesCat = (cat === 'all' || cardCat === cat.toLowerCase());
      const matchesSearch = (!term || name.includes(term) || label.includes(term));

      c.style.display = (matchesCat && matchesSearch) ? 'block' : 'none';
    });
  }

  function filterEngineRegistrySearch(term) {
    const activeChip = document.querySelector('#engine-cat-filter-chips .btn-primary');
    const cat = activeChip ? activeChip.dataset.cat : 'all';
    filterEngineRegistryCat(cat, activeChip);
  }

  function toggleAllEnginesInRegistry(enableState) {
    const cards = document.querySelectorAll('#endp-searxng-engines-wrap .searxng-engine-card');
    cards.forEach(c => {
      if (c.style.display !== 'none') {
        const chk = c.querySelector('.engine-enabled-checkbox');
        if (chk) {
          chk.checked = enableState;
          const id = c.dataset.id;
          if (window.SearchEndpoints && id) {
            window.SearchEndpoints.syncEngineCard(id);
          }
        }
      }
    });
    updateSearxngEnginesCount();
  }

  function openEngineImportModal() {
    const modal = document.getElementById('engine-import-modal');
    if (modal) {
      modal.classList.add('open');
      const textarea = document.getElementById('engine-import-textarea');
      if (textarea) textarea.focus();
      const status = document.getElementById('engine-import-status');
      if (status) status.innerText = '';
    }
  }

  async function submitEngineImport() {
    const textarea = document.getElementById('engine-import-textarea');
    const statusEl = document.getElementById('engine-import-status');
    const val = textarea?.value?.trim();
    if (!val) {
      if (statusEl) statusEl.innerText = 'Please paste content to import.';
      return;
    }
    if (statusEl) statusEl.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Processing import...';

    try {
      const resp = await fetch('/api/hsearch/engines/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: val })
      });
      const data = await resp.json();
      if (data.ok) {
        if (statusEl) {
          statusEl.style.color = 'var(--accent-emerald, #10b981)';
          statusEl.innerText = `Imported: +${data.added} new, ${data.updated} updated. Total: ${data.total_engines} engines.`;
        }
        setTimeout(() => {
          document.getElementById('engine-import-modal')?.classList.remove('open');
          loadEndpointsList();
        }, 1200);
      } else {
        if (statusEl) {
          statusEl.style.color = 'var(--accent-rose, #f43f5e)';
          statusEl.innerText = 'Import failed: ' + (data.error || 'Unknown error');
        }
      }
    } catch (e) {
      if (statusEl) {
        statusEl.style.color = 'var(--accent-rose, #f43f5e)';
        statusEl.innerText = 'Network error: ' + e.message;
      }
    }
  }

  function exportEnginesList() {
    window.open('/api/hsearch/engines/export', '_blank');
  }

  async function syncEnginesWithDaemon() {
    try {
      const resp = await fetch('/api/hsearch/engines/sync', { method: 'POST' });
      const data = await resp.json();
      if (data.ok) {
        alert(`Synchronized ${data.total_synced} engines with SearXNG daemon.`);
      }
    } catch (e) {
      alert('Error syncing with daemon: ' + e.message);
    }
  }

    window.SearchModals = {
    refreshTorStatus,
    openComponentsModal,
    switchComponentsModalTab,
    closeAllModals,
    loadComponentsList,
    installComponent,
    uninstallComponent,
    startComponent,
    stopComponent,
    torNewCircuit,
    loadEndpointsList,
    addSearxngFallbackNode,
    addCustomTorEngineNode,
    addCustomSearchNode,
    saveEndpointsFromUI,
    autoDetectTorBrowser,
    resetEndpointsFromUI
  };

  // Global window bindings for HTML onclick handlers
  window.openComponentsModal = openComponentsModal;
  window.switchComponentsModalTab = switchComponentsModalTab;
  window.closeAllModals = closeAllModals;
  window.installComponent = installComponent;
  window.uninstallComponent = uninstallComponent;
  window.startComponent = startComponent;
  window.stopComponent = stopComponent;
  window.torNewCircuit = torNewCircuit;
  window.addSearxngFallbackNode = addSearxngFallbackNode;
  window.addSearxngFallback = addSearxngFallbackNode;
  window.addCustomTorEngineNode = addCustomTorEngineNode;
  window.addCustomTorEngine = addCustomTorEngineNode;
  window.addCustomSearchNode = addCustomSearchNode;
  window.saveEndpointsFromUI = saveEndpointsFromUI;
  window.autoDetectTorBrowser = autoDetectTorBrowser;
  window.resetEndpointsFromUI = resetEndpointsFromUI;
  window.refreshTorStatus = refreshTorStatus;
  window.updateSearxngEnginesCount = updateSearxngEnginesCount;
  window.addSearxngEngineNode = addSearxngEngineNode;
  window.filterEngineRegistryCat = filterEngineRegistryCat;
  window.filterEngineRegistrySearch = filterEngineRegistrySearch;
  window.toggleAllEnginesInRegistry = toggleAllEnginesInRegistry;
  window.openEngineImportModal = openEngineImportModal;
  window.submitEngineImport = submitEngineImport;
  window.exportEnginesList = exportEnginesList;
  window.syncEnginesWithDaemon = syncEnginesWithDaemon;
})();

