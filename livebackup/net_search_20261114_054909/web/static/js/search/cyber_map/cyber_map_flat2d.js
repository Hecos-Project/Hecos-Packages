/**
 * cyber_map_flat2d.js
 * Ultra-lightweight HTML5 Canvas 2D Tactical Map renderer.
 * Uses local countries-110m.json topology, interactive pan/zoom, animated Bezier protocol arcs,
 * Darknet Layer badge, hover tooltips, and zero heavy WebGL dependencies.
 */
(function () {
  let _landPolygonsPromise = null;
  let _polygons = null;

  async function ensureMapPolygons() {
    if (_polygons) return _polygons;
    if (_landPolygonsPromise) return _landPolygonsPromise;
    _landPolygonsPromise = (async () => {
      try {
        if (!window.topojson) {
          await new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = '/netsearch_static/vendor/cyber_map/topojson-client.min.js';
            s.async = true;
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
          });
        }
        const res = await fetch('/netsearch_static/vendor/cyber_map/countries-110m.json');
        if (!res.ok) return [];
        const topo = await res.json();
        if (window.topojson && topo.objects && topo.objects.countries) {
          _polygons = window.topojson.feature(topo, topo.objects.countries).features || [];
        } else {
          _polygons = [];
        }
      } catch (_e) {
        _polygons = [];
      }
      return _polygons;
    })();
    return _landPolygonsPromise;
  }

  class CyberMapFlat2D {
    constructor(containerEl, opts = {}) {
      this.container = containerEl;
      this.onSelectNode = opts.onSelectNode || (() => {});
      this.canvas = null;
      this.ctx = null;
      this.tooltipEl = null;
      this.mounted = false;
      this.active = false;
      this.zoom = 1.0;
      this.panX = 0;
      this.panY = 0;
      this._dragging = false;
      this._dragMoved = false;
      this._lastX = 0;
      this._lastY = 0;
      this._rafId = null;
      this._phase = 0;
      this._graph = { nodes: [], edges: [] };
      this._selectedId = null;
      this._screenNodes = [];
      this._resizeObserver = null;
    }

    async mount() {
      if (!this.mounted) {
        this.container.innerHTML = '';
        this.canvas = document.createElement('canvas');
        this.canvas.style.width = '100%';
        this.canvas.style.height = '100%';
        this.canvas.style.display = 'block';
        this.canvas.style.cursor = 'grab';
        this.container.appendChild(this.canvas);

        this.tooltipEl = document.createElement('div');
        this.tooltipEl.className = 'cm-globe-tooltip';
        this.tooltipEl.style.position = 'absolute';
        this.tooltipEl.style.display = 'none';
        this.tooltipEl.style.zIndex = '6';
        this.container.appendChild(this.tooltipEl);

        this.ctx = this.canvas.getContext('2d');
        this._bindEvents();
        this.mounted = true;

        await ensureMapPolygons();
      }
      this.active = true;
      this.resize();
      this._startLoop();
      return true;
    }

    _bindEvents() {
      const c = this.canvas;
      c.addEventListener('mousedown', (e) => {
        this._dragging = true;
        this._dragMoved = false;
        this._lastX = e.clientX;
        this._lastY = e.clientY;
        c.style.cursor = 'grabbing';
      });

      window.addEventListener('mousemove', (e) => {
        if (!this.active) return;
        if (this._dragging) {
          const dx = e.clientX - this._lastX;
          const dy = e.clientY - this._lastY;
          if (Math.abs(dx) > 2 || Math.abs(dy) > 2) this._dragMoved = true;
          this.panX += dx;
          this.panY += dy;
          this._lastX = e.clientX;
          this._lastY = e.clientY;
          return;
        }
        const rect = c.getBoundingClientRect();
        if (e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom) {
          this._handleHover(e.clientX - rect.left, e.clientY - rect.top);
        } else if (this.tooltipEl) {
          this.tooltipEl.style.display = 'none';
        }
      });

      window.addEventListener('mouseup', () => {
        if (this._dragging) {
          this._dragging = false;
          c.style.cursor = 'grab';
        }
      });

      c.addEventListener('click', (e) => {
        if (this._dragMoved) return;
        const rect = c.getBoundingClientRect();
        const hit = this._findHitNode(e.clientX - rect.left, e.clientY - rect.top);
        if (hit) {
          this.onSelectNode(hit.node.id);
        }
      });

      c.addEventListener('wheel', (e) => {
        e.preventDefault();
        const rect = c.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const factor = e.deltaY < 0 ? 1.18 : 0.85;
        const nextZoom = Math.max(0.85, Math.min(8.0, this.zoom * factor));
        const ratio = nextZoom / this.zoom;
        this.panX = mx - (mx - this.panX) * ratio;
        this.panY = my - (my - this.panY) * ratio;
        this.zoom = nextZoom;
      }, { passive: false });

      if (typeof ResizeObserver !== 'undefined') {
        this._resizeObserver = new ResizeObserver(() => this.resize());
        this._resizeObserver.observe(this.container);
      }
    }

    _findHitNode(x, y) {
      let best = null;
      let bestDist = 14;
      for (const sn of this._screenNodes) {
        const dist = Math.hypot(sn.x - x, sn.y - y);
        if (dist <= bestDist) {
          best = sn;
          bestDist = dist;
        }
      }
      return best;
    }

    _handleHover(x, y) {
      const hit = this._findHitNode(x, y);
      if (!hit || !this.tooltipEl) {
        if (this.tooltipEl) this.tooltipEl.style.display = 'none';
        this.canvas.style.cursor = this._dragging ? 'grabbing' : 'grab';
        return;
      }
      const d = hit.node;
      this.canvas.style.cursor = 'pointer';
      const addr = d.ip ? `${d.host} (${d.ip})` : d.host;
      this.tooltipEl.innerHTML = `
        <div class="tt-host">${this._esc(d.label || d.host)}</div>
        <div class="tt-meta">
          <div><b>Addr:</b> ${this._esc(addr)}${d.port ? ':' + d.port : ''}</div>
          <div><b>Proto:</b> <span style="color:${this._esc(d.color)}">${this._esc(d.protocol_label || d.protocol)}</span></div>
          <div><b>Geo:</b> ${this._esc(d.country_name || 'Unknown')}</div>
          ${d.result_count ? `<div><b>Results:</b> ${d.result_count}</div>` : ''}
        </div>
      `;
      this.tooltipEl.style.display = 'block';
      const maxX = Math.max(10, this.container.clientWidth - 250);
      this.tooltipEl.style.left = Math.min(maxX, x + 14) + 'px';
      this.tooltipEl.style.top = Math.max(10, y - 16) + 'px';
    }

    _esc(s) {
      return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    resize() {
      if (!this.canvas || !this.container) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.max(300, this.container.clientWidth || 800);
      const h = Math.max(200, this.container.clientHeight || 360);
      this.canvas.width = Math.floor(w * dpr);
      this.canvas.height = Math.floor(h * dpr);
      this._w = w;
      this._h = h;
      this._dpr = dpr;
    }

    resetView() {
      this.zoom = 1.0;
      this.panX = 0;
      this.panY = 0;
    }

    focusCoord(lat, lon) {
      if (!this._w || !this._h || typeof lat !== 'number' || typeof lon !== 'number') return;
      const targetZoom = Math.max(this.zoom, 2.2);
      const baseX = ((lon + 180) / 360) * this._w;
      const baseY = ((90 - lat) / 180) * this._h;
      this.zoom = targetZoom;
      this.panX = this._w * 0.5 - baseX * targetZoom;
      this.panY = this._h * 0.5 - baseY * targetZoom;
    }

    _project(lat, lon) {
      const w = this._w || 800;
      const h = this._h || 360;
      const bx = ((lon + 180) / 360) * w;
      const by = ((90 - lat) / 180) * h;
      return [bx * this.zoom + this.panX, by * this.zoom + this.panY];
    }

    render(graph, selectedId) {
      this._graph = graph || { nodes: [], edges: [] };
      this._selectedId = selectedId || null;
      if (this.active) this._drawFrame();
    }

    _startLoop() {
      if (this._rafId) return;
      const tick = () => {
        if (!this.active) {
          this._rafId = null;
          return;
        }
        this._phase = (this._phase + 0.65) % 10000;
        this._drawFrame();
        this._rafId = requestAnimationFrame(tick);
      };
      this._rafId = requestAnimationFrame(tick);
    }

    pause() {
      this.active = false;
      if (this._rafId) {
        cancelAnimationFrame(this._rafId);
        this._rafId = null;
      }
    }

    resume() {
      this.active = true;
      this.resize();
      this._startLoop();
    }

    _drawFrame() {
      const ctx = this.ctx;
      const w = this._w || 800;
      const h = this._h || 360;
      if (!ctx || !w || !h) return;

      ctx.save();
      ctx.scale(this._dpr || 1, this._dpr || 1);

      // Background
      ctx.fillStyle = '#050914';
      ctx.fillRect(0, 0, w, h);

      // Tactical lat/lon grid
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.08)';
      ctx.lineWidth = 1;
      for (let lon = -150; lon <= 150; lon += 30) {
        const [gx] = this._project(0, lon);
        ctx.beginPath();
        ctx.moveTo(gx, 0);
        ctx.lineTo(gx, h);
        ctx.stroke();
      }
      for (let lat = -60; lat <= 60; lat += 30) {
        const [, gy] = this._project(lat, 0);
        ctx.beginPath();
        ctx.moveTo(0, gy);
        ctx.lineTo(w, gy);
        ctx.stroke();
      }

      // Draw countries GeoJSON polygons
      if (_polygons && _polygons.length > 0) {
        ctx.fillStyle = 'rgba(17, 30, 56, 0.85)';
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.28)';
        ctx.lineWidth = 0.8;
        for (const feat of _polygons) {
          const geom = feat.geometry;
          if (!geom) continue;
          const rings = geom.type === 'Polygon'
            ? [geom.coordinates]
            : (geom.type === 'MultiPolygon' ? geom.coordinates : []);
          for (const poly of rings) {
            for (const ring of poly) {
              if (!ring || ring.length < 2) continue;
              ctx.beginPath();
              for (let i = 0; i < ring.length; i++) {
                const pt = ring[i];
                const [px, py] = this._project(pt[1], pt[0]);
                if (i === 0) ctx.moveTo(px, py);
                else ctx.lineTo(px, py);
              }
              ctx.closePath();
              ctx.fill();
              ctx.stroke();
            }
          }
        }
      }

      // Draw curved protocol edges
      const edges = (this._graph.edges || []).slice(0, 180);
      for (const e of edges) {
        const [x1, y1] = this._project(e.startLat, e.startLon);
        const [x2, y2] = this._project(e.endLat, e.endLon);
        const mx = (x1 + x2) * 0.5;
        const my = (y1 + y2) * 0.5 - Math.min(90, Math.hypot(x2 - x1, y2 - y1) * 0.22);

        ctx.save();
        ctx.strokeStyle = e.color || '#38bdf8';
        ctx.globalAlpha = 0.55;
        ctx.lineWidth = Math.min(2.4, 0.9 + (e.weight || 1) * 0.25);
        ctx.setLineDash(e.dashed ? [5, 5] : [8, 6]);
        ctx.lineDashOffset = -this._phase;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.quadraticCurveTo(mx, my, x2, y2);
        ctx.stroke();
        ctx.restore();
      }

      // Draw nodes + collect screen coordinates for hit-testing
      const nodes = this._graph.nodes || [];
      const screenNodes = [];
      for (const n of nodes) {
        const [nx, ny] = this._project(n.lat, n.lon);
        const isSelected = n.id === this._selectedId;
        const r = isSelected
          ? 7
          : (n.node_type === 'local_core' ? 6 : (n.node_type === 'tor_relay' ? 5 : Math.min(6.5, 3.3 + Math.log2(Math.max(1, n.result_count || 1)) * 0.85)));

        // Subtle outer glow
        ctx.beginPath();
        ctx.arc(nx, ny, r + 4, 0, Math.PI * 2);
        ctx.fillStyle = n.color || '#38bdf8';
        ctx.globalAlpha = isSelected ? 0.35 : 0.16;
        ctx.fill();

        // Core dot
        ctx.globalAlpha = 1;
        ctx.beginPath();
        ctx.arc(nx, ny, r, 0, Math.PI * 2);
        ctx.fillStyle = isSelected ? '#ffffff' : (n.color || '#38bdf8');
        ctx.fill();
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = '#020617';
        ctx.stroke();

        // Short label for infra/selected/onion nodes
        if (isSelected || n.node_type === 'local_core' || n.node_type === 'tor_relay') {
          ctx.font = '600 10px JetBrains Mono, monospace';
          ctx.fillStyle = '#e2e8f0';
          ctx.fillText(n.label || n.host, nx + r + 5, ny + 3);
        }

        screenNodes.push({ x: nx, y: ny, r, node: n });
      }
      this._screenNodes = screenNodes;

      ctx.restore();
    }
  }

  window.CyberMapFlat2D = CyberMapFlat2D;
})();
