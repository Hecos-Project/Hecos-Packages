/**
 * cyber_map_globe3d.js
 * Interactive 3D Cyber Globe renderer built on Globe.gl (Three.js) using local vendor assets.
 * Features animated protocol arcs, pulsing node rings, dark cyber land polygons,
 * resize responsiveness, and automatic WebGL fallback protection.
 */
(function () {
  let _vendorPromise = null;
  let _countriesFeatures = null;

  function loadScriptOnce(src) {
    return new Promise((resolve, reject) => {
      const existing = Array.from(document.scripts).find(s => s.src && s.src.includes(src));
      if (existing && (existing.dataset.loaded === '1' || (src.includes('globe.gl') && window.Globe) || (src.includes('topojson') && window.topojson))) {
        resolve();
        return;
      }
      const s = document.createElement('script');
      s.src = src;
      s.async = true;
      s.onload = () => { s.dataset.loaded = '1'; resolve(); };
      s.onerror = () => reject(new Error('Failed to load ' + src));
      document.head.appendChild(s);
    });
  }

  async function ensureAssetsLoaded() {
    if (_vendorPromise) return _vendorPromise;
    _vendorPromise = (async () => {
      if (!window.topojson) {
        await loadScriptOnce('/netsearch_static/vendor/cyber_map/topojson-client.min.js');
      }
      if (!window.Globe) {
        await loadScriptOnce('/netsearch_static/vendor/cyber_map/globe.gl.min.js');
      }
      if (!_countriesFeatures) {
        const res = await fetch('/netsearch_static/vendor/cyber_map/countries-110m.json');
        if (res.ok) {
          const topo = await res.json();
          if (window.topojson && topo.objects && topo.objects.countries) {
            _countriesFeatures = window.topojson.feature(topo, topo.objects.countries).features || [];
          }
        }
      }
    })();
    return _vendorPromise;
  }

  function hasWebGL() {
    try {
      const canvas = document.createElement('canvas');
      return Boolean(window.WebGLRenderingContext && (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
    } catch (_e) {
      return false;
    }
  }

  function esc(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  class CyberGlobe3D {
    constructor(containerEl, opts = {}) {
      this.container = containerEl;
      this.onSelectNode = opts.onSelectNode || (() => {});
      this.onFallback2D = opts.onFallback2D || (() => {});
      this.globe = null;
      this.autoRotate = true;
      this.mounted = false;
      this._resizeObserver = null;
      this._latestGraph = { nodes: [], edges: [] };
      this._selectedId = null;
    }

    async mount() {
      if (this.mounted) {
        this.resize();
        return true;
      }
      if (!hasWebGL()) {
        console.warn('[CyberGlobe3D] WebGL unavailable, falling back to 2D Map.');
        this.onFallback2D('WebGL unavailable');
        return false;
      }
      try {
        await ensureAssetsLoaded();
        if (!window.Globe) {
          this.onFallback2D('Globe.gl failed to load');
          return false;
        }
        const rect = this.container.getBoundingClientRect();
        const w = Math.max(300, Math.floor(rect.width || this.container.clientWidth || 800));
        const h = Math.max(220, Math.floor(rect.height || this.container.clientHeight || 360));

        const g = window.Globe()(this.container)
          .width(w)
          .height(h)
          .backgroundColor('rgba(4, 7, 17, 1)')
          .showGlobe(true)
          .showAtmosphere(true)
          .atmosphereColor('#06b6d4')
          .atmosphereAltitude(0.16)
          .showGraticules(true)
          .polygonsData(_countriesFeatures || [])
          .polygonCapColor(() => 'rgba(13, 25, 48, 0.88)')
          .polygonSideColor(() => 'rgba(6, 182, 212, 0.08)')
          .polygonStrokeColor(() => 'rgba(56, 189, 248, 0.28)')
          .polygonAltitude(0.005)
          .pointLat('lat')
          .pointLng('lon')
          .pointColor((d) => (d.id === this._selectedId ? '#ffffff' : (d.color || '#38bdf8')))
          .pointAltitude((d) => {
            if (d.node_type === 'local_core') return 0.055;
            if (d.node_type === 'tor_relay') return 0.04;
            if (d.protocol === 'onion_v3') return 0.045;
            return Math.min(0.07, 0.015 + Math.log10(Math.max(1, d.result_count || 1)) * 0.018);
          })
          .pointRadius((d) => {
            if (d.id === this._selectedId) return 0.72;
            if (d.node_type === 'local_core' || d.node_type === 'local_daemon') return 0.52;
            if (d.node_type === 'tor_relay') return 0.44;
            return Math.min(0.65, 0.28 + Math.log2(Math.max(1, d.result_count || 1)) * 0.07);
          })
          .pointLabel((d) => {
            const addr = d.ip ? `${d.host} (${d.ip})` : d.host;
            return `<div class="cm-globe-tooltip">
              <div class="tt-host">${esc(d.label || d.host)}</div>
              <div class="tt-meta">
                <div><b>Addr:</b> ${esc(addr)}${d.port ? ':' + d.port : ''}</div>
                <div><b>Proto:</b> <span style="color:${esc(d.color)}">${esc(d.protocol_label || d.protocol)}</span> (${esc(d.transport || '')})</div>
                <div><b>Geo:</b> ${esc(d.country_name || 'Unknown')}${d.city ? ' • ' + esc(d.city) : ''}</div>
                ${d.result_count ? `<div><b>Results:</b> ${d.result_count} (${esc((d.engines || []).join(', '))})</div>` : ''}
              </div>
            </div>`;
          })
          .onPointClick((d) => {
            if (d && d.id) {
              this.onSelectNode(d.id);
              this.focusCoord(d.lat, d.lon, 1.5);
            }
          })
          .arcStartLat('startLat')
          .arcStartLng('startLon')
          .arcEndLat('endLat')
          .arcEndLng('endLon')
          .arcColor((e) => [e.color || '#38bdf8', 'rgba(255,255,255,0.65)'])
          .arcDashLength((e) => (e.dashed ? 0.35 : 0.6))
          .arcDashGap((e) => (e.dashed ? 0.25 : 0.35))
          .arcDashAnimateTime((e) => (e.protocol === 'tor_circuit' || e.protocol === 'onion_v3' ? 1400 : 2100))
          .arcStroke((e) => Math.min(1.6, 0.35 + (e.weight || 1) * 0.16))
          .arcAltitudeAutoScale(0.38)
          .ringLat('lat')
          .ringLng('lon')
          .ringColor((d) => d.color || '#22d3ee')
          .ringMaxRadius((d) => (d.id === this._selectedId ? 5.5 : 3.2))
          .ringPropagationSpeed(2.2)
          .ringRepeatPeriod((d) => (d.id === this._selectedId ? 900 : 1800));

        // Style Three.js globe sphere dark navy
        try {
          const mat = g.globeMaterial();
          if (mat && mat.color) {
            mat.color.set('#070d1c');
            if (mat.emissive) mat.emissive.set('#041022');
            if (mat.emissiveIntensity !== undefined) mat.emissiveIntensity = 0.65;
          }
          const controls = g.controls();
          if (controls) {
            controls.autoRotate = this.autoRotate;
            controls.autoRotateSpeed = 0.45;
            controls.enableDamping = true;
            controls.dampingFactor = 0.08;
          }
        } catch (_e) { /* non-critical styling */ }

        g.pointOfView({ lat: 36.0, lng: 4.0, altitude: 2.05 }, 400);

        this.globe = g;
        this.mounted = true;

        if (typeof ResizeObserver !== 'undefined') {
          this._resizeObserver = new ResizeObserver(() => this.resize());
          this._resizeObserver.observe(this.container);
        }
        this.render(this._latestGraph, this._selectedId);
        return true;
      } catch (err) {
        console.warn('[CyberGlobe3D] Initialization failed, falling back to 2D:', err);
        this.onFallback2D(err.message || '3D init error');
        return false;
      }
    }

    setAutoRotate(enabled) {
      this.autoRotate = Boolean(enabled);
      if (this.globe) {
        try {
          const controls = this.globe.controls();
          if (controls) controls.autoRotate = this.autoRotate;
        } catch (_e) {}
      }
    }

    focusCoord(lat, lon, altitude = 1.65) {
      if (!this.globe || typeof lat !== 'number' || typeof lon !== 'number') return;
      try {
        this.globe.pointOfView({ lat, lng: lon, altitude }, 650);
      } catch (_e) {}
    }

    resetView() {
      this.focusCoord(36.0, 4.0, 2.05);
    }

    resize() {
      if (!this.globe || !this.container) return;
      const rect = this.container.getBoundingClientRect();
      if (rect.width > 50 && rect.height > 50) {
        this.globe.width(Math.floor(rect.width)).height(Math.floor(rect.height));
      }
    }

    render(graph, selectedId) {
      this._latestGraph = graph || { nodes: [], edges: [] };
      this._selectedId = selectedId || null;
      if (!this.globe || !this.mounted) return;

      const nodes = this._latestGraph.nodes || [];
      const edges = this._latestGraph.edges || [];

      // Limit arcs to top 160 to keep 60fps smooth under massive sweeps
      const slicedEdges = edges.slice(0, 160);
      const ringNodes = nodes.filter(
        n => n.id === this._selectedId || n.node_type === 'local_core' || n.node_type === 'tor_relay' || n.protocol === 'onion_v3'
      ).slice(0, 35);

      this.globe
        .pointsData(nodes)
        .arcsData(slicedEdges)
        .ringsData(ringNodes);
    }

    pause() {
      if (this.globe) {
        try {
          const controls = this.globe.controls();
          if (controls) controls.autoRotate = false;
        } catch (_e) {}
      }
    }

    resume() {
      if (this.globe) {
        this.setAutoRotate(this.autoRotate);
        this.resize();
      }
    }
  }

  window.CyberGlobe3D = CyberGlobe3D;
})();
