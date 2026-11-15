/**
 * Central Hub Search Endpoints Adapters, Engine Cards & Populaters
 * Extracted from search_endpoints.js and attached to window.SearchEndpoints.
 */
window.SearchEndpointsAdapters = (function () {
  function attach(SE) {
    if (!SE) return SE;
    const { escapeHtml, decomposeUrl, renderCard, addEndpoint } = SE;

    function _resolveWrap(wrapElOrId) {
      return typeof wrapElOrId === 'string' ? document.getElementById(wrapElOrId) : wrapElOrId;
    }

    function renderSearxngEngineCard(item) {
      const id = item.id || ('sx_eng_' + Math.random().toString(36).substr(2, 9));
      const name = item.name || item.id || '';
      const label = item.label || (name ? name.charAt(0).toUpperCase() + name.slice(1) : '');
      const category = item.category || 'general';
      const enabled = item.enabled !== false;
      const sourceId = item._source_id || '';

      return `
        <div class="endpoint-card searxng-engine-card" id="card-${id}" data-id="${id}" data-source-id="${escapeHtml(sourceId)}" style="margin-bottom:8px; border-left:3px solid var(--accent-cyan, #06b6d4);">
          <div class="endpoint-card-header" style="align-items:center;">
            <div class="endpoint-card-title-group" style="flex:1; display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
              <input type="text" class="engine-name-input" value="${escapeHtml(name)}" placeholder="Engine ID (e.g. bing, yandex)" style="font-family:monospace; font-weight:700; max-width:140px; padding:4px 8px; border-radius:6px; border:1px solid var(--border); background:var(--bg0); color:var(--text); font-size:11px;" title="SearXNG backend adapter name" oninput="window.SearchEndpoints.syncEngineCard('${id}')">
              <input type="text" class="engine-label-input" value="${escapeHtml(label)}" placeholder="Display Label (e.g. Bing Search)" style="flex:1; min-width:140px; padding:4px 8px; border-radius:6px; border:1px solid var(--border); background:var(--bg0); color:var(--text); font-size:11px;" title="Human-readable label" oninput="window.SearchEndpoints.syncEngineCard('${id}')">
              <select class="engine-category-select" style="padding:4px 8px; border-radius:6px; border:1px solid var(--border); background:var(--bg0); color:var(--text); font-size:11px;" onchange="window.SearchEndpoints.syncEngineCard('${id}')" title="Engine category">
                <option value="general" ${category === 'general' ? 'selected' : ''}>🌐 General (Web)</option>
                <option value="videos" ${category === 'videos' ? 'selected' : ''}>🎬 Videos (Media)</option>
                <option value="images" ${category === 'images' ? 'selected' : ''}>🖼️ Images</option>
                <option value="news" ${category === 'news' ? 'selected' : ''}>📰 News</option>
                <option value="files" ${category === 'files' ? 'selected' : ''}>📁 Files / Dorks</option>
                <option value="music" ${category === 'music' ? 'selected' : ''}>🎵 Music / Audio</option>
              </select>
            </div>
            <div class="endpoint-card-actions" style="display:flex; align-items:center; gap:8px;">
              <label class="endpoint-toggle-label" title="Enable or disable this engine without deleting" style="cursor:pointer;">
                <input type="checkbox" class="engine-enabled-checkbox" ${enabled ? 'checked' : ''} onchange="window.SearchEndpoints.syncEngineCard('${id}')">
                <span class="engine-toggle-text badge-pill ${enabled ? 'badge-ok' : 'badge-neutral'}" style="font-size:10px;">${enabled ? 'Active' : 'Disabled'}</span>
              </label>
              <button type="button" class="btn-icon-del" onclick="this.closest('.searxng-engine-card').remove(); if(typeof window.updateSearxngEnginesCount==='function') window.updateSearxngEnginesCount();" title="Remove this engine">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
        </div>
      `;
    }

    function syncEngineCard(id) {
      const card = document.getElementById(`card-${id}`);
      if (!card) return;
      const checkbox = card.querySelector('.engine-enabled-checkbox');
      const toggleText = card.querySelector('.engine-toggle-text');
      if (checkbox && toggleText) {
        const isAct = checkbox.checked;
        toggleText.textContent = isAct ? 'Active' : 'Disabled';
        toggleText.className = `engine-toggle-text badge-pill ${isAct ? 'badge-ok' : 'badge-neutral'}`;
      }
      if (typeof window.updateSearxngEnginesCount === 'function') {
        window.updateSearxngEnginesCount();
      }
    }

    function collectSearxngEngineCard(card) {
      if (!card) return null;
      const id = card.dataset.id;
      const name = card.querySelector('.engine-name-input')?.value.trim().toLowerCase() || '';
      const label = card.querySelector('.engine-label-input')?.value.trim() || name;
      const category = card.querySelector('.engine-category-select')?.value || 'general';
      const enabled = card.querySelector('.engine-enabled-checkbox')?.checked ?? true;
      const sourceId = card.dataset.sourceId || '';
      if (!name) return null;
      const out = { id, name, label, category, enabled };
      if (sourceId) out._source_id = sourceId;
      return out;
    }

    function addSearxngEngine(containerId, defaultItem = {}) {
      const wrap = document.getElementById(containerId);
      if (!wrap) return null;
      const id = defaultItem.id || ('sx_eng_' + Math.random().toString(36).substr(2, 9));
      const item = {
        id: id,
        name: defaultItem.name || '',
        label: defaultItem.label || '',
        category: defaultItem.category || 'general',
        enabled: defaultItem.enabled !== false,
        _source_id: defaultItem._source_id || ''
      };
      wrap.insertAdjacentHTML('beforeend', renderSearxngEngineCard(item));
      const added = document.getElementById(`card-${id}`);
      if (added && !item.name) {
        const nameInp = added.querySelector('.engine-name-input');
        if (nameInp) nameInp.focus();
      }
      if (typeof window.updateSearxngEnginesCount === 'function') {
        window.updateSearxngEnginesCount();
      }
      return id;
    }

    function buildTorEngineDefs(ep) {
      const ahmia = ep.dark_ahmia || {};
      const torch = ep.dark_torch || {};
      const haystak = ep.dark_haystak || {};
      const onionland = ep.dark_onionland || {};
      const excavator = ep.dark_excavator || {};
      const phobos = ep.dark_phobos || {};
      const tor66 = ep.dark_tor66 || {};
      const daniel = ep.dark_danieltore || {};
      return [
        { key: 'ahmia_onion', badge: 'TOR ONION', data: ahmia.onion || decomposeUrl(ahmia.onion_url || 'http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion', 'Ahmia (.onion)', 'http') },
        { key: 'ahmia_clear', badge: 'CLEARNET GATEWAY', data: ahmia.clearnet || decomposeUrl(ahmia.clearnet_url || 'https://ahmia.fi', 'Ahmia Clearnet Gateway', 'https') },
        { key: 'ddg_onion', badge: 'TOR ONION', data: torch.ddg || decomposeUrl(torch.ddg_onion || 'https://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion/html/', 'DuckDuckGo (.onion)', 'https') },
        { key: 'torch_onion', badge: 'TOR ONION', data: torch.torch || decomposeUrl(torch.torch_onion || 'http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion/cgi-bin/omega/omega', 'Torch (.onion)', 'http') },
        { key: 'haystak_onion', badge: 'TOR ONION', data: haystak.onion || decomposeUrl(haystak.onion_url || 'http://haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion', 'Haystak (.onion)', 'http') },
        { key: 'onionland_clear', badge: 'CLEARNET GATEWAY', data: onionland.clearnet || decomposeUrl(onionland.clearnet_url || 'https://onionsearchengine.com/search.php', 'Onion Search Engine', 'https') },
        { key: 'excavator_onion', badge: 'TOR ONION', data: excavator.onion || decomposeUrl(excavator.onion_url || 'http://2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion/search', 'Excavator (.onion)', 'http') },
        { key: 'phobos_onion', badge: 'TOR ONION', data: phobos.onion || decomposeUrl(phobos.onion_url || 'http://phobosxilamwcg75xt22id7aywkzol6q6rfl2flipcqoc4e4ahima5id.onion/search', 'Phobos (.onion)', 'http') },
        { key: 'tor66_onion', badge: 'TOR ONION', data: tor66.onion || decomposeUrl(tor66.onion_url || 'http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search', 'Tor66 (.onion)', 'http') },
        { key: 'daniel_onion', badge: 'TOR ONION', data: daniel.onion || decomposeUrl(daniel.onion_url || 'http://tordexu73joywapk2txdr54jed4imqledpcvcuf75qsas2gwdgksvnyd.onion/search', 'TorDex Directory (.onion)', 'http') }
      ];
    }

    function populateSearxngLocal(wrapElOrId, sx = {}) {
      const wrap = _resolveWrap(wrapElOrId);
      if (!wrap) return;
      const localInst = sx.local_instance || decomposeUrl(sx.local_url || 'http://127.0.0.1:8889', 'SearXNG Local Daemon', 'http');
      localInst.id = 'endp_sx_local';
      wrap.innerHTML = renderCard(localInst, {
        typeBadge: 'LOCAL DAEMON',
        isDeletable: false,
        key: 'searxng_local',
        category: 'searxng'
      });
    }

    function populateSearxngEngines(wrapElOrId, sx = {}) {
      const wrap = _resolveWrap(wrapElOrId);
      if (!wrap) return [];
      const sxEngines = Array.isArray(sx.engines) ? sx.engines : [];
      wrap.innerHTML = '';
      sxEngines.forEach(eng => addSearxngEngine(wrap.id, eng));
      if (typeof window.updateSearxngEnginesCount === 'function') {
        window.updateSearxngEnginesCount();
      }
      return sxEngines;
    }

    function populateFallbacks(wrapElOrId, fallbacks = [], customNodes = []) {
      const wrap = _resolveWrap(wrapElOrId);
      if (!wrap) return;
      wrap.innerHTML = '';
      (Array.isArray(fallbacks) ? fallbacks : []).forEach(f => {
        const item = (typeof f === 'string') ? decomposeUrl(f, '', 'https') : f;
        addEndpoint(wrap.id, item, {
          typeBadge: 'SEARXNG MIRROR',
          isDeletable: true,
          key: 'searxng_fallback',
          category: 'searxng'
        });
      });
      (Array.isArray(customNodes) ? customNodes : []).forEach(cn => {
        addEndpoint(wrap.id, cn, {
          typeBadge: 'CUSTOM NODE',
          isDeletable: true,
          key: 'custom_node',
          category: 'custom'
        });
      });
    }

    function populateTorEngines(wrapElOrId, ep = {}, clearFirst = true) {
      const wrap = _resolveWrap(wrapElOrId);
      if (!wrap) return;
      if (clearFirst) wrap.innerHTML = '';
      buildTorEngineDefs(ep).forEach(ted => {
        ted.data.id = 'endp_' + ted.key;
        wrap.insertAdjacentHTML('beforeend', renderCard(ted.data, {
          typeBadge: ted.badge,
          isDeletable: false,
          key: ted.key,
          category: 'tor'
        }));
      });
      const customTorEngines = Array.isArray(ep.custom_onion_engines) ? ep.custom_onion_engines : [];
      customTorEngines.forEach(cte => {
        addEndpoint(wrap.id, cte, {
          typeBadge: 'CUSTOM TOR',
          isDeletable: true,
          key: 'custom_tor',
          category: cte.category || 'onion',
          showCategory: true
        });
      });
    }

    const NODE_PRESETS = {
      searxng_fallback: {
        containerId: 'endp-searxng-fallbacks-wrap',
        defaults: { name: 'Custom Fallback Node', protocol: 'https', host: '', port: '', path: '', enabled: true },
        options: { typeBadge: 'SEARXNG MIRROR', isDeletable: true, key: 'searxng_fallback', category: 'searxng' }
      },
      custom_tor: {
        containerId: 'endp-tor-engines-wrap',
        defaults: { name: 'Custom Onion Engine', category: 'onion', protocol: 'http', host: '', port: '', path: '/search?q={q}', enabled: true },
        options: { typeBadge: 'CUSTOM TOR', isDeletable: true, key: 'custom_tor', category: 'onion', showCategory: true }
      },
      custom_node: {
        containerId: 'endp-custom-nodes-wrap',
        defaults: { name: 'Custom Search Node', protocol: 'https', host: '', port: '', path: '', enabled: true },
        options: { typeBadge: 'CUSTOM NODE', isDeletable: true, key: 'custom_node', category: 'custom' }
      },
      custom_clear: {
        containerId: 'endp-custom-clear-wrap',
        defaults: { name: 'Custom Web / OpenSearch', protocol: 'https', host: '', port: '', path: '/search?q={q}', search_template: '', enabled: true },
        options: { typeBadge: 'OPENSEARCH / WEB', isDeletable: true, key: 'custom_clear', showCategory: true, category: 'general' }
      },
      custom_archive: {
        containerId: 'endp-archives-wrap',
        defaults: { name: 'Custom Archive / Repository', protocol: 'https', host: '', port: '', path: '/api/search?q={q}', search_template: '', enabled: true },
        options: { typeBadge: 'CUSTOM ARCHIVE', isDeletable: true, key: 'custom_archive', showCategory: true, category: 'files' }
      }
    };

    function addPresetEndpoint(kind, overrideContainerId = null) {
      const spec = NODE_PRESETS[kind];
      if (!spec) return null;
      return addEndpoint(overrideContainerId || spec.containerId, { ...spec.defaults }, { ...spec.options });
    }

    Object.assign(SE, {
      renderSearxngEngineCard,
      syncEngineCard,
      collectSearxngEngineCard,
      addSearxngEngine,
      buildTorEngineDefs,
      populateSearxngLocal,
      populateSearxngEngines,
      populateFallbacks,
      populateTorEngines,
      addPresetEndpoint,
    });
    return SE;
  }

  return { attach };
})();

if (window.SearchEndpoints) {
  window.SearchEndpointsAdapters.attach(window.SearchEndpoints);
}
