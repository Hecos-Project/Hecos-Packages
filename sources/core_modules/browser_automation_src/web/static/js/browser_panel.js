  window.populateBrowserUI = function() {
      // Force init if completely missing so it persists
      if (!window.cfg.plugins) window.cfg.plugins = {};
      if (!window.cfg.plugins.BROWSER) {
          window.cfg.plugins.BROWSER = { enabled: true, browser_engine_mode: 'cdp_mode' };
          if (typeof window.saveConfig === 'function') {
              window.saveConfig(true);
          }
      }
      const bCfg = window.cfg.plugins.BROWSER;
      if (bCfg.browser_engine_mode !== 'cdp_mode' && bCfg.browser_engine_mode !== 'app_mode') {
          bCfg.browser_engine_mode = 'cdp_mode';
          if (typeof window.saveConfig === 'function') {
              window.saveConfig(true);
          }
      }
      const mode = bCfg.browser_engine_mode;
      
      const browserEl = document.getElementById('browser-enabled');
      if (browserEl) browserEl.checked = bCfg.enabled ?? true;
      
      const emApp = document.getElementById('em-app');
      if(emApp && mode === 'app_mode') emApp.checked = true;
      const emCdp = document.getElementById('em-cdp');
      if(emCdp && mode === 'cdp_mode') emCdp.checked = true;
      
      if(typeof window.updateModeUI === 'function') {
          window.updateModeUI();
      }
      
      const aCfg = window.cfg?.plugins?.AUTOMATION || {};
      const autoEnabled = aCfg.enabled ?? false;
      const autoEl = document.getElementById('automation-enabled');
      if (autoEl) autoEl.checked = autoEnabled;

      const cdpPort = document.getElementById('browser-cdp-port');
      if (cdpPort) cdpPort.value = bCfg.cdp_port || 9222;
      
      const headless = document.getElementById('browser-headless');
      if (headless) headless.checked = bCfg.headless ?? true;
      
      const blockAds = document.getElementById('browser-block-ads');
      if (blockAds) blockAds.checked = bCfg.block_ads ?? true;
      
      const startup = document.getElementById('browser-startup-url');
      if (startup) startup.value = bCfg.startup_url || '';
      
      const engine = document.getElementById('browser-engine');
      if (engine) engine.value = bCfg.browser_type || 'chromium';

      const navTimeout = document.getElementById('browser-nav-timeout');
      if (navTimeout) navTimeout.value = bCfg.nav_timeout || 30;

      const actionTimeout = document.getElementById('browser-action-timeout');
      if (actionTimeout) actionTimeout.value = bCfg.action_timeout || 5;

      const waitTimeout = document.getElementById('browser-wait-timeout');
      if (waitTimeout) waitTimeout.value = bCfg.wait_timeout || 8;

      const threadTimeout = document.getElementById('browser-thread-timeout');
      if (threadTimeout) threadTimeout.value = bCfg.thread_timeout || 60;

      const routingOverride = document.getElementById('browser-routing-override');
      if (routingOverride) {
          const overrides = window.cfg?.routing_overrides?.overrides || {};
          routingOverride.value = overrides.BROWSER || '';
      }

      // ── Deep Search Config Population ──
      const sCfg = bCfg.search || {};
      const torCfg = sCfg.tor || {};
      const searxCfg = sCfg.searxng || {};

      const masterEl = document.getElementById('search-master-enabled');
      if (masterEl && sCfg.enabled !== undefined) masterEl.checked = sCfg.enabled;

      const torEl = document.getElementById('search-tor-enabled');
      if (torEl && torCfg.enabled !== undefined) torEl.checked = torCfg.enabled;

       const torSocksEl = document.getElementById('search-tor-socks-port');
      if (torSocksEl && torCfg.socks_port) torSocksEl.value = torCfg.socks_port;

      const torCtrlEl = document.getElementById('search-tor-control-port');
      if (torCtrlEl && torCfg.control_port) torCtrlEl.value = torCfg.control_port;

      const onionActionEl = document.getElementById('search-tor-onion-action');
      if (onionActionEl && torCfg.onion_action) onionActionEl.value = torCfg.onion_action;

      const torBrowserPathEl = document.getElementById('search-tor-browser-path');
      if (torBrowserPathEl && torCfg.tor_browser_path) torBrowserPathEl.value = torCfg.tor_browser_path;

      const timeoutEl = document.getElementById('search-timeout');
      if (timeoutEl && sCfg.timeout) timeoutEl.value = sCfg.timeout;

      const limitEl = document.getElementById('search-limit');
      if (limitEl && sCfg.limit) limitEl.value = sCfg.limit;

      const searxUrlEl = document.getElementById('search-searxng-url');
      if (searxUrlEl && searxCfg.url) searxUrlEl.value = searxCfg.url;

      const searxEnabledEl = document.getElementById('search-searxng-enabled');
      if (searxEnabledEl && searxCfg.enabled !== undefined) searxEnabledEl.checked = searxCfg.enabled;

      // Authoritative sync from /api/hsearch/config
      fetch('/api/hsearch/config')
          .then(r => r.json())
          .then(data => {
              if (data && data.ok && data.config) {
                  const cfg = data.config;
                  if (bCfg) bCfg.search = cfg;
                  if (masterEl && cfg.enabled !== undefined) masterEl.checked = cfg.enabled;
                  if (torEl && cfg.tor && cfg.tor.enabled !== undefined) torEl.checked = cfg.tor.enabled;
                  if (torSocksEl && cfg.tor && cfg.tor.socks_port) torSocksEl.value = cfg.tor.socks_port;
                  if (torCtrlEl && cfg.tor && cfg.tor.control_port) torCtrlEl.value = cfg.tor.control_port;
                  if (onionActionEl && cfg.tor && cfg.tor.onion_action) onionActionEl.value = cfg.tor.onion_action;
                  if (torBrowserPathEl && cfg.tor && cfg.tor.tor_browser_path) torBrowserPathEl.value = cfg.tor.tor_browser_path;
                  if (timeoutEl && cfg.timeout) timeoutEl.value = cfg.timeout;
                  if (limitEl && cfg.limit) limitEl.value = cfg.limit;
                  if (searxUrlEl && cfg.searxng && cfg.searxng.url) searxUrlEl.value = cfg.searxng.url;
                  if (searxEnabledEl && cfg.searxng && cfg.searxng.enabled !== undefined) searxEnabledEl.checked = cfg.searxng.enabled;
              }
          })
          .catch(() => {});
                  if (searxUrlEl && cfg.searxng && cfg.searxng.url) searxUrlEl.value = cfg.searxng.url;
                  if (searxEnabledEl && cfg.searxng && cfg.searxng.enabled !== undefined) searxEnabledEl.checked = cfg.searxng.enabled;
              }
          })
          .catch(() => {});

      // Update Tor badge asynchronously
      const torBadge = document.getElementById('tor-cfg-status-badge');
      if (torBadge) {
          fetch('/api/hsearch/tor_status')
              .then(r => r.json())
              .then(d => {
                  if (d.ok) {
                      torBadge.innerText = `Online (${d.ip || 'Port ' + d.port})`;
                      torBadge.style.background = 'rgba(168,85,247,0.2)';
                      torBadge.style.color = '#c084fc';
                  } else {
                      torBadge.innerText = 'Offline';
                      torBadge.style.background = 'rgba(255,255,255,0.06)';
                      torBadge.style.color = 'var(--muted)';
                  }
              })
              .catch(() => {
                  if (torBadge) torBadge.innerText = 'Offline';
              });
      }

      // Dynamically fetch and display actual status of search components
      if (window.refreshSearchComponentsUI) {
          window.refreshSearchComponentsUI();
      }

      // Populate resilient endpoints in browser panel
      if (window.reloadBrowserPanelEndpoints) {
          window.reloadBrowserPanelEndpoints();
      }
  };

  window.refreshSearchComponentsUI = async function() {
      try {
          const res = await fetch('/api/hsearch/components').then(r => r.json());
          if (!res.ok || !res.components) return;
          res.components.forEach(c => {
              const el = document.getElementById(`comp-action-${c.id}`);
              if (el) {
                  if (c.is_installed) {
                      el.innerHTML = `
                          <div style="display:flex; align-items:center; gap:8px;">
                              <span style="font-size:11px; color:var(--accent-emerald, #10b981); font-weight:600;"><i class="fas fa-check-circle"></i> Installed</span>
                              <button class="btn btn-xs" style="opacity:0.6; padding:3px 7px;" onclick="window.installSearchComponent('${c.id}', this)" title="Reinstall / update">Reinstall</button>
                          </div>
                      `;
                  } else {
                      el.innerHTML = `
                          <button class="btn btn-xs btn-primary" onclick="window.installSearchComponent('${c.id}', this)">Install</button>
                      `;
                  }
              }
              if (c.id === 'tor_daemon') {
                  const instBtn = document.getElementById('tor-install-btn');
                  const startBtn = document.getElementById('tor-start-btn');
                  if (instBtn && startBtn) {
                      if (c.is_installed) {
                          instBtn.innerHTML = '<i class="fas fa-check"></i> Installed';
                          instBtn.disabled = true;
                          instBtn.style.opacity = '0.7';
                          startBtn.disabled = false;
                          startBtn.title = '';
                          if (c.is_running) {
                              startBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Daemon';
                              startBtn.className = 'btn btn-sm btn-danger';
                          } else {
                              startBtn.innerHTML = '<i class="fas fa-play"></i> Start Daemon';
                              startBtn.className = 'btn btn-sm btn-secondary';
                          }
                      } else {
                          instBtn.innerHTML = '<i class="fas fa-download"></i> Install Tor Daemon';
                          instBtn.disabled = false;
                          instBtn.style.opacity = '1';
                          startBtn.disabled = true;
                          startBtn.title = 'Install Tor daemon first';
                      }
                  }
              }
          });
      } catch (err) {
          console.warn('[BrowserPanel] Failed to refresh search components UI:', err);
      }
  };

  window.reloadBrowserPanelEndpoints = async function() {
      try {
          const res = await fetch('/api/hsearch/endpoints').then(r => r.json());
          if (!res.ok || !res.endpoints) return;
          const ep = res.endpoints;
          const sx = ep.searxng || {};
          const SE = window.SearchEndpoints;
          if (!SE) return;

          // 1. Populate SearXNG local daemon instance
          const localWrap = document.getElementById('cfg-searxng-local-wrap');
          if (localWrap) {
              localWrap.innerHTML = '';
              const localInst = sx.local_instance || SE.decomposeUrl(sx.local_url || 'http://127.0.0.1:8888', 'SearXNG Local Daemon', 'http');
              localInst.id = 'cfg_sx_local';
              localWrap.innerHTML = SE.renderCard(localInst, {
                  typeBadge: 'LOCAL DAEMON',
                  isDeletable: false,
                  key: 'searxng_local',
                  category: 'searxng'
              });
          }

          // 2. Populate SearXNG fallbacks
          const listWrap = document.getElementById('cfg-searxng-fallbacks-list');
          if (listWrap) {
              listWrap.innerHTML = '';
              const fallbacks = Array.isArray(sx.fallbacks) ? sx.fallbacks : [];
              fallbacks.forEach(f => {
                  const item = (typeof f === 'string') ? SE.decomposeUrl(f, '', 'https') : f;
                  SE.addEndpoint('cfg-searxng-fallbacks-list', item, {
                      typeBadge: 'SEARXNG MIRROR',
                      isDeletable: true,
                      key: 'searxng_fallback',
                      category: 'searxng'
                  });
              });
          }

          // 3. Populate Built-in Tor & Gateway Engines
          const torWrap = document.getElementById('cfg-tor-engines-list');
          if (torWrap) {
              torWrap.innerHTML = '';

              const ahmia = ep.dark_ahmia || {};
              const torch = ep.dark_torch || {};
              const haystak = ep.dark_haystak || {};
              const onionland = ep.dark_onionland || {};
              const excavator = ep.dark_excavator || {};
              const phobos = ep.dark_phobos || {};
              const tor66 = ep.dark_tor66 || {};
              const daniel = ep.dark_danieltore || {};

              const torEnginesDef = [
                  {
                      key: 'ahmia_onion',
                      badge: 'TOR ONION',
                      data: ahmia.onion || SE.decomposeUrl(ahmia.onion_url || 'http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion', 'Ahmia (.onion)', 'http')
                  },
                  {
                      key: 'ahmia_clear',
                      badge: 'CLEARNET GATEWAY',
                      data: ahmia.clearnet || SE.decomposeUrl(ahmia.clearnet_url || 'https://ahmia.fi', 'Ahmia Clearnet Gateway', 'https')
                  },
                  {
                      key: 'ddg_onion',
                      badge: 'TOR ONION',
                      data: torch.ddg || SE.decomposeUrl(torch.ddg_onion || 'https://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion/html/', 'DuckDuckGo (.onion)', 'https')
                  },
                  {
                      key: 'torch_onion',
                      badge: 'TOR ONION',
                      data: torch.torch || SE.decomposeUrl(torch.torch_onion || 'http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion/cgi-bin/omega/omega', 'Torch (.onion)', 'http')
                  },
                  {
                      key: 'haystak_onion',
                      badge: 'TOR ONION',
                      data: haystak.onion || SE.decomposeUrl(haystak.onion_url || 'http://haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion', 'Haystak (.onion)', 'http')
                  },
                  {
                      key: 'onionland_clear',
                      badge: 'CLEARNET GATEWAY',
                      data: onionland.clearnet || SE.decomposeUrl(onionland.clearnet_url || 'https://onionsearchengine.com/search.php', 'Onion Search Engine', 'https')
                  },
                  {
                      key: 'excavator_onion',
                      badge: 'TOR ONION',
                      data: excavator.onion || SE.decomposeUrl(excavator.onion_url || 'http://2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion/search', 'Excavator (.onion)', 'http')
                  },
                  {
                      key: 'phobos_onion',
                      badge: 'TOR ONION',
                      data: phobos.onion || SE.decomposeUrl(phobos.onion_url || 'http://phobosxilamwcg75xt22id7aywkzol6q6rfl2flipcqoc4e4ahima5id.onion/search', 'Phobos (.onion)', 'http')
                  },
                  {
                      key: 'tor66_onion',
                      badge: 'TOR ONION',
                      data: tor66.onion || SE.decomposeUrl(tor66.onion_url || 'http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search', 'Tor66 (.onion)', 'http')
                  },
                  {
                      key: 'daniel_onion',
                      badge: 'TOR ONION',
                      data: daniel.onion || SE.decomposeUrl(daniel.onion_url || 'http://tordexu73joywapk2txdr54jed4imqledpcvcuf75qsas2gwdgksvnyd.onion/search', 'TorDex Directory (.onion)', 'http')
                  }
              ];

              torEnginesDef.forEach(ted => {
                  ted.data.id = 'cfg_' + ted.key;
                  torWrap.insertAdjacentHTML('beforeend', SE.renderCard(ted.data, {
                      typeBadge: ted.badge,
                      isDeletable: false,
                      key: ted.key,
                      category: 'tor'
                  }));
              });

              // Add custom tor engines
              const customTorEngines = Array.isArray(ep.custom_onion_engines) ? ep.custom_onion_engines : [];
              customTorEngines.forEach(cte => {
                  SE.addEndpoint('cfg-tor-engines-list', cte, {
                      typeBadge: 'CUSTOM TOR',
                      isDeletable: true,
                      key: 'custom_tor',
                      category: 'tor'
                  });
              });
          }

          // 4. Populate Custom Nodes
          const customWrap = document.getElementById('cfg-custom-nodes-list');
          if (customWrap) {
              customWrap.innerHTML = '';
              const customNodes = Array.isArray(ep.custom_nodes) ? ep.custom_nodes : [];
              customNodes.forEach(cn => {
                  SE.addEndpoint('cfg-custom-nodes-list', cn, {
                      typeBadge: 'CUSTOM NODE',
                      isDeletable: true,
                      key: 'custom_node',
                      category: 'custom'
                  });
              });
          }
      } catch (err) {
          console.warn('[BrowserPanel] Failed to load search endpoints:', err);
      }
  };

  window.addConfigSearxngFallbackNode = function() {
      if (!window.SearchEndpoints) return;
      window.SearchEndpoints.addEndpoint('cfg-searxng-fallbacks-list', {
          name: 'Custom Fallback Node',
          protocol: 'https',
          host: '',
          port: '',
          path: '',
          enabled: true
      }, {
          typeBadge: 'SEARXNG MIRROR',
          isDeletable: true,
          key: 'searxng_fallback',
          category: 'searxng'
      });
  };

  window.addConfigCustomTorEngine = function() {
      if (!window.SearchEndpoints) return;
      window.SearchEndpoints.addEndpoint('cfg-tor-engines-list', {
          name: 'Custom Onion Engine',
          protocol: 'http',
          host: '',
          port: '',
          path: '/search?q={q}',
          enabled: true
      }, {
          typeBadge: 'CUSTOM TOR',
          isDeletable: true,
          key: 'custom_tor',
          category: 'tor'
      });
  };

  window.addConfigCustomNode = function() {
      if (!window.SearchEndpoints) return;
      window.SearchEndpoints.addEndpoint('cfg-custom-nodes-list', {
          name: 'Custom Search Node',
          protocol: 'https',
          host: '',
          port: '',
          path: '',
          enabled: true
      }, {
          typeBadge: 'CUSTOM NODE',
          isDeletable: true,
          key: 'custom_node',
          category: 'custom'
      });
  };

  window.saveConfigEndpoints = async function() {
      const SE = window.SearchEndpoints;
      if (!SE) return;

      // Collect SearXNG local
      const localCard = document.querySelector('#cfg-searxng-local-wrap .endpoint-card');
      const localItem = SE.collectCard(localCard);

      // Collect SearXNG fallbacks
      const fallbackCards = document.querySelectorAll('#cfg-searxng-fallbacks-list .endpoint-card');
      const fallbacks = [];
      fallbackCards.forEach(c => {
          const item = SE.collectCard(c);
          if (item && (item.host || item.url)) fallbacks.push(item);
      });

      // Collect Tor engines by key
      function getTorItem(key) {
          const card = document.querySelector(`#cfg-tor-engines-list .endpoint-card[data-key="${key}"]`);
          return SE.collectCard(card);
      }

      const ahmiaOnion = getTorItem('ahmia_onion');
      const ahmiaClear = getTorItem('ahmia_clear');
      const ddgOnion = getTorItem('ddg_onion');
      const torchOnion = getTorItem('torch_onion');
      const haystakOnion = getTorItem('haystak_onion');
      const onionlandClear = getTorItem('onionland_clear');
      const excavatorOnion = getTorItem('excavator_onion');
      const phobosOnion = getTorItem('phobos_onion');
      const tor66Onion = getTorItem('tor66_onion');
      const danielOnion = getTorItem('daniel_onion');

      // Collect Custom Tor engines
      const customTorCards = document.querySelectorAll('#cfg-tor-engines-list .endpoint-card[data-key="custom_tor"]');
      const customTorEngines = [];
      customTorCards.forEach(c => {
          const item = SE.collectCard(c);
          if (item && (item.host || item.url)) {
              customTorEngines.push({
                  name: item.name || 'Custom Onion',
                  onion_url: item.url,
                  protocol: item.protocol,
                  host: item.host,
                  port: item.port,
                  path: item.path,
                  search_template: item.path || '/search?q={q}',
                  enabled: item.enabled,
                  use_api_key: item.use_api_key,
                  api_key: item.api_key
              });
          }
      });

      // Collect Custom Nodes
      const customNodeCards = document.querySelectorAll('#cfg-custom-nodes-list .endpoint-card');
      const customNodes = [];
      customNodeCards.forEach(c => {
          const item = SE.collectCard(c);
          if (item && (item.host || item.url)) customNodes.push(item);
      });

      const payload = {
          searxng: {
              local_instance: localItem,
              local_url: localItem?.url || 'http://127.0.0.1:8888',
              fallbacks: fallbacks
          },
          dark_ahmia: {
              onion: ahmiaOnion,
              onion_url: ahmiaOnion?.url || '',
              clearnet: ahmiaClear,
              clearnet_url: ahmiaClear?.url || ''
          },
          dark_torch: {
              torch: torchOnion,
              torch_onion: torchOnion?.url || '',
              ddg: ddgOnion,
              ddg_onion: ddgOnion?.url || ''
          },
          dark_haystak: {
              onion: haystakOnion,
              onion_url: haystakOnion?.url || ''
          },
          dark_onionland: {
              clearnet: onionlandClear,
              clearnet_url: onionlandClear?.url || ''
          },
          dark_excavator: {
              onion: excavatorOnion,
              onion_url: excavatorOnion?.url || ''
          },
          dark_phobos: {
              onion: phobosOnion,
              onion_url: phobosOnion?.url || ''
          },
          dark_tor66: {
              onion: tor66Onion,
              onion_url: tor66Onion?.url || ''
          },
          dark_danieltore: {
              onion: danielOnion,
              onion_url: danielOnion?.url || ''
          },
          custom_onion_engines: customTorEngines,
          custom_nodes: customNodes
      };

      try {
          const res = await fetch('/api/hsearch/endpoints', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
          }).then(r => r.json());

          if (res.ok) {
              if (typeof window.showToast === 'function') {
                  window.showToast('Search endpoints & nodes saved successfully!');
              } else {
                  alert('Search endpoints & nodes saved successfully!');
              }
              window.reloadBrowserPanelEndpoints();
          } else {
              alert('Failed to save endpoints: ' + (res.error || 'Unknown error'));
          }
      } catch (e) {
          alert('Error saving endpoints: ' + e.message);
      }
  };

  window.resetConfigEndpoints = async function() {
      if (!confirm('Reset all search endpoints to defaults?')) return;
      try {
          const res = await fetch('/api/hsearch/endpoints/reset', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' }
          }).then(r => r.json());

          if (res.ok) {
              alert('Endpoints reset to factory defaults.');
              window.reloadBrowserPanelEndpoints();
          } else {
              alert('Failed to reset endpoints: ' + (res.error || 'Unknown error'));
          }
      } catch (e) {
          alert('Error resetting endpoints: ' + e.message);
      }
  };

  /**
   * Helper to update in-memory config and trigger a silent save to disk.
   */
  window.updateConfig = function(path, val) {
      console.log(`[Config] Updating ${path} to`, val);
      // Update local window.cfg object so buildPayload picks it up
      const keys = path.split('.');
      let obj = window.cfg;
      for (let i = 0; i < keys.length - 1; i++) {
          obj[keys[i]] = obj[keys[i]] || {};
          obj = obj[keys[i]];
      }
      obj[keys[keys.length - 1]] = val;

      // If updating search settings, also send directly to /api/hsearch/config
      if (path.startsWith('plugins.BROWSER.search.')) {
          const sub = path.replace('plugins.BROWSER.search.', '');
          const parts = sub.split('.');
          const payload = {};
          let cur = payload;
          for (let i = 0; i < parts.length - 1; i++) {
              cur[parts[i]] = {};
              cur = cur[parts[i]];
          }
          cur[parts[parts.length - 1]] = val;
          fetch('/api/hsearch/config', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
          }).catch(e => console.warn('[BrowserPanel] Direct search save error:', e));
      }
      
      // Call global saveConfig if available (silent mode)
      if (typeof saveConfig === 'function') {
          saveConfig(true); 
      }
  };

  window.updateModeUI = function() {
      const emApp = document.getElementById('em-app');
      const emCdp = document.getElementById('em-cdp');
      const boxApp = document.getElementById('mode-box-app');
      const boxCdp = document.getElementById('mode-box-cdp');

      if (boxApp) {
          boxApp.style.borderColor = (emApp && emApp.checked) ? 'var(--accent)' : 'transparent';
          boxApp.style.boxShadow = (emApp && emApp.checked) ? '0 0 0 2px var(--accent) inset, 0 4px 15px rgba(124,58,237,0.1)' : 'none';
      }
      if (boxCdp) {
          boxCdp.style.borderColor = (emCdp && emCdp.checked) ? 'var(--accent)' : 'transparent';
          boxCdp.style.boxShadow = (emCdp && emCdp.checked) ? '0 0 0 2px var(--accent) inset, 0 4px 15px rgba(124,58,237,0.1)' : 'none';
      }
  };

  async function launchCdpBrowser() {
      if (!confirm("A new instance of Chrome/Edge will be launched with debugging enabled. Do you want to proceed?")) return;
      try {
          const r = await fetch('/api/browser/launch_external', { method: 'POST' });
          const d = await r.json();
          if (d.ok) alert(window.t('webui_diag_done') + ": " + d.message);
          else alert(window.t('webui_diag_error') + ": " + d.error);
      } catch(e) {
          alert(window.t('webui_diag_error') + ": " + e.message);
      }
  }

  // ── Deep Search On-Demand Component Handlers ─────────────────────────────
  window.installSearchComponent = async function(id, btn) {
      const originalText = btn.innerHTML;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Installing...';
      btn.disabled = true;

      const taskId = `search_comp_${id}`;
      let modal = null;
      if (window.HecosProgress && typeof window.HecosProgress.createModal === 'function') {
          modal = window.HecosProgress.createModal({
              taskId: taskId,
              title: `Installazione ${id}`,
              source: 'HSEARCH',
              showCancel: true,
              onCancel: () => {
                  if (window.HecosProgress.cancel) window.HecosProgress.cancel(taskId);
              }
          });
      }

      // Active progress polling for live update
      const pollInterval = setInterval(async () => {
          try {
              const pr = await fetch(`/api/progress/${encodeURIComponent(taskId)}`).then(r => r.json());
              if (pr && pr.ok && pr.task && modal) {
                  modal.update(pr.task);
              }
          } catch (_) {}
      }, 400);

      try {
          const res = await fetch(`/api/hsearch/components/${id}/install`, { method: 'POST' });
          const data = await res.json();
          clearInterval(pollInterval);
          if (data.ok) {
              if (modal) {
                  modal.update({ state: 'done', percent: 100, message: 'Installazione completata con successo!' });
                  setTimeout(() => { if (modal.close) modal.close(); }, 1200);
              }
              btn.innerHTML = '<i class="fas fa-check"></i> Installed';
              if (window.populateBrowserUI) window.populateBrowserUI();
          } else {
              if (modal) {
                  modal.update({ state: 'error', message: data.message || data.error });
              } else {
                  alert(`Installation error: ${data.message || data.error}`);
              }
              btn.innerHTML = originalText;
          }
      } catch (err) {
          clearInterval(pollInterval);
          if (modal) {
              modal.update({ state: 'error', message: err.message });
          } else {
              alert(`Network error: ${err.message}`);
          }
          btn.innerHTML = originalText;
      } finally {
          btn.disabled = false;
      }
  };

  window.toggleTorDaemon = async function(btn) {
      btn.disabled = true;
      try {
          const st = await fetch('/api/hsearch/tor_status').then(r => r.json());
          const action = st.ok ? 'stop' : 'start';
          const res = await fetch(`/api/hsearch/components/tor_daemon/${action}`, { method: 'POST' }).then(r => r.json());
          alert(res.ok ? `Tor daemon: ${action} completed.` : `Error: ${res.message}`);
          if (window.populateBrowserUI) window.populateBrowserUI();
      } catch(e) {
          alert(`Error: ${e.message}`);
      } finally {
          btn.disabled = false;
      }
  };

  window.requestTorNewIdentity = async function(btn) {
      try {
          const res = await fetch('/api/hsearch/tor_newnym', { method: 'POST' }).then(r => r.json());
          alert(res.ok ? 'New Tor circuit requested successfully!' : `Error: ${res.message}`);
          if (window.populateBrowserUI) window.populateBrowserUI();
      } catch(e) {
          alert(`Error: ${e.message}`);
      }
  };

  window.detectTorBrowserPath = async function() {
      try {
          const res = await fetch('/api/hsearch/detect_tor_browser').then(r => r.json());
          if (res.ok && res.path) {
              const el = document.getElementById('search-tor-browser-path');
              if (el) el.value = res.path;
              window.updateConfig('plugins.BROWSER.search.tor.tor_browser_path', res.path);
              if (typeof window.showToast === 'function') {
                  window.showToast('Detected Tor Browser: ' + res.path);
              } else {
                  alert('Detected Tor Browser:\n' + res.path);
              }
          } else {
              alert('Tor Browser not automatically detected in standard folders. You can manually enter the path to firefox.exe.');
          }
      } catch (err) {
          alert('Error detecting Tor Browser: ' + err.message);
      }
  };


