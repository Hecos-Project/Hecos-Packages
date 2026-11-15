/**
 * Central Hub Node & Preset Insertion Actions
 * Extracted from netsearch_panel.js for modularity.
 */
(function () {
  function _notify(msg, type = 'info') {
    if (typeof window._nsNotify === 'function') {
      window._nsNotify(msg, type);
    } else if (typeof window.showToast === 'function') {
      window.showToast(msg, type);
    } else {
      console.log(`[NetSearch] [${type}] ${msg}`);
    }
  }

  function _withEndpoints(cb) {
    if (typeof window._nsEnsureSearchEndpoints === 'function') {
      window._nsEnsureSearchEndpoints(cb);
    } else if (window.SearchEndpoints) {
      cb(window.SearchEndpoints);
    }
  }

  function _appendStreamNode(itemCfg) {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('streams');
    window.toggleEndpointSection && window.toggleEndpointSection(null, 'endp-streams-nodes-body', true);
    _withEndpoints((SE) => {
      SE.addEndpoint('endp-streams-nodes-wrap', {
        name: itemCfg.name || 'Custom Live Stream',
        protocol: itemCfg.protocol || 'https',
        host: itemCfg.host || '',
        port: itemCfg.port || '',
        path: itemCfg.path || '',
        category: itemCfg.category || 'tv',
        enabled: true
      }, {
        typeBadge: 'STREAM NODE',
        isDeletable: true,
        key: 'custom_stream',
        showCategory: true,
        categoryMode: 'streams',
        category: itemCfg.category || 'tv'
      });
      window.updateStreamsTabBadgeCount && window.updateStreamsTabBadgeCount();
      if (window.SearchSources && typeof window.SearchSources.renderStreamStats === 'function') {
        window.SearchSources.renderStreamStats();
      }
    });
  }

  window.addSearxngFallbackNode = function () {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('searxng');
    window.toggleEndpointSection(null, 'endp-searxng-fallbacks-body', true);
    _withEndpoints((SE) => SE.addPresetEndpoint('searxng_fallback'));
  };

  window.addCustomTorEngineNode = function () {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('dark');
    window.toggleEndpointSection(null, 'endp-tor-engines-body', true);
    _withEndpoints((SE) => SE.addPresetEndpoint('custom_tor'));
  };

  window.addCustomSearchNode = function () {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('searxng');
    window.toggleEndpointSection(null, 'endp-searxng-fallbacks-body', true);
    _withEndpoints((SE) => SE.addPresetEndpoint('custom_node', 'endp-searxng-fallbacks-wrap'));
  };

  window.addCustomClearEngineNode = function () {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('web');
    window.toggleEndpointSection(null, 'endp-custom-clear-body', true);
    _withEndpoints((SE) => SE.addPresetEndpoint('custom_clear'));
  };

  window.addCustomArchiveNode = function () {
    window.switchNetSearchEndpointTab && window.switchNetSearchEndpointTab('web');
    window.toggleEndpointSection(null, 'endp-archives-body', true);
    _withEndpoints((SE) => SE.addPresetEndpoint('custom_archive'));
  };

  window.addCustomStreamNode = function () {
    _appendStreamNode({
      name: 'Custom Live Stream',
      protocol: 'https',
      host: '',
      port: '',
      path: '/live/master.m3u8',
      category: 'tv'
    });
  };

  window.quickAddStreamPresetNode = function (name, protocol, host, port, path, category) {
    _appendStreamNode({
      name: name || 'Live Stream Node',
      protocol: protocol || 'https',
      host: host || '',
      port: port || '',
      path: path || '',
      category: category || 'tv'
    });
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
    _withEndpoints((SE) => {
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
    const existing = document.querySelector(`#endp-searxng-engines-wrap .searxng-engine-card input.engine-name-input[value="${name}"]`);
    if (existing) {
      const card = existing.closest('.searxng-engine-card');
      const cb = card.querySelector('.engine-enabled-checkbox');
      if (cb && !cb.checked) {
        cb.checked = true;
        _withEndpoints(SE => SE.syncEngineCard(card.dataset.id));
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
})();
