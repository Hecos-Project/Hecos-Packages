/**
 * cyber_map_hud.js
 * Renders the HUD chrome, protocol filter strip, Tor circuit banner, and Node Telemetry Inspector.
 */
(function () {
  function esc(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  class CyberMapHUD {
    constructor(dockEl, controller) {
      this.dockEl = dockEl;
      this.ctrl = controller;
      this.isStandalone = Boolean(controller.isStandalone);
      this.els = {};
      this._buildMarkup();
    }

    _buildMarkup() {
      this.dockEl.innerHTML = `
        <div class="cm-hud-top">
          <div class="cm-hud-brand">
            <span class="cm-pulse-dot"></span>
            <span>CYBER MAP &bull; NETWORK TOPOLOGY</span>
            <span class="cm-privacy-pill is-local" id="cm-privacy-pill" title="Follows Privacy Shield state">LOCAL ONLY</span>
          </div>

          <div class="cm-hud-stats">
            <span class="cm-stat-chip"><i class="fas fa-circle-nodes" style="color:#38bdf8;"></i> <strong id="cm-stat-nodes">0</strong> nodes</span>
            <span class="cm-stat-chip"><i class="fas fa-diagram-project" style="color:#22d3ee;"></i> <strong id="cm-stat-edges">0</strong> links</span>
            <span class="cm-stat-chip"><i class="fas fa-route" style="color:#a855f7;"></i> <strong id="cm-stat-circuits">0</strong> Tor</span>
          </div>

          <div class="cm-hud-controls">
            ${this.isStandalone ? `
              <select id="cm-session-select" class="cm-session-select" title="Load a saved search session into the Cyber Map">
                <option value="">Live Sync (Active Search)</option>
              </select>
            ` : ''}

            <div class="cm-view-switch" title="Switch between 3D Globe (Globe.gl) and lightweight 2D Map">
              <button type="button" class="cm-btn is-active" id="cm-btn-3d"><i class="fas fa-globe"></i> 3D</button>
              <button type="button" class="cm-btn" id="cm-btn-2d"><i class="fas fa-map"></i> 2D</button>
            </div>

            <button type="button" class="cm-btn is-active" id="cm-btn-rotate" title="Toggle 3D Globe Auto-Rotation">
              <i class="fas fa-sync-alt"></i>
            </button>
            <button type="button" class="cm-btn" id="cm-btn-reset" title="Reset Camera / Zoom">
              <i class="fas fa-crosshairs"></i>
            </button>
            <button type="button" class="cm-btn is-tor" id="cm-btn-newnym" title="Request New Tor Circuit (NEWNYM) and refresh hops">
              <i class="fas fa-random"></i> Tor Circuit
            </button>

            ${!this.isStandalone ? `
              <button type="button" class="cm-btn" id="cm-btn-popout" title="Open Cyber Map in a dedicated separate window">
                <i class="fas fa-external-link-alt"></i> Window
              </button>
              <button type="button" class="cm-btn" id="cm-btn-fullscreen" title="Toggle Fullscreen Cyber Map">
                <i class="fas fa-expand"></i>
              </button>
              <button type="button" class="cm-btn" id="cm-btn-close" title="Collapse Cyber Map">
                <i class="fas fa-times"></i>
              </button>
            ` : ''}
          </div>
        </div>

        <div class="cm-proto-strip" id="cm-proto-strip"></div>

        <div class="cm-stage" id="cm-stage">
          <div class="cm-canvas-layer" id="cm-canvas-3d"></div>
          <div class="cm-canvas-layer is-hidden" id="cm-canvas-2d"></div>

          <div class="cm-tor-banner" id="cm-tor-banner">
            <div class="cm-tor-banner-title">
              <i class="fas fa-user-secret"></i>
              <span id="cm-tor-status-text">Tor Telemetry: Checking...</span>
            </div>
            <div class="cm-tor-hops" id="cm-tor-hops"></div>
          </div>

          <aside class="cm-inspector" id="cm-inspector">
            <div class="cm-inspector-hdr">
              <div class="cm-inspector-title" id="cm-insp-title">Node Inspector</div>
              <button type="button" class="cm-btn" id="cm-insp-close" style="padding:2px 6px;"><i class="fas fa-times"></i></button>
            </div>
            <div class="cm-inspector-body" id="cm-insp-body"></div>
          </aside>
        </div>

        <div class="cm-resizer-bottom" id="cm-resizer-bottom" title="Drag vertically to resize Cyber Map height"></div>
      `;

      const q = (id) => this.dockEl.querySelector('#' + id);
      this.els = {
        privacyPill: q('cm-privacy-pill'),
        statNodes: q('cm-stat-nodes'),
        statEdges: q('cm-stat-edges'),
        statCircuits: q('cm-stat-circuits'),
        sessionSelect: q('cm-session-select'),
        btn3d: q('cm-btn-3d'),
        btn2d: q('cm-btn-2d'),
        btnRotate: q('cm-btn-rotate'),
        btnReset: q('cm-btn-reset'),
        btnNewnym: q('cm-btn-newnym'),
        btnPopout: q('cm-btn-popout'),
        btnFullscreen: q('cm-btn-fullscreen'),
        btnClose: q('cm-btn-close'),
        protoStrip: q('cm-proto-strip'),
        stage: q('cm-stage'),
        canvas3d: q('cm-canvas-3d'),
        canvas2d: q('cm-canvas-2d'),
        torStatusText: q('cm-tor-status-text'),
        torHops: q('cm-tor-hops'),
        inspector: q('cm-inspector'),
        inspTitle: q('cm-insp-title'),
        inspBody: q('cm-insp-body'),
        inspClose: q('cm-insp-close'),
        resizerBottom: q('cm-resizer-bottom')
      };

      this._bindControls();
    }

    _bindControls() {
      const e = this.els;
      e.btn3d.addEventListener('click', () => this.ctrl.setViewMode('3d'));
      e.btn2d.addEventListener('click', () => this.ctrl.setViewMode('2d'));
      e.btnRotate.addEventListener('click', () => this.ctrl.toggleAutoRotate());
      e.btnReset.addEventListener('click', () => this.ctrl.resetView());
      e.btnNewnym.addEventListener('click', () => this.ctrl.requestNewTorCircuit());
      if (e.btnPopout) e.btnPopout.addEventListener('click', () => this.ctrl.openStandaloneWindow());
      if (e.btnFullscreen) e.btnFullscreen.addEventListener('click', () => this.ctrl.toggleFullscreen());
      if (e.btnClose) e.btnClose.addEventListener('click', () => this.ctrl.closeDock());
      if (e.inspClose) e.inspClose.addEventListener('click', () => this.ctrl.state.selectNode(null));
      if (e.sessionSelect) {
        e.sessionSelect.addEventListener('change', (ev) => {
          this.ctrl.loadSessionById(ev.target.value);
        });
      }
    }

    updateViewButtons(viewMode, autoRotate) {
      this.els.btn3d.classList.toggle('is-active', viewMode === '3d');
      this.els.btn2d.classList.toggle('is-active', viewMode === '2d');
      this.els.canvas3d.classList.toggle('is-hidden', viewMode !== '3d');
      this.els.canvas2d.classList.toggle('is-hidden', viewMode !== '2d');
      this.els.btnRotate.style.display = viewMode === '3d' ? 'inline-flex' : 'none';
      this.els.btnRotate.classList.toggle('is-active', Boolean(autoRotate));
    }

    updatePrivacyPill(localOnly) {
      const el = this.els.privacyPill;
      if (!el) return;
      if (localOnly) {
        el.className = 'cm-privacy-pill is-local';
        el.textContent = 'PRIVACY: LOCAL ONLY';
        el.title = 'Zero external DNS/GeoIP lookups — offline GeoDB + Tor GeoIP only';
      } else {
        el.className = 'cm-privacy-pill is-external';
        el.textContent = 'DNS ACTIVE (ALL ENGINES)';
        el.title = 'Resolving target IPv4/IPv6 addresses via DNS';
      }
    }

    renderStats(graph, state) {
      this.els.statNodes.textContent = String((graph.nodes || []).length);
      this.els.statEdges.textContent = String((graph.edges || []).length);
      this.els.statCircuits.textContent = String((state.torCircuits || []).length);
      this.updatePrivacyPill(state.localOnly);
      this.renderTorBanner(state);
      this.renderProtocolStrip(state);
    }

    renderTorBanner(state) {
      if (!state.torOnline) {
        this.els.torStatusText.textContent = 'Tor Daemon Offline (Clearnet / Local Mode)';
        this.els.torHops.innerHTML = '<span style="color:#94a3b8;">Start Tor daemon in Engines or Settings to inspect live .onion circuits.</span>';
        return;
      }
      const circs = state.torCircuits || [];
      if (circs.length === 0) {
        this.els.torStatusText.textContent = 'Tor Online — Waiting for built circuit';
        this.els.torHops.innerHTML = '<span class="cm-hop-badge">127.0.0.1 SOCKS5h</span>';
        return;
      }
      const primary = circs[0];
      this.els.torStatusText.textContent = `Tor Circuit #${primary.circuit_id} (${primary.purpose || 'GENERAL'})`;
      const hopHtml = (primary.hops || []).map((h) => {
        const ipTxt = h.ip ? ` ${h.ip}` : '';
        return `<span class="cm-hop-badge" title="FP: ${esc(h.fingerprint)}">${esc((h.role || '').toUpperCase())}: ${esc(h.nickname)} [${esc(h.country_code)}${esc(ipTxt)}]</span>`;
      }).join(' <span>&rarr;</span> ');
      this.els.torHops.innerHTML = `<span class="cm-hop-badge">Hecos</span> <span>&rarr;</span> ${hopHtml}`;
    }

    renderProtocolStrip(state) {
      const counts = state.getProtocolCounts();
      const active = state.activeProtocol || 'all';
      const chips = [
        `<button type="button" class="cm-proto-chip ${active === 'all' ? 'is-active' : ''}" data-proto="all">
          <span class="cm-proto-dot" style="background:#e2e8f0;"></span>
          <span>All Protocols</span>
          <span class="cm-proto-count">${counts.all || 0}</span>
        </button>`
      ];

      Object.entries(state.protocols || {}).forEach(([pid, spec]) => {
        const cnt = counts[pid] || 0;
        if (cnt === 0 && active !== pid) return;
        chips.push(`
          <button type="button" class="cm-proto-chip ${active === pid ? 'is-active' : ''}" data-proto="${esc(pid)}" title="${esc(spec.transport || '')}">
            <span class="cm-proto-dot" style="background:${esc(spec.color)};"></span>
            <span>${esc(spec.label)}</span>
            <span class="cm-proto-count">${cnt}</span>
          </button>
        `);
      });

      this.els.protoStrip.innerHTML = chips.join('');
      this.els.protoStrip.querySelectorAll('.cm-proto-chip').forEach((btn) => {
        btn.addEventListener('click', () => {
          state.setActiveProtocol(btn.getAttribute('data-proto') || 'all');
        });
      });
    }

    renderInspector(nodeDetails) {
      const insp = this.els.inspector;
      if (!nodeDetails) {
        insp.classList.remove('is-open');
        return;
      }
      insp.classList.add('is-open');
      this.els.inspTitle.textContent = nodeDetails.label || nodeDetails.host;

      const meta = nodeDetails.metadata || {};
      const addrStr = nodeDetails.ip ? `${nodeDetails.host} (${nodeDetails.ip})` : nodeDetails.host;
      const results = nodeDetails.results || [];

      this.els.inspBody.innerHTML = `
        <div class="cm-kv-grid">
          <div class="cm-kv-k">Host / ID</div><div class="cm-kv-v">${esc(addrStr)}</div>
          ${nodeDetails.ipv6 ? `<div class="cm-kv-k">IPv6</div><div class="cm-kv-v">${esc(nodeDetails.ipv6)}</div>` : ''}
          <div class="cm-kv-k">Protocol</div><div class="cm-kv-v" style="color:${esc(nodeDetails.color)};">${esc(nodeDetails.protocol_label)}</div>
          <div class="cm-kv-k">Transport</div><div class="cm-kv-v">${esc(nodeDetails.transport)}</div>
          <div class="cm-kv-k">Port</div><div class="cm-kv-v">${nodeDetails.port || 'N/A'}</div>
          <div class="cm-kv-k">Location</div><div class="cm-kv-v">${esc(nodeDetails.country_name)}${nodeDetails.city ? ' • ' + esc(nodeDetails.city) : ''} (${esc(nodeDetails.geo_source)})</div>
          ${meta.fingerprint ? `<div class="cm-kv-k">Tor FP</div><div class="cm-kv-v">${esc(meta.fingerprint)}</div>` : ''}
          ${(nodeDetails.engines && nodeDetails.engines.length) ? `<div class="cm-kv-k">Engines</div><div class="cm-kv-v">${esc(nodeDetails.engines.join(', '))}</div>` : ''}
        </div>

        <div class="cm-inspector-actions">
          <button type="button" class="cm-btn" id="cm-insp-copy"><i class="fas fa-copy"></i> Copy Addr</button>
          ${nodeDetails.node_type !== 'local_core' && nodeDetails.node_type !== 'tor_relay' ? `
            <button type="button" class="cm-btn is-active" id="cm-insp-filter"><i class="fas fa-filter"></i> Filter in Search</button>
          ` : ''}
        </div>

        ${results.length > 0 ? `
          <div class="cm-inspector-results">
            <div style="font-size:10px; color:#94a3b8; font-weight:700;">MATCHED RESULTS (${results.length}):</div>
            ${results.slice(0, 20).map((r) => {
              const href = (r.url && r.url.toLowerCase().includes('.onion'))
                ? '/search/viewer?url=' + encodeURIComponent(r.url)
                : r.url;
              return `<a class="cm-inspector-res-item" href="${esc(href)}" target="_blank" rel="noopener noreferrer">
                <span class="res-t">${esc(r.title)}</span>
                <span class="res-u">${esc(r.url)}</span>
              </a>`;
            }).join('')}
          </div>
        ` : ''}
      `;

      const copyBtn = this.els.inspBody.querySelector('#cm-insp-copy');
      if (copyBtn) {
        copyBtn.addEventListener('click', () => {
          const val = nodeDetails.ip || nodeDetails.host || '';
          if (navigator.clipboard && val) navigator.clipboard.writeText(val).catch(() => {});
          copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied';
        });
      }

      const filterBtn = this.els.inspBody.querySelector('#cm-insp-filter');
      if (filterBtn) {
        filterBtn.addEventListener('click', () => {
          this.ctrl.filterSearchByHost(nodeDetails.host);
        });
      }
    }

    populateSessionOptions(sessions, selectedId) {
      if (!this.els.sessionSelect) return;
      const opts = ['<option value="">Live Sync (Active Search)</option>'];
      (sessions || []).slice(0, 30).forEach((s) => {
        const label = `${s.title || s.query} [${String(s.mode || 'clear').toUpperCase()} • ${s.total_results || 0}]`;
        opts.push(`<option value="${esc(s.id)}" ${s.id === selectedId ? 'selected' : ''}>${esc(label)}</option>`);
      });
      this.els.sessionSelect.innerHTML = opts.join('');
    }
  }

  window.CyberMapHUD = CyberMapHUD;
})();
