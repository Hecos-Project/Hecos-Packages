/**
 * cyber_map_state.js
 * Graph state manager for the Net Search Cyber Map.
 * Aggregates multi-protocol infrastructure nodes, live Tor circuit hops, and search target hosts.
 */
(function () {
  const DEFAULT_PROTOCOLS = {
    local_ipc: { protocol_id: 'local_ipc', label: 'Local IPC', color: '#06b6d4', transport: '127.0.0.1' },
    searxng_rpc: { protocol_id: 'searxng_rpc', label: 'SearXNG', color: '#22d3ee', transport: 'HTTP Meta-RPC' },
    tor_circuit: { protocol_id: 'tor_circuit', label: 'Tor Circuit', color: '#a855f7', transport: 'SOCKS5h -> Tor OR' },
    onion_v3: { protocol_id: 'onion_v3', label: 'DarkWeb (.onion)', color: '#f43f5e', transport: 'Hidden Service v3' },
    https: { protocol_id: 'https', label: 'HTTPS', color: '#3b82f6', transport: 'TCP/443 TLS' },
    http: { protocol_id: 'http', label: 'HTTP', color: '#60a5fa', transport: 'TCP/80' },
    osint_api: { protocol_id: 'osint_api', label: 'OSINT', color: '#f59e0b', transport: 'OSINT REST / Sherlock' },
    file_dork: { protocol_id: 'file_dork', label: 'Files', color: '#10b981', transport: 'File Hunter' },
    media_stream: { protocol_id: 'media_stream', label: 'Media', color: '#ec4899', transport: 'Media / yt-dlp' },
    rss_feed: { protocol_id: 'rss_feed', label: 'RSS / News', color: '#38bdf8', transport: 'RSS/Atom' },
    sqlite_dir: { protocol_id: 'sqlite_dir', label: 'SQLite Index', color: '#14b8a6', transport: 'Local SQLite3' },
    p2p_magnet: { protocol_id: 'p2p_magnet', label: 'Magnet', color: '#84cc16', transport: 'DHT URI' },
    ftp: { protocol_id: 'ftp', label: 'FTP', color: '#34d399', transport: 'TCP/21' }
  };

  function hashString(str) {
    let h = 2166136261;
    const s = String(str || '');
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function extractHost(url) {
    const raw = String(url || '').trim();
    if (!raw) return '';
    if (raw.startsWith('magnet:')) return 'dht.magnet';
    try {
      const u = new URL(raw.includes('://') ? raw : ('https://' + raw));
      return (u.hostname || '').toLowerCase();
    } catch (_e) {
      return raw.split('/')[0].split(':')[0].toLowerCase();
    }
  }

  function extractPort(url, protocol) {
    try {
      const u = new URL(String(url || ''));
      if (u.port) return parseInt(u.port, 10);
      if (u.protocol === 'http:') return 80;
      if (u.protocol === 'https:') return 443;
      if (u.protocol === 'ftp:') return 21;
    } catch (_e) { /* ignore */ }
    if (protocol === 'onion_v3') return 80;
    if (protocol === 'tor_circuit') return 9055;
    if (protocol === 'local_ipc') return 8889;
    return 443;
  }

  function quickClassify(item) {
    const url = String(item.url || '');
    const host = extractHost(url);
    const engId = String(item.engine_id || '').toLowerCase();
    const eng = String(item.engine || '').toLowerCase();
    const cat = String(item.category || '').toLowerCase();
    const net = String(item.network || '').toLowerCase();

    if (url.startsWith('magnet:')) return { protocol: 'p2p_magnet', host: 'dht.magnet', port: 6881 };
    if (host.endsWith('.onion') || net === 'tor' || engId.startsWith('dark_')) {
      return { protocol: 'onion_v3', host, port: extractPort(url, 'onion_v3') };
    }
    if (engId.includes('domain_directory') || eng.includes('sqlite')) {
      return { protocol: 'sqlite_dir', host: host || 'domain_lists.sqlite', port: 0 };
    }
    if (engId.startsWith('osint_') || cat === 'osint') {
      return { protocol: 'osint_api', host, port: extractPort(url, 'osint_api') };
    }
    if (engId.startsWith('files_') || cat === 'files') {
      return { protocol: 'file_dork', host, port: extractPort(url, 'file_dork') };
    }
    if (engId.startsWith('media_') || ['videos', 'images', 'audio'].includes(cat)) {
      return { protocol: 'media_stream', host, port: extractPort(url, 'media_stream') };
    }
    if (engId.includes('news') || eng.includes('rss:') || cat === 'news') {
      return { protocol: 'rss_feed', host, port: extractPort(url, 'rss_feed') };
    }
    if (engId.includes('searxng')) {
      return { protocol: 'searxng_rpc', host, port: extractPort(url, 'searxng_rpc') };
    }
    if (url.startsWith('http://')) {
      return { protocol: 'http', host, port: extractPort(url, 'http') };
    }
    return { protocol: 'https', host, port: extractPort(url, 'https') };
  }

  function quickOfflineLatLon(host, anchorLat, anchorLon) {
    const h = hashString(host);
    if (host.endsWith('.onion')) {
      const ang = ((h & 0xffff) / 65535) * Math.PI * 2;
      const rad = 7 + (((h >>> 16) & 0xffff) / 65535) * 11;
      const baseLat = typeof anchorLat === 'number' ? anchorLat : 22.0;
      const baseLon = typeof anchorLon === 'number' ? anchorLon : -38.0;
      return {
        lat: Math.max(-68, Math.min(68, baseLat + Math.sin(ang) * rad)),
        lon: ((baseLon + Math.cos(ang) * rad * 1.2 + 540) % 360) - 180,
        cc: 'ONION',
        cname: 'Tor Darknet Layer',
        virtual: true
      };
    }
    const hubs = [
      [39.04, -77.48, 'US', 'United States'],
      [37.77, -122.41, 'US', 'United States'],
      [50.11, 8.68, 'DE', 'Germany'],
      [52.36, 4.90, 'NL', 'Netherlands'],
      [51.50, -0.12, 'GB', 'United Kingdom'],
      [48.85, 2.35, 'FR', 'France'],
      [41.87, 12.56, 'IT', 'Italy'],
      [35.68, 139.69, 'JP', 'Japan'],
      [1.35, 103.81, 'SG', 'Singapore']
    ];
    const c = hubs[h % hubs.length];
    const ang = (((h >>> 8) & 0xff) / 255) * Math.PI * 2;
    const rad = 0.6 + (((h >>> 16) & 0xff) / 255) * 2.5;
    return {
      lat: c[0] + Math.sin(ang) * rad,
      lon: c[1] + Math.cos(ang) * rad,
      cc: c[2],
      cname: c[3],
      virtual: true
    };
  }

  class CyberMapState {
    constructor() {
      this.protocols = Object.assign({}, DEFAULT_PROTOCOLS);
      this.baseNodes = [];
      this.baseEdges = [];
      this.torCircuits = [];
      this.torOnline = false;
      this.searxOnline = false;
      this.localOnly = true;
      this.query = '';
      this.mode = 'clear';
      this.sessionId = null;

      this.targetNodes = new Map();     // nodeId -> Node
      this.targetEdges = new Map();     // edgeId -> Edge
      this.hostResults = new Map();     // nodeId -> Array<Result>
      this.resolvedHosts = new Map();   // `${host}|${protocol}` -> resolved telemetry
      this.pendingResolve = new Map();  // key -> raw payload
      this.activeProtocol = 'all';
      this.selectedNodeId = null;
      this._resolveTimer = null;
      this._listeners = new Set();
    }

    subscribe(fn) {
      if (typeof fn === 'function') this._listeners.add(fn);
      return () => this._listeners.delete(fn);
    }

    _notify(reason) {
      this._listeners.forEach((fn) => {
        try { fn(reason, this); } catch (e) { console.warn('[CyberMapState] subscriber err', e); }
      });
    }

    setLocalOnly(val) {
      const next = Boolean(val);
      if (this.localOnly !== next) {
        this.localOnly = next;
        // Re-resolve hosts if switching to ALL ENGINES so real IPs get fetched
        if (!next && this.targetNodes.size > 0) {
          this.resolvedHosts.clear();
          this.targetNodes.forEach((node) => {
            const key = `${node.host}|${node.protocol}`;
            this.pendingResolve.set(key, {
              host: node.host,
              url: node.sampleUrl || '',
              engine_id: node.engines[0] || '',
              protocol: node.protocol,
              network: node.network
            });
          });
          this._scheduleBatchResolve();
        }
        this._notify('privacy');
      }
    }

    setActiveProtocol(proto) {
      this.activeProtocol = proto || 'all';
      this._notify('filter');
    }

    selectNode(nodeId) {
      this.selectedNodeId = nodeId || null;
      this._notify('select');
    }

    getRendezvousAnchor() {
      // Use real Exit or Rendezvous Tor relay coordinates when available to anchor .onion darknet nodes
      for (const circ of this.torCircuits) {
        const hops = circ.hops || [];
        if (hops.length > 0) {
          const tail = hops[hops.length - 1];
          if (typeof tail.lat === 'number' && typeof tail.lon === 'number' && (tail.lat !== 0 || tail.lon !== 0)) {
            return { nodeId: `tor_relay:${tail.fingerprint}`, lat: tail.lat, lon: tail.lon };
          }
        }
      }
      if (this.baseNodes.some(n => n.id === 'local:tor_socks')) {
        return { nodeId: 'local:tor_socks', lat: 24.0, lon: -36.0 };
      }
      return { nodeId: 'local:hecos_core', lat: 24.0, lon: -36.0 };
    }

    applyTopology(data) {
      if (!data || !data.ok) return;
      this.baseNodes = Array.isArray(data.nodes) ? data.nodes : [];
      this.baseEdges = Array.isArray(data.edges) ? data.edges : [];
      this.searxOnline = Boolean(data.searx_online);
      this.localOnly = Boolean(data.local_only);
      if (data.protocols) {
        this.protocols = Object.assign({}, DEFAULT_PROTOCOLS, data.protocols);
      }
      if (data.tor) {
        this.torOnline = Boolean(data.tor.tor_online);
        this.torCircuits = Array.isArray(data.tor.circuits) ? data.tor.circuits : [];
      }
      this._reanchorOnionNodes();
      this._notify('topology');
    }

    applyTorCircuits(data) {
      if (!data) return;
      this.torOnline = Boolean(data.tor_online);
      this.torCircuits = Array.isArray(data.circuits) ? data.circuits : [];
      // Rebuild tor_relay nodes & edges cleanly inside baseNodes/baseEdges
      this.baseNodes = this.baseNodes.filter(n => n.node_type !== 'tor_relay');
      this.baseEdges = this.baseEdges.filter(e => !String(e.id || '').startsWith('edge:circ:'));

      const seenRelays = new Set();
      this.torCircuits.slice(0, 4).forEach((circ) => {
        const cid = circ.circuit_id;
        let prevId = 'local:tor_socks';
        (circ.hops || []).forEach((hop) => {
          const hopId = `tor_relay:${hop.fingerprint}`;
          if (!seenRelays.has(hopId)) {
            seenRelays.add(hopId);
            this.baseNodes.push({
              id: hopId,
              label: `${hop.nickname} (${String(hop.role || '').toUpperCase()})`,
              host: hop.ip || hop.fingerprint.slice(0, 12),
              node_type: 'tor_relay',
              network: 'tor',
              protocol: 'tor_circuit',
              protocol_label: 'Tor OR Relay',
              transport: `Tor OR/${hop.or_port || 9001}`,
              port: hop.or_port || 9001,
              ip: hop.ip || null,
              lat: hop.lat,
              lon: hop.lon,
              country_code: hop.country_code || 'XX',
              country_name: hop.country_name || 'Tor Relay',
              city: `Tor ${hop.role} Relay`,
              geo_source: 'tor_control',
              color: '#a855f7',
              engines: [],
              result_count: 0,
              metadata: { fingerprint: hop.fingerprint, role: hop.role, circuit_id: cid, purpose: circ.purpose }
            });
          }
          this.baseEdges.push({
            id: `edge:circ:${cid}:${prevId}->${hopId}`,
            source: prevId,
            target: hopId,
            protocol: 'tor_circuit',
            protocol_label: `Tor Circuit #${cid}`,
            color: '#a855f7',
            weight: 2,
            dashed: false,
            circuit_id: cid
          });
          prevId = hopId;
        });
      });

      this._reanchorOnionNodes();
      this._notify('tor_circuits');
    }

    _reanchorOnionNodes() {
      const anchor = this.getRendezvousAnchor();
      this.targetEdges.forEach((edge) => {
        if (edge.protocol === 'onion_v3') {
          edge.source = anchor.nodeId;
        }
      });
    }

    resetSearch(meta) {
      this.targetNodes.clear();
      this.targetEdges.clear();
      this.hostResults.clear();
      this.pendingResolve.clear();
      this.selectedNodeId = null;
      if (meta) {
        if (meta.query !== undefined) this.query = meta.query;
        if (meta.mode !== undefined) this.mode = meta.mode;
        if (meta.sessionId !== undefined) this.sessionId = meta.sessionId;
        if (meta.localOnly !== undefined) this.localOnly = Boolean(meta.localOnly);
      }
      this._notify('reset');
    }

    ingestResults(items, defaultEngineId) {
      if (!Array.isArray(items) || items.length === 0) return;
      const anchor = this.getRendezvousAnchor();
      let changed = false;

      for (const raw of items) {
        if (!raw || !raw.url) continue;
        const { protocol, host, port } = quickClassify(raw);
        if (!host) continue;

        const key = `${host}|${protocol}`;
        const nodeId = `target:${key}`;
        const protoSpec = this.protocols[protocol] || DEFAULT_PROTOCOLS[protocol] || DEFAULT_PROTOCOLS.https;
        const engId = raw.engine_id || defaultEngineId || 'search';

        if (!this.hostResults.has(nodeId)) {
          this.hostResults.set(nodeId, []);
        }
        const list = this.hostResults.get(nodeId);
        if (!list.some(r => r.url === raw.url)) {
          list.push({
            title: raw.title || host,
            url: raw.url,
            engine: raw.engine || engId,
            engine_id: engId,
            category: raw.category || 'general'
          });
        }

        const cached = this.resolvedHosts.get(key);
        if (!this.targetNodes.has(nodeId)) {
          const fallbackGeo = quickOfflineLatLon(host, anchor.lat, anchor.lon);
          const geo = cached || {
            lat: fallbackGeo.lat,
            lon: fallbackGeo.lon,
            country_code: fallbackGeo.cc,
            country_name: fallbackGeo.cname,
            city: '',
            ip: null,
            ipv6: null,
            geo_source: 'instant_est',
            is_virtual: fallbackGeo.virtual,
            port: port
          };

          this.targetNodes.set(nodeId, {
            id: nodeId,
            label: host,
            host: host,
            node_type: protocol === 'onion_v3' ? 'onion_service' : (protocol === 'osint_api' ? 'osint_target' : (protocol === 'file_dork' ? 'file_host' : 'web_host')),
            network: (protocol === 'onion_v3' || host.endsWith('.onion')) ? 'tor' : 'clearnet',
            protocol: protocol,
            protocol_label: protoSpec.label,
            transport: protoSpec.transport,
            port: geo.port || port,
            ip: geo.ip || null,
            ipv6: geo.ipv6 || null,
            lat: geo.lat,
            lon: geo.lon,
            country_code: geo.country_code,
            country_name: geo.country_name,
            city: geo.city || '',
            geo_source: geo.geo_source || 'instant_est',
            is_virtual: Boolean(geo.is_virtual),
            color: protoSpec.color,
            engines: [engId],
            result_count: list.length,
            sampleUrl: raw.url,
            isFresh: true
          });

          // Build routing edge from appropriate upstream daemon
          let srcId = 'local:hecos_core';
          if (protocol === 'onion_v3') {
            srcId = anchor.nodeId;
          } else if (protocol === 'searxng_rpc' || (engId === 'clear_searxng' && this.searxOnline)) {
            srcId = this.baseNodes.some(n => n.id === 'local:searxng') ? 'local:searxng' : 'local:hecos_core';
          } else if (protocol === 'sqlite_dir') {
            srcId = this.baseNodes.some(n => n.id === 'local:domain_sqlite') ? 'local:domain_sqlite' : 'local:hecos_core';
          }

          const edgeId = `edge:${srcId}->${nodeId}`;
          this.targetEdges.set(edgeId, {
            id: edgeId,
            source: srcId,
            target: nodeId,
            protocol: protocol,
            protocol_label: protoSpec.label,
            color: protoSpec.color,
            weight: 1,
            dashed: protocol === 'onion_v3'
          });

          if (!cached && !this.pendingResolve.has(key)) {
            this.pendingResolve.set(key, {
              host: host,
              url: raw.url,
              engine_id: engId,
              engine: raw.engine || '',
              category: raw.category || '',
              network: raw.network || ''
            });
          }
          changed = true;
        } else {
          const existing = this.targetNodes.get(nodeId);
          existing.result_count = list.length;
          if (engId && !existing.engines.includes(engId)) {
            existing.engines.push(engId);
          }
          const edge = this.targetEdges.get(`edge:${this._findSourceForTarget(nodeId)}->${nodeId}`);
          if (edge) {
            edge.weight = Math.min(6, 1 + Math.floor(Math.log2(Math.max(1, list.length))));
          }
          changed = true;
        }
      }

      if (this.pendingResolve.size > 0) {
        this._scheduleBatchResolve();
      }
      if (changed) {
        this._notify('results');
      }
    }

    _findSourceForTarget(targetId) {
      for (const e of this.targetEdges.values()) {
        if (e.target === targetId) return e.source;
      }
      return 'local:hecos_core';
    }

    _scheduleBatchResolve() {
      if (this._resolveTimer) return;
      this._resolveTimer = setTimeout(() => {
        this._resolveTimer = null;
        this._flushBatchResolve();
      }, 280);
    }

    async _flushBatchResolve() {
      if (this.pendingResolve.size === 0) return;
      const entries = Array.from(this.pendingResolve.entries()).slice(0, 80);
      entries.forEach(([k]) => this.pendingResolve.delete(k));
      const payloadItems = entries.map(([, v]) => v);

      try {
        const res = await fetch('/api/hsearch/cyber_map/resolve_batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: payloadItems, local_only: this.localOnly })
        });
        if (!res.ok) return;
        const data = await res.json();
        if (!data || !data.ok || !Array.isArray(data.resolved)) return;

        let updated = false;
        const anchor = this.getRendezvousAnchor();
        for (const r of data.resolved) {
          const key = `${r.host}|${r.protocol}`;
          this.resolvedHosts.set(key, r);
          const nodeId = `target:${key}`;
          const node = this.targetNodes.get(nodeId);
          if (node) {
            if (r.protocol === 'onion_v3') {
              // Anchor darknet layer around rendezvous node when real circuit exists
              const off = quickOfflineLatLon(r.host, anchor.lat, anchor.lon);
              node.lat = off.lat;
              node.lon = off.lon;
            } else {
              node.lat = r.lat;
              node.lon = r.lon;
            }
            node.ip = r.ip || node.ip;
            node.ipv6 = r.ipv6 || node.ipv6;
            node.port = r.port !== undefined ? r.port : node.port;
            node.country_code = r.country_code || node.country_code;
            node.country_name = r.country_name || node.country_name;
            node.city = r.city || node.city;
            node.geo_source = r.geo_source || node.geo_source;
            node.is_virtual = Boolean(r.is_virtual);
            node.protocol = r.protocol || node.protocol;
            node.protocol_label = r.protocol_label || node.protocol_label;
            node.transport = r.transport || node.transport;
            node.color = r.color || node.color;
            updated = true;
          }
        }
        if (updated) {
          this._notify('resolved');
        }
      } catch (err) {
        console.warn('[CyberMapState] batch resolve error:', err);
      }

      if (this.pendingResolve.size > 0) {
        this._scheduleBatchResolve();
      }
    }

    getProtocolCounts() {
      const counts = { all: 0 };
      const allNodes = this.getAllNodesRaw();
      allNodes.forEach((n) => {
        counts.all += 1;
        counts[n.protocol] = (counts[n.protocol] || 0) + 1;
      });
      return counts;
    }

    getAllNodesRaw() {
      const merged = [];
      const seen = new Set();
      this.baseNodes.forEach((n) => {
        if (!seen.has(n.id)) {
          seen.add(n.id);
          merged.push(n);
        }
      });
      this.targetNodes.forEach((n) => {
        if (!seen.has(n.id)) {
          seen.add(n.id);
          merged.push(n);
        }
      });
      return merged;
    }

    getVisibleGraph() {
      const filter = this.activeProtocol || 'all';
      const rawNodes = this.getAllNodesRaw();
      const rawEdges = [...this.baseEdges, ...Array.from(this.targetEdges.values())];

      const visibleNodes = filter === 'all'
        ? rawNodes
        : rawNodes.filter((n) => n.protocol === filter || n.node_type === 'local_core');

      const nodeIndex = new Map();
      visibleNodes.forEach((n) => nodeIndex.set(n.id, n));

      const visibleEdges = [];
      rawEdges.forEach((e) => {
        const src = nodeIndex.get(e.source);
        const dst = nodeIndex.get(e.target);
        if (!src || !dst) return;
        if (filter !== 'all' && e.protocol !== filter && dst.protocol !== filter) return;
        visibleEdges.push({
          id: e.id,
          source: e.source,
          target: e.target,
          startLat: src.lat,
          startLon: src.lon,
          endLat: dst.lat,
          endLon: dst.lon,
          protocol: e.protocol,
          protocol_label: e.protocol_label,
          color: e.color || dst.color || '#38bdf8',
          weight: e.weight || 1,
          dashed: Boolean(e.dashed),
          circuit_id: e.circuit_id || null
        });
      });

      // Keep local_core + connected infra + filtered nodes
      return {
        nodes: visibleNodes,
        edges: visibleEdges
      };
    }

    getNodeDetails(nodeId) {
      if (!nodeId) return null;
      const node = this.getAllNodesRaw().find(n => n.id === nodeId);
      if (!node) return null;
      const results = this.hostResults.get(nodeId) || [];
      return Object.assign({}, node, { results });
    }
  }

  window.CyberMapState = new CyberMapState();
})();
