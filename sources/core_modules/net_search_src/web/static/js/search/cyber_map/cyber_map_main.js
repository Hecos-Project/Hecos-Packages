/**
 * cyber_map_main.js
 * Resilient orchestrator & Error Boundary for the Hecos Net Search Cyber Map.
 * Coordinates lazy-initialization, 3D Globe / 2D Map toggling, docked resizing,
 * fullscreen mode, dedicated standalone window syncing, and live search events.
 */
(function () {
  const VIEW_PREF_KEY = 'hecos_cyber_map_view_mode';
  const HEIGHT_PREF_KEY = 'hecos_cyber_map_dock_height';

  class CyberMapController {
    constructor() {
      this.dockEl = null;
      this.isStandalone = false;
      this.isOpen = false;
      this.isFullscreen = false;
      this.viewMode = (function () {
        try { return localStorage.getItem(VIEW_PREF_KEY) || '3d'; } catch (_e) { return '3d'; }
      })();
      this.autoRotate = true;
      this.state = window.CyberMapState;
      this.bus = window.CyberMapBus;
      this.hud = null;
      this.globe3d = null;
      this.flat2d = null;
      this._torPollTimer = null;
      this._initialized = false;
    }

    init(opts = {}) {
      if (this._initialized) return;
      const rootId = opts.standalone ? 'cyber-map-standalone-root' : 'cyber-map-dock';
      this.dockEl = document.getElementById(rootId);
      if (!this.dockEl) return;

      this.isStandalone = Boolean(opts.standalone);
      if (this.isStandalone) {
        this.dockEl.classList.add('is-standalone', 'is-open');
        this.isOpen = true;
      } else {
        try {
          const savedH = parseInt(localStorage.getItem(HEIGHT_PREF_KEY), 10);
          if (savedH && savedH >= 240 && savedH <= 760) {
            this.dockEl.style.height = savedH + 'px';
          }
        } catch (_e) {}
      }

      this.hud = new window.CyberMapHUD(this.dockEl, this);
      this.globe3d = new window.CyberGlobe3D(this.hud.els.canvas3d, {
        onSelectNode: (id) => this.handleNodeSelect(id),
        onFallback2D: (_reason) => this.setViewMode('2d', false)
      });
      this.flat2d = new window.CyberMapFlat2D(this.hud.els.canvas2d, {
        onSelectNode: (id) => this.handleNodeSelect(id)
      });

      if (!this.isStandalone) {
        this._initDockResizer();
      }

      this.state.subscribe((reason) => {
        if (this.isOpen) {
          this.renderActiveView();
          if (reason === 'select') {
            this.hud.renderInspector(this.state.getNodeDetails(this.state.selectedNodeId));
          }
        }
      });

      this._subscribeBus();
      this._initialized = true;

      if (this.isStandalone) {
        this._activate();
        const urlParams = new URLSearchParams(window.location.search);
        const sess = urlParams.get('session') || '';
        this._loadSessionsList(sess);
        if (sess) {
          this.loadSessionById(sess);
        } else if (this.bus) {
          this.bus.requestSnapshot();
        }
      }
    }

    _subscribeBus() {
      if (!this.bus) return;
      this.bus.subscribe((msg) => {
        if (!msg || !msg.type) return;
        if (msg.type === 'SEARCH_STARTED') {
          this.state.resetSearch({
            query: msg.query,
            mode: msg.mode,
            sessionId: msg.sessionId,
            localOnly: msg.localOnly
          });
          this.fetchTorCircuits();
        } else if (msg.type === 'SEARCH_RESULTS') {
          if (msg.localOnly !== undefined) this.state.setLocalOnly(msg.localOnly);
          this.state.ingestResults(msg.results || [], msg.engine || '');
        } else if (msg.type === 'SEARCH_COMPLETED') {
          this.fetchTorCircuits();
        } else if (msg.type === 'PRIVACY_CHANGED') {
          this.state.setLocalOnly(Boolean(msg.localOnly));
        } else if (msg.type === 'SESSION_LOADED' || msg.type === 'SYNC_SNAPSHOT') {
          this.state.resetSearch({
            query: msg.query,
            mode: msg.mode,
            sessionId: msg.sessionId,
            localOnly: msg.localOnly
          });
          this.state.ingestResults(msg.results || [], '');
          this.fetchTorCircuits();
        }
      });
    }

    async _activate() {
      await this.fetchTopology();
      // Pull current SearchState when opened inside /search after a search already finished
      if (!this.isStandalone && window.SearchState && Array.isArray(window.SearchState.results) && window.SearchState.results.length > 0 && this.state.targetNodes.size === 0) {
        this.state.resetSearch({
          query: window.SearchState.currentQuery,
          mode: window.SearchState.currentMode,
          sessionId: window.SearchState.activeSessionId,
          localOnly: window.SearchState.localOnly
        });
        this.state.ingestResults(window.SearchState.results, '');
      }
      await this.setViewMode(this.viewMode, false);
      this._startTorPoller();
    }

    toggleDock() {
      if (!this._initialized) this.init({ standalone: false });
      if (this.isOpen) {
        this.closeDock();
      } else {
        this.openDock();
      }
    }

    openDock() {
      if (!this._initialized) this.init({ standalone: false });
      this.isOpen = true;
      this.dockEl.classList.add('is-open');
      const trig = document.getElementById('btn-cyber-map-toggle');
      if (trig) trig.classList.add('is-active');
      this._activate();
    }

    closeDock() {
      this.isOpen = false;
      this.isFullscreen = false;
      if (this.dockEl) {
        this.dockEl.classList.remove('is-open', 'is-fullscreen');
      }
      const trig = document.getElementById('btn-cyber-map-toggle');
      if (trig) trig.classList.remove('is-active');
      if (this.globe3d) this.globe3d.pause();
      if (this.flat2d) this.flat2d.pause();
      this._stopTorPoller();
    }

    toggleFullscreen() {
      if (!this.dockEl) return;
      this.isFullscreen = !this.isFullscreen;
      this.dockEl.classList.toggle('is-fullscreen', this.isFullscreen);
      if (this.hud && this.hud.els.btnFullscreen) {
        this.hud.els.btnFullscreen.innerHTML = this.isFullscreen
          ? '<i class="fas fa-compress"></i>'
          : '<i class="fas fa-expand"></i>';
      }
      setTimeout(() => {
        if (this.viewMode === '3d' && this.globe3d) this.globe3d.resize();
        if (this.viewMode === '2d' && this.flat2d) this.flat2d.resize();
      }, 60);
    }

    openStandaloneWindow() {
      const sid = (window.SearchState && (window.SearchState.activeSessionId || window.SearchState.currentSessionId)) || '';
      const q = sid ? `?session=${encodeURIComponent(sid)}` : '';
      window.open(`/search/cyber_map${q}`, 'HecosCyberMapWindow', 'width=1280,height=820,menubar=no,toolbar=no,location=no,status=no');
    }

    async setViewMode(mode, persist = true) {
      const target = mode === '2d' ? '2d' : '3d';
      this.viewMode = target;
      if (persist) {
        try { localStorage.setItem(VIEW_PREF_KEY, target); } catch (_e) {}
      }
      this.hud.updateViewButtons(target, this.autoRotate);

      if (target === '3d') {
        if (this.flat2d) this.flat2d.pause();
        const ok = await this.globe3d.mount();
        if (ok) {
          this.globe3d.resume();
          this.renderActiveView();
        }
      } else {
        if (this.globe3d) this.globe3d.pause();
        await this.flat2d.mount();
        this.flat2d.resume();
        this.renderActiveView();
      }
    }

    toggleAutoRotate() {
      this.autoRotate = !this.autoRotate;
      if (this.globe3d) this.globe3d.setAutoRotate(this.autoRotate);
      this.hud.updateViewButtons(this.viewMode, this.autoRotate);
    }

    resetView() {
      if (this.viewMode === '3d' && this.globe3d) this.globe3d.resetView();
      if (this.viewMode === '2d' && this.flat2d) this.flat2d.resetView();
    }

    handleNodeSelect(nodeId) {
      this.state.selectNode(nodeId);
      const details = this.state.getNodeDetails(nodeId);
      this.hud.renderInspector(details);
      if (details) {
        if (this.viewMode === '2d' && this.flat2d) this.flat2d.focusCoord(details.lat, details.lon);
      }
    }

    filterSearchByHost(host) {
      if (!host) return;
      if (!this.isStandalone) {
        const refineInput = document.getElementById('results-refine-input');
        if (refineInput) {
          refineInput.value = `domain:${host}`;
          refineInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
      } else if (this.bus) {
        this.bus.emit('FILTER_HOST_IN_SEARCH', { host });
      }
    }

    renderActiveView() {
      if (!this.isOpen || !this.hud) return;
      const graph = this.state.getVisibleGraph();
      this.hud.renderStats(graph, this.state);
      if (this.viewMode === '3d' && this.globe3d && this.globe3d.mounted) {
        this.globe3d.render(graph, this.state.selectedNodeId);
      } else if (this.viewMode === '2d' && this.flat2d && this.flat2d.mounted) {
        this.flat2d.render(graph, this.state.selectedNodeId);
      }
    }

    async fetchTopology() {
      try {
        const res = await fetch('/api/hsearch/cyber_map/topology');
        if (!res.ok) return;
        const data = await res.json();
        if (window.SearchState && window.SearchState.localOnly !== undefined) {
          data.local_only = Boolean(window.SearchState.localOnly);
        }
        this.state.applyTopology(data);
      } catch (e) {
        console.warn('[CyberMap] fetchTopology err:', e);
      }
    }

    async fetchTorCircuits(force = false) {
      const now = Date.now();
      if (!force && this._lastTorFetchTs && (now - this._lastTorFetchTs) < 2500) {
        return;
      }
      this._lastTorFetchTs = now;
      try {
        const res = await fetch(`/api/hsearch/cyber_map/tor_circuits?force=${force ? 'true' : 'false'}`);
        if (!res.ok) return;
        const data = await res.json();
        this.state.applyTorCircuits(data);
      } catch (e) {
        console.warn('[CyberMap] fetchTorCircuits err:', e);
      }
    }

    async requestNewTorCircuit() {
      const btn = this.hud && this.hud.els.btnNewnym;
      if (btn) btn.disabled = true;
      try {
        const res = await fetch('/api/hsearch/cyber_map/new_circuit', { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          this.state.applyTorCircuits(data);
        }
      } catch (e) {
        console.warn('[CyberMap] new_circuit err:', e);
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    async _loadSessionsList(selectedId) {
      try {
        const res = await fetch('/api/hsearch/sessions?limit=30');
        if (!res.ok) return;
        const data = await res.json();
        if (data && data.ok && this.hud) {
          this.hud.populateSessionOptions(data.sessions || [], selectedId);
        }
      } catch (_e) {}
    }

    async loadSessionById(sessionId) {
      if (!sessionId) {
        if (this.bus) this.bus.requestSnapshot();
        return;
      }
      try {
        const res = await fetch(`/api/hsearch/sessions/${encodeURIComponent(sessionId)}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data && data.ok && data.session) {
          const s = data.session;
          this.state.resetSearch({
            query: s.query,
            mode: s.mode,
            sessionId: s.id
          });
          this.state.ingestResults(s.results || [], '');
          this.fetchTorCircuits();
        }
      } catch (e) {
        console.warn('[CyberMap] loadSessionById err:', e);
      }
    }

    _startTorPoller() {
      if (this._torPollTimer) return;
      this._torPollTimer = setInterval(() => {
        if (this.isOpen) this.fetchTorCircuits(false);
      }, 10000);
    }

    _stopTorPoller() {
      if (this._torPollTimer) {
        clearInterval(this._torPollTimer);
        this._torPollTimer = null;
      }
    }

    _initDockResizer() {
      const bar = this.hud && this.hud.els.resizerBottom;
      if (!bar || !this.dockEl) return;
      bar.addEventListener('mousedown', (ev) => {
        ev.preventDefault();
        const startY = ev.clientY;
        const startH = this.dockEl.getBoundingClientRect().height;
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'ns-resize';

        const onMove = (m) => {
          const nextH = Math.max(240, Math.min(window.innerHeight * 0.78, Math.round(startH + (m.clientY - startY))));
          this.dockEl.style.height = nextH + 'px';
        };
        const onUp = () => {
          document.body.style.userSelect = '';
          document.body.style.cursor = '';
          window.removeEventListener('mousemove', onMove);
          window.removeEventListener('mouseup', onUp);
          try {
            localStorage.setItem(HEIGHT_PREF_KEY, String(Math.round(this.dockEl.getBoundingClientRect().height)));
          } catch (_e) {}
          if (this.viewMode === '3d' && this.globe3d) this.globe3d.resize();
          if (this.viewMode === '2d' && this.flat2d) this.flat2d.resize();
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
      });
    }
  }

  window.CyberMap = new CyberMapController();
  window.toggleCyberMap = () => {
    try {
      window.CyberMap.toggleDock();
    } catch (err) {
      console.error('[CyberMap] Isolated UI error:', err);
    }
  };
})();
