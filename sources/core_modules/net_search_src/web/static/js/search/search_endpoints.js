/**
 * search_endpoints.js
 * Modular Resilient Search Endpoints, Nodes & Fallbacks Manager for Hecos Deep Search.
 * Provides rich card rendering, automatic URL decomposition/composition,
 * protocol selection (including custom protocols), port configuration, and persistence.
 */
window.SearchEndpoints = (function () {

  function escapeHtml(str) {
    if (!str && str !== 0) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function decomposeUrl(rawUrl, defaultName = '', defaultProto = 'https', useApiKey = false, apiKey = '') {
    if (!rawUrl) {
      return {
        name: defaultName,
        protocol: defaultProto,
        host: '',
        port: '',
        path: '',
        url: '',
        enabled: true,
        use_api_key: !!useApiKey,
        api_key: apiKey || ''
      };
    }
    const str = String(rawUrl).trim();
    let proto = defaultProto;
    let rest = str;

    if (str.includes('://')) {
      const parts = str.split('://');
      proto = parts[0].toLowerCase();
      rest = parts[1] || '';
    }

    let host = rest;
    let port = '';
    let path = '';

    if (rest.includes('/')) {
      const slashIdx = rest.indexOf('/');
      host = rest.substring(0, slashIdx);
      path = rest.substring(slashIdx);
    }

    if (host.includes(':')) {
      const colParts = host.split(':');
      host = colParts[0];
      port = colParts[1] || '';
    }

    const computed = buildUrl(proto, host, port, path);
    return {
      name: defaultName || host,
      protocol: proto,
      host: host,
      port: port,
      path: path,
      url: computed,
      enabled: true,
      use_api_key: !!useApiKey,
      api_key: apiKey || ''
    };
  }

  function buildUrl(proto, host, port, path) {
    const p = (proto || 'https').trim().replace(/[:/]/g, '').toLowerCase();
    const h = (host || '').trim().replace(/\/$/, '');
    if (!h) return '';
    let portStr = '';
    const pt = String(port || '').trim();
    if (pt && pt !== '80' && pt !== '443') {
      portStr = ':' + pt;
    }
    let pathStr = (path || '').trim();
    if (pathStr && !pathStr.startsWith('/')) {
      pathStr = '/' + pathStr;
    }
    return `${p}://${h}${portStr}${pathStr}`;
  }

  function renderCard(item, options = {}) {
    const id = item.id || ('ep_' + Math.random().toString(36).substr(2, 9));
    const name = item.name || '';
    let proto = (item.protocol || 'https').toLowerCase().replace(/[:/]/g, '');
    const host = item.host || '';
    const port = item.port || '';
    const path = item.path || '';
    const enabled = item.enabled !== false;
    const isDeletable = !!options.isDeletable;
    const typeBadge = options.typeBadge || 'NODE';
    const computedUrl = item.url || buildUrl(proto, host, port, path);
    const standardProtos = ['https', 'http', 'rtsp', 'rtmp', 'mms', 'socks5', 'socks5h'];
    const isCustomProto = !standardProtos.includes(proto);
    const useApiKey = item.use_api_key === true;
    const apiKey = item.api_key || '';
    const sourceId = item._source_id || '';
    const searchTemplate = item.search_template || '';
    const curCat = String(item.category || options.category || (options.categoryMode === 'streams' ? 'tv' : 'general')).toLowerCase();
    const showCategory = !!options.showCategory;
    const isStreamCat = (options.categoryMode === 'streams');
    const categorySelectHtml = showCategory ? (isStreamCat ? `
      <select class="endpoint-category-select" title="Live Stream Category (TV / Radio / Webcam / Raw)"
        onchange="window.SearchEndpoints.onCategoryChange('${id}', this)"
        style="padding:3px 7px; border-radius:6px; border:1px solid var(--border); background:var(--bg0); color:var(--text); font-size:10px; font-weight:600;">
        <option value="tv" ${curCat === 'tv' ? 'selected' : ''}>TV / IPTV</option>
        <option value="radio" ${curCat === 'radio' ? 'selected' : ''}>Radio / Icecast</option>
        <option value="webcam" ${curCat === 'webcam' ? 'selected' : ''}>Live Webcam</option>
        <option value="raw" ${curCat === 'raw' ? 'selected' : ''}>Raw Stream</option>
      </select>
    ` : `
      <select class="endpoint-category-select" title="Result category / tab"
        onchange="window.SearchEndpoints.onCategoryChange('${id}', this)"
        style="padding:3px 7px; border-radius:6px; border:1px solid var(--border); background:var(--bg0); color:var(--text); font-size:10px; font-weight:600;">
        <option value="general" ${curCat === 'general' ? 'selected' : ''}>Web</option>
        ${(options.key === 'custom_tor' || options.category === 'onion' || curCat === 'onion') ? `<option value="onion" ${curCat === 'onion' ? 'selected' : ''}>Onion (All)</option>` : ''}
        <option value="videos" ${curCat === 'videos' ? 'selected' : ''}>Videos</option>
        <option value="images" ${curCat === 'images' ? 'selected' : ''}>Images</option>
        <option value="audio" ${curCat === 'audio' || curCat === 'music' ? 'selected' : ''}>Audio</option>
        <option value="files" ${curCat === 'files' ? 'selected' : ''}>Files</option>
        <option value="news" ${curCat === 'news' ? 'selected' : ''}>News</option>
      </select>
    `) : '';

    return `
      <div class="endpoint-card" id="card-${id}" data-id="${id}" data-key="${escapeHtml(options.key || '')}" data-category="${escapeHtml(curCat)}" data-source-id="${escapeHtml(sourceId)}" data-search-template="${escapeHtml(searchTemplate)}">
        <div class="endpoint-card-header">
          <div class="endpoint-card-title-group">
            <input type="text" class="endpoint-name-input" value="${escapeHtml(name)}" placeholder="Endpoint Name / Label" title="Custom name or label" oninput="window.SearchEndpoints.syncUrl('${id}')">
            <span class="badge-pill badge-neutral">${escapeHtml(typeBadge)}</span>
            ${categorySelectHtml}
            ${sourceId ? '<span class="badge-pill" style="font-size:9px; background:rgba(16,185,129,0.16); color:#34d399;" title="Managed by Source List">AUTO</span>' : ''}
          </div>
          <div class="endpoint-card-actions">
            <label class="endpoint-toggle-label" title="Enable or disable this endpoint without deleting">
              <input type="checkbox" class="endpoint-enabled-checkbox" ${enabled ? 'checked' : ''} onchange="window.SearchEndpoints.syncUrl('${id}')">
              <span class="endpoint-toggle-text">${enabled ? 'Active' : 'Disabled'}</span>
            </label>
            ${isDeletable ? `
              <button type="button" class="btn-icon-del" onclick="this.closest('.endpoint-card').remove()" title="Delete this endpoint">
                <i class="fas fa-trash"></i>
              </button>
            ` : ''}
          </div>
        </div>

        <div class="endpoint-card-fields">
          <div class="endpoint-field-col proto-col">
            <label title="Transport protocol: HTTPS, HTTP, SOCKS5/5h, or custom scheme">Protocol</label>
            <div class="proto-input-wrap">
              <select class="endpoint-proto-select" title="Select connection protocol" onchange="window.SearchEndpoints.onProtoChange('${id}', this)">
                <option value="https" ${proto === 'https' ? 'selected' : ''}>https://</option>
                <option value="http" ${proto === 'http' ? 'selected' : ''}>http://</option>
                <option value="rtsp" ${proto === 'rtsp' ? 'selected' : ''}>rtsp://</option>
                <option value="rtmp" ${proto === 'rtmp' ? 'selected' : ''}>rtmp://</option>
                <option value="mms" ${proto === 'mms' ? 'selected' : ''}>mms://</option>
                <option value="socks5" ${proto === 'socks5' ? 'selected' : ''}>socks5://</option>
                <option value="socks5h" ${proto === 'socks5h' ? 'selected' : ''}>socks5h://</option>
                <option value="custom" ${isCustomProto ? 'selected' : ''}>Custom...</option>
              </select>
              <input type="text" class="endpoint-proto-custom" value="${escapeHtml(isCustomProto ? proto : '')}" style="${isCustomProto ? '' : 'display:none;'}" placeholder="proto" title="Custom protocol scheme" oninput="window.SearchEndpoints.syncUrl('${id}')">
            </div>
          </div>

          <div class="endpoint-field-col host-col">
            <label title="Domain name, IP address, or .onion host (pasting a full URL auto-fills all fields)">Host / Address / .onion</label>
            <input type="text" class="endpoint-host-input" value="${escapeHtml(host)}" placeholder="domain.com, IP or .onion" title="Hostname, IP, or .onion address (paste full URL to auto-split)" oninput="window.SearchEndpoints.onHostInput('${id}', this)">
          </div>

          <div class="endpoint-field-col port-col">
            <label title="Optional TCP port (defaults: 80 for HTTP, 443 for HTTPS, 8889 for local SearXNG)">Port</label>
            <input type="text" class="endpoint-port-input" value="${escapeHtml(port)}" placeholder="Port (e.g. 443, 8080)" title="Custom TCP port (leave blank for standard 80/443)" oninput="window.SearchEndpoints.syncUrl('${id}')">
          </div>

          <div class="endpoint-field-col path-col">
            <label title="Endpoint path or query template; supports {q} or {searchTerms} and {api_key}">Path / Template</label>
            <input type="text" class="endpoint-path-input" value="${escapeHtml(path)}" placeholder="/search?q={q}" title="URL path or search query template (supports {q}, {searchTerms}, {api_key})" oninput="window.SearchEndpoints.syncUrl('${id}')">
          </div>
        </div>

        <div class="endpoint-api-row">
          <label class="endpoint-api-toggle-label" title="Enable API authentication: sent as Bearer/X-API-Key headers or substituted into {api_key} in Path/Template">
            <input type="checkbox" class="endpoint-api-toggle" ${useApiKey ? 'checked' : ''} onchange="window.SearchEndpoints.onApiKeyToggle('${id}', this)">
            <span class="endpoint-api-toggle-text"><i class="fas fa-key"></i> Use API Key</span>
          </label>
          <div class="endpoint-api-key-wrap" id="api-wrap-${id}" style="${useApiKey ? '' : 'display:none;'}">
            <div class="endpoint-api-input-group">
              <input type="password" class="endpoint-api-key-input" value="${escapeHtml(apiKey)}" placeholder="Enter API Token or Secret Key" title="API Key / Bearer Token (or substituted into {api_key} if present in Path/Template)" oninput="window.SearchEndpoints.syncUrl('${id}')">
              <button type="button" class="btn-api-visibility" onclick="window.SearchEndpoints.toggleKeyVisibility('${id}')" title="Show / Hide API Key">
                <i class="fas fa-eye"></i>
              </button>
            </div>
          </div>
        </div>

        <div class="endpoint-preview-row" title="Final computed request URL built from Protocol + Host + Port + Path">
          <span class="endpoint-preview-label"><i class="fas fa-link"></i> Full URL:</span>
          <code class="endpoint-preview-url" id="preview-${id}">${escapeHtml(computedUrl || '(Enter host to preview URL)')}</code>
        </div>
      </div>
    `;
  }

  function onCategoryChange(id, select) {
    const card = document.getElementById(`card-${id}`);
    if (card && select) {
      card.dataset.category = select.value || 'general';
    }
  }

  function onProtoChange(id, select) {
    const card = document.getElementById(`card-${id}`);
    if (!card) return;
    const customInput = card.querySelector('.endpoint-proto-custom');
    if (customInput) {
      if (select.value === 'custom') {
        customInput.style.display = 'inline-block';
        customInput.focus();
      } else {
        customInput.style.display = 'none';
        customInput.value = '';
      }
    }
    syncUrl(id);
  }

  function onApiKeyToggle(id, checkbox) {
    const card = document.getElementById(`card-${id}`);
    if (!card) return;
    const wrap = document.getElementById(`api-wrap-${id}`);
    if (wrap) {
      if (checkbox.checked) {
        wrap.style.display = 'block';
        const input = wrap.querySelector('.endpoint-api-key-input');
        if (input) input.focus();
      } else {
        wrap.style.display = 'none';
      }
    }
    syncUrl(id);
  }

  function toggleKeyVisibility(id) {
    const card = document.getElementById(`card-${id}`);
    if (!card) return;
    const input = card.querySelector('.endpoint-api-key-input');
    const icon = card.querySelector('.btn-api-visibility i');
    if (!input) return;
    if (input.type === 'password') {
      input.type = 'text';
      if (icon) icon.className = 'fas fa-eye-slash';
    } else {
      input.type = 'password';
      if (icon) icon.className = 'fas fa-eye';
    }
  }

  function onHostInput(id, input) {
    const card = document.getElementById(`card-${id}`);
    if (!card) return;
    const val = input.value.trim();

    // If user pasted a full URL into the host field, auto-decompose it
    if (val.includes('://')) {
      const dec = decomposeUrl(val);
      const protoSelect = card.querySelector('.endpoint-proto-select');
      const protoCustom = card.querySelector('.endpoint-proto-custom');
      const portInput = card.querySelector('.endpoint-port-input');
      const pathInput = card.querySelector('.endpoint-path-input');

      if (['https', 'http', 'socks5', 'socks5h'].includes(dec.protocol)) {
        protoSelect.value = dec.protocol;
        protoCustom.style.display = 'none';
        protoCustom.value = '';
      } else {
        protoSelect.value = 'custom';
        protoCustom.style.display = 'inline-block';
        protoCustom.value = dec.protocol;
      }

      input.value = dec.host;
      if (dec.port && portInput) portInput.value = dec.port;
      if (dec.path && pathInput) pathInput.value = dec.path;
    }

    syncUrl(id);
  }

  function syncUrl(id) {
    const card = document.getElementById(`card-${id}`);
    if (!card) return '';
    const protoSelect = card.querySelector('.endpoint-proto-select');
    const protoCustom = card.querySelector('.endpoint-proto-custom');
    const hostInput = card.querySelector('.endpoint-host-input');
    const portInput = card.querySelector('.endpoint-port-input');
    const pathInput = card.querySelector('.endpoint-path-input');
    const preview = document.getElementById(`preview-${id}`);
    const toggleText = card.querySelector('.endpoint-toggle-text');
    const checkbox = card.querySelector('.endpoint-enabled-checkbox');

    if (toggleText && checkbox) {
      toggleText.innerText = checkbox.checked ? 'Active' : 'Disabled';
    }

    let proto = protoSelect ? protoSelect.value : 'https';
    if (proto === 'custom' && protoCustom) {
      proto = protoCustom.value.trim() || 'https';
    }
    const host = hostInput ? hostInput.value.trim() : '';
    const port = portInput ? portInput.value.trim() : '';
    const path = pathInput ? pathInput.value.trim() : '';

    const fullUrl = buildUrl(proto, host, port, path);
    if (preview) {
      preview.innerText = fullUrl || '(Enter host to preview URL)';
    }
    return fullUrl;
  }

  function collectCard(card) {
    if (!card) return null;
    const id = card.dataset.id;
    const key = card.dataset.key || '';
    const catSelect = card.querySelector('.endpoint-category-select');
    const category = (catSelect ? catSelect.value : card.dataset.category) || 'general';
    const sourceId = card.dataset.sourceId || '';
    let searchTemplate = card.dataset.searchTemplate || '';
    const name = card.querySelector('.endpoint-name-input')?.value.trim() || '';

    const protoSelect = card.querySelector('.endpoint-proto-select');
    const protoCustom = card.querySelector('.endpoint-proto-custom');
    let proto = protoSelect ? protoSelect.value : 'https';
    if (proto === 'custom' && protoCustom) {
      proto = protoCustom.value.trim() || 'https';
    }
    const host = card.querySelector('.endpoint-host-input')?.value.trim() || '';
    const port = card.querySelector('.endpoint-port-input')?.value.trim() || '';
    let path = card.querySelector('.endpoint-path-input')?.value.trim() || '';
    const enabled = card.querySelector('.endpoint-enabled-checkbox')?.checked ?? true;
    const useApiKey = card.querySelector('.endpoint-api-toggle')?.checked ?? false;
    const apiKey = card.querySelector('.endpoint-api-key-input')?.value.trim() || '';
    const url = buildUrl(proto, host, port, path);
    if (url && (url.includes('{q}') || url.includes('{searchTerms}'))) {
      searchTemplate = url;
    }

    const out = { id, key, category, name, protocol: proto, host, port, path, url, enabled, use_api_key: useApiKey, api_key: apiKey };
    if (sourceId) out._source_id = sourceId;
    if (searchTemplate) out.search_template = searchTemplate;
    return out;
  }

  function collectContainer(container) {
    if (!container) return [];
    const cards = container.querySelectorAll('.endpoint-card');
    const list = [];
    cards.forEach(c => {
      const item = collectCard(c);
      if (item) list.push(item);
    });
    return list;
  }

  function addEndpoint(containerId, defaultItem = {}, options = {}) {
    const wrap = document.getElementById(containerId);
    if (!wrap) return null;
    const id = defaultItem.id || ('ep_' + Math.random().toString(36).substr(2, 9));
    const item = {
      id: id,
      name: defaultItem.name || 'New Endpoint',
      protocol: defaultItem.protocol || 'https',
      host: defaultItem.host || '',
      port: defaultItem.port || '',
      path: defaultItem.path || '',
      url: defaultItem.url || '',
      enabled: defaultItem.enabled !== false,
      use_api_key: defaultItem.use_api_key === true,
      api_key: defaultItem.api_key || '',
      category: defaultItem.category || options.category || 'general',
      search_template: defaultItem.search_template || '',
      _source_id: defaultItem._source_id || ''
    };
    const html = renderCard(item, { ...options, isDeletable: true });
    wrap.insertAdjacentHTML('beforeend', html);
    const added = document.getElementById(`card-${id}`);
    if (added) {
      const nameInp = added.querySelector('.endpoint-name-input');
      if (nameInp) nameInp.focus();
    }
    return id;
  }

  // Engine card adapters & populators are attached by hub/endpoints_adapters.js via SearchEndpointsAdapters.attach(SE).

  function collectTorAndSearxngPayload() {
    const localCard = document.querySelector('#endp-searxng-local-wrap .endpoint-card');
    const localItem = collectCard(localCard);

    const sxEngines = [];
    const _collectEngine = window.SearchEndpoints?.collectSearxngEngineCard;
    document.querySelectorAll('#endp-searxng-engines-wrap .searxng-engine-card').forEach(c => {
      const item = _collectEngine ? _collectEngine(c) : null;
      if (item && item.name) sxEngines.push(item);
    });

    const fallbacks = [];
    const customNodes = [];
    document.querySelectorAll('#endp-searxng-fallbacks-wrap .endpoint-card').forEach(c => {
      const item = collectCard(c);
      if (item && (item.host || item.url)) {
        if (c.dataset.key === 'custom_node') customNodes.push(item);
        else fallbacks.push(item);
      }
    });

    document.querySelectorAll('#endp-custom-nodes-wrap .endpoint-card').forEach(c => {
      const item = collectCard(c);
      if (item && (item.host || item.url)) customNodes.push(item);
    });

    function getTorItem(key) {
      const card = document.querySelector(`#endp-tor-engines-wrap .endpoint-card[data-key="${key}"]`);
      return collectCard(card);
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

    const customTorEngines = [];
    document.querySelectorAll('#endp-tor-engines-wrap .endpoint-card[data-key="custom_tor"]').forEach(c => {
      const item = collectCard(c);
      if (item && (item.host || item.url)) {
        const entry = {
          id: item.id,
          name: item.name || 'Custom Onion',
          category: item.category || 'onion',
          onion_url: item.url,
          protocol: item.protocol,
          host: item.host,
          port: item.port,
          path: item.path,
          search_template: item.search_template || item.path || '/search?q={q}',
          enabled: item.enabled,
          use_api_key: item.use_api_key,
          api_key: item.api_key
        };
        if (item._source_id) entry._source_id = item._source_id;
        customTorEngines.push(entry);
      }
    });

    const customStreamNodes = [];
    document.querySelectorAll('#endp-streams-nodes-wrap .endpoint-card').forEach(c => {
      const item = collectCard(c);
      if (item && (item.host || item.url)) {
        item.category = item.category || 'tv';
        customStreamNodes.push(item);
      }
    });

    return {
      localItem,
      payload: {
        searxng: {
          local_instance: localItem,
          local_url: localItem?.url || 'http://127.0.0.1:8889',
          fallbacks: fallbacks,
          engines: sxEngines
        },
        dark_ahmia: { onion: ahmiaOnion, onion_url: ahmiaOnion?.url || '', clearnet: ahmiaClear, clearnet_url: ahmiaClear?.url || '' },
        dark_torch: { torch: torchOnion, torch_onion: torchOnion?.url || '', ddg: ddgOnion, ddg_onion: ddgOnion?.url || '' },
        dark_haystak: { onion: haystakOnion, onion_url: haystakOnion?.url || '' },
        dark_onionland: { clearnet: onionlandClear, clearnet_url: onionlandClear?.url || '' },
        dark_excavator: { onion: excavatorOnion, onion_url: excavatorOnion?.url || '' },
        dark_phobos: { onion: phobosOnion, onion_url: phobosOnion?.url || '' },
        dark_tor66: { onion: tor66Onion, onion_url: tor66Onion?.url || '' },
        dark_danieltore: { onion: danielOnion, onion_url: danielOnion?.url || '' },
        custom_nodes: customNodes,
        custom_onion_engines: customTorEngines,
        custom_stream_nodes: customStreamNodes
      }
    };
  }

  const api = {
    escapeHtml,
    decomposeUrl,
    buildUrl,
    renderCard,
    onCategoryChange,
    onProtoChange,
    onApiKeyToggle,
    toggleKeyVisibility,
    onHostInput,
    syncUrl,
    collectCard,
    collectContainer,
    addEndpoint,
    collectTorAndSearxngPayload
  };
  if (window.SearchEndpointsAdapters) {
    window.SearchEndpointsAdapters.attach(api);
  }
  return api;
})();
