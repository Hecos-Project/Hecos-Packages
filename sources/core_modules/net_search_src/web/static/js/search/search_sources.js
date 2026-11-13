/**
 * search_sources.js
 * Modular UI controller for Automated & Manual Search Engine Source Lists / Compilations.
 * Manages remote feeds (GitHub, OpenSearch XML, .onion, JSON/CSV/YAML/SQLite),
 * local file uploads, dry-run duplicate previews, auto-update scheduling, and source removal.
 */
window.SearchSources = (function () {
  let _sources = [];
  let _presets = [];
  let _domainSummary = { total_domains: 0, by_role: {} };
  let _editingSourceId = '';
  let _activeTab = 'searxng';

  const TAB_META = {
    searxng: {
      pools: ['searxng_fallbacks', 'custom_nodes', 'searxng_engines'],
      defaultPool: 'searxng_fallbacks',
      defaultFormat: 'auto',
      hint: 'SearXNG Mirrors & Nodes',
      addTitle: 'Add / Import SearXNG Node List',
      emptyMsg: 'No automated SearXNG source lists configured. Use a preset above or click "+ Add / Import SearXNG List".'
    },
    web: {
      pools: ['custom_clear_engines'],
      defaultPool: 'custom_clear_engines',
      defaultFormat: 'auto',
      hint: 'Custom Web / OpenSearch Engines',
      addTitle: 'Add / Import Web / OpenSearch List',
      emptyMsg: 'No Web / OpenSearch source lists configured. Click "+ Add / Import Web List" to add one.'
    },
    dark: {
      pools: ['custom_onion_engines'],
      defaultPool: 'custom_onion_engines',
      defaultFormat: 'onion_list',
      hint: 'Tor .onion Search Engines',
      addTitle: 'Add / Import .onion Engine List',
      emptyMsg: 'No .onion source lists configured. Use a preset above or click "+ Add / Import .onion List".'
    },
    files: {
      pools: ['custom_clear_engines', 'custom_onion_engines'],
      defaultPool: 'custom_clear_engines',
      defaultFormat: 'auto',
      hint: 'File Hunter Sources & Custom File Repos',
      addTitle: 'Add / Import Custom File Repository',
      emptyMsg: 'Add custom Clearnet or .onion file repositories from the Web and Dark Web tabs.'
    },
    domains: {
      pools: ['domain_directory', 'domain_blocklist', 'domain_allowlist'],
      defaultPool: 'domain_directory',
      defaultFormat: 'domain_list',
      hint: 'SQLite Domain Index (Directory / Blocklist / Allowlist)',
      addTitle: 'Add / Import Domain Compilation List',
      emptyMsg: 'No domain compilation lists loaded yet. Click "+ Add / Import Domain List".'
    }
  };

  function _tabForItem(item) {
    if (!item) return 'web';
    const pool = String(item.target_pool || 'auto');
    for (const [tab, meta] of Object.entries(TAB_META)) {
      if (meta.pools.includes(pool)) return tab;
    }
    const fmt = String(item.format || 'auto').toLowerCase();
    const loc = String(item.location || '').toLowerCase();
    if (fmt === 'domain_list') return 'domains';
    if (fmt === 'onion_list' || item.use_tor || loc.includes('.onion') || loc.includes('onion')) return 'dark';
    if (fmt === 'yaml' || loc.includes('searx')) return 'searxng';
    return 'web';
  }

  function _esc(str) {
    if (!str && str !== 0) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function _notify(msg, type = 'info') {
    if (typeof window.showToast === 'function') {
      window.showToast(msg, type);
    } else {
      console.log(`[NetSearch:Sources] [${type}] ${msg}`);
    }
  }

  function _formatTs(ts) {
    if (!ts) return 'Never';
    try {
      return new Date(ts * 1000).toLocaleString();
    } catch (_) {
      return String(ts);
    }
  }

  function _statusBadge(src) {
    const st = src.last_status || 'never';
    if (st === 'ok') return '<span class="badge-pill badge-ok" style="font-size:10px;">OK</span>';
    if (st === 'unchanged') return '<span class="badge-pill badge-neutral" style="font-size:10px;">Up-to-date</span>';
    if (st === 'skipped_tor_offline') return '<span class="badge-pill" style="font-size:10px; background:rgba(245,158,11,0.18); color:#fbbf24;">Tor Offline</span>';
    if (st === 'error') return '<span class="badge-pill" style="font-size:10px; background:rgba(239,68,68,0.18); color:#f87171;">Error</span>';
    return '<span class="badge-pill badge-neutral" style="font-size:10px;">Pending</span>';
  }

  function _renderDomainRoleSwitch(src) {
    const curPool = String(src.target_pool || 'domain_blocklist');
    const curRole = curPool.startsWith('domain_') ? curPool.replace('domain_', '') : 'blocklist';
    const roles = [
      {
        id: 'directory',
        label: 'Directory',
        title: 'Searchable Directory (Reverse Mode): Actively searches domains in this list via token matching, site: dorks, and HTTP probes when SafeSearch is OFF. Best choice for unfiltered search even on parental-control blocklists.'
      },
      {
        id: 'blocklist',
        label: 'Blocklist',
        title: 'SafeSearch Exclusion Filter: Hides search results matching these domains when SafeSearch is ON. Does NOT search them.'
      },
      {
        id: 'allowlist',
        label: 'Allowlist',
        title: 'SafeSearch Bypass Exceptions: Always keeps results from these domains visible even when SafeSearch + Blocklist would filter them out.'
      }
    ];
    return `
      <div class="ns-role-btn-group" title="Switch how SQLite uses this domain list in 1 click (without re-downloading)">
        ${roles.map(r => `
          <button type="button" class="ns-role-btn ${curRole === r.id ? 'active' : ''}"
            title="${_esc(r.title)}"
            onclick="window.SearchSources.setDomainRole('${_esc(src.id)}', '${r.id}')">
            ${_esc(r.label)}
          </button>
        `).join('')}
      </div>
    `;
  }

  function renderDomainStats() {
    const byRole = (_domainSummary && _domainSummary.by_role) ? _domainSummary.by_role : {};
    const fmtNum = (v) => Number(v || 0).toLocaleString();
    const dEl = document.getElementById('domain-cnt-directory');
    const bEl = document.getElementById('domain-cnt-blocklist');
    const aEl = document.getElementById('domain-cnt-allowlist');
    if (dEl) dEl.textContent = fmtNum(byRole.directory);
    if (bEl) bEl.textContent = fmtNum(byRole.blocklist);
    if (aEl) aEl.textContent = fmtNum(byRole.allowlist);
  }

  async function load() {
    try {
      const res = await fetch('/api/hsearch/sources').then(r => r.json());
      if (!res || !res.ok) return;
      _sources = Array.isArray(res.sources) ? res.sources : [];
      _presets = Array.isArray(res.presets) ? res.presets : [];
      _domainSummary = res.domain_summary || { total_domains: 0, by_role: {} };

      const autoSw = document.getElementById('sources-auto-update-master');
      if (autoSw) autoSw.checked = res.auto_update_enabled !== false;

      const countBadge = document.getElementById('badge-sources-count');
      if (countBadge) countBadge.textContent = `${_sources.length} Lists`;

      renderDomainStats();
      renderPresets();
      renderList();
    } catch (e) {
      const wrap = document.getElementById(`endp-sources-list-${_activeTab}`);
      if (wrap) wrap.innerHTML = `<div style="font-size:11px; color:#f87171;">Failed to load sources: ${_esc(e.message)}</div>`;
    }
  }

  function renderPresets() {
    Object.keys(TAB_META).forEach(tab => {
      const bar = document.getElementById(`endp-sources-presets-${tab}`);
      if (!bar) return;
      const items = _presets.filter(p => _tabForItem(p) === tab);
      if (!items.length) {
        bar.style.display = 'none';
        bar.innerHTML = '';
        return;
      }
      bar.style.display = 'flex';
      bar.innerHTML = '<span style="font-size:10px; color:var(--muted); text-transform:uppercase; font-weight:700; margin-right:4px;">Presets:</span>' +
        items.map(p => `
          <button type="button" class="btn btn-sm btn-secondary" style="font-size:10px; padding:2px 8px;"
            title="${_esc(p.description || p.location)}"
            onclick="window.SearchSources.quickAddPreset('${_esc(p.preset_id)}')">
            + ${_esc(p.name)}
          </button>
        `).join('');
    });
  }

  function _renderSourceCard(src, tab) {
    const stats = src.stats || {};
    const enabled = src.enabled !== false;
    const autoLabel = src.auto_update ? `Auto (${src.interval_hours || 12}h)` : 'Manual only';
    const fmtBadge = String(src.format || 'auto').toUpperCase();
    const torBadge = src.use_tor ? '<span class="badge-pill" style="font-size:10px; background:rgba(168,85,247,0.18); color:#c084fc;" title="Fetched over Tor SOCKS5h">TOR</span>' : '';
    const roleSwitchHtml = (tab === 'domains')
      ? _renderDomainRoleSwitch(src)
      : `<span class="badge-pill badge-neutral" style="font-size:10px;" title="Target endpoint pool">${_esc(src.target_pool || 'auto')}</span>`;
    const errHtml = src.last_error ? `<div style="font-size:10px; color:#f87171; margin-top:4px;"><i class="fas fa-exclamation-triangle"></i> ${_esc(src.last_error)}</div>` : '';

    const bySource = (_domainSummary && _domainSummary.by_source) ? _domainSummary.by_source[src.id] : null;
    const indexedCount = bySource ? Number(bySource.count || 0) : 0;
    const addedLastSync = Number(stats.added || 0);
    const skippedLastSync = Number(stats.skipped_duplicates || 0);
    const parsedCount = Number(stats.parsed || 0);
    const countMetricHtml = (tab === 'domains' && indexedCount > 0)
      ? `<span style="color:var(--accent-emerald, #10b981); font-weight:700;" title="Total domains currently active in SQLite for this list">${indexedCount.toLocaleString()} indexed in SQLite</span>
         <span title="New domains inserted on the last sync run (0 means list was already indexed without new upstream additions)">(+${addedLastSync.toLocaleString()} new on last sync)</span>`
      : `<span style="color:var(--accent-emerald, #10b981);" title="New entries added during the last sync">+${addedLastSync.toLocaleString()} added</span>
         <span title="Entries already present and skipped to prevent duplicates">${skippedLastSync.toLocaleString()} already present</span>`;

    return `
      <div class="endpoint-card" style="margin-bottom:8px; opacity:${enabled ? '1' : '0.68'}; border-left:3px solid ${enabled ? 'var(--accent-emerald, #10b981)' : 'var(--border)'};">
        <div class="endpoint-card-header" style="margin-bottom:6px;">
          <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
            <strong style="font-size:12px; color:var(--text);">${_esc(src.name || src.id)}</strong>
            <span class="badge-pill badge-neutral" style="font-size:10px;" title="Detected compilation format">${_esc(fmtBadge)}</span>
            ${roleSwitchHtml}
            ${torBadge}
            ${_statusBadge(src)}
          </div>
          <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
            <label class="endpoint-toggle-label" style="cursor:pointer; margin-right:4px;" title="Enable or disable this source and its imported entries without deleting">
              <input type="checkbox" ${enabled ? 'checked' : ''} onchange="window.SearchSources.toggle('${_esc(src.id)}', this.checked)">
              <span style="font-size:11px;">${enabled ? 'Active' : 'Disabled'}</span>
            </label>
            <button type="button" class="btn btn-sm btn-secondary" style="font-size:10px; padding:3px 8px;" onclick="window.SearchSources.syncOne('${_esc(src.id)}')" title="Re-fetch upstream source and merge any newly added entries">
              <i class="fas fa-sync-alt"></i> Sync
            </button>
            <button type="button" class="btn btn-sm btn-secondary" style="font-size:10px; padding:3px 8px;" onclick="window.SearchSources.edit('${_esc(src.id)}')" title="Edit source name, URL, format, role, or sync interval">
              <i class="fas fa-pen"></i>
            </button>
            <button type="button" class="btn-icon-del" onclick="window.SearchSources.remove('${_esc(src.id)}')" title="Delete this source AND purge all entries imported from it">
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </div>
        <div style="font-size:11px; font-family:monospace; color:var(--muted); word-break:break-all; margin-bottom:5px;" title="Source location">
          ${_esc(src.location || '')}
        </div>
        <div style="display:flex; gap:12px; flex-wrap:wrap; font-size:10px; color:var(--muted);">
          <span title="Background refresh schedule"><i class="fas fa-clock"></i> ${_esc(autoLabel)}</span>
          <span title="Timestamp of the last sync check">Last sync: ${_esc(_formatTs(src.last_sync))}</span>
          ${countMetricHtml}
          <span title="Total valid lines/entries parsed from the upstream file">(${parsedCount.toLocaleString()} parsed)</span>
        </div>
        ${errHtml}
      </div>
    `;
  }

  function renderList() {
    Object.entries(TAB_META).forEach(([tab, meta]) => {
      const wrap = document.getElementById(`endp-sources-list-${tab}`);
      const items = _sources.filter(src => _tabForItem(src) === tab);
      const badge = document.getElementById(`badge-sources-${tab}-count`);
      if (badge) badge.textContent = `${items.length} Lists`;

      if (tab === 'domains') {
        const domTabBadge = document.getElementById('badge-tab-domains-count');
        if (domTabBadge) domTabBadge.textContent = String(items.length);
      }

      if (!wrap) return;
      if (!items.length) {
        wrap.innerHTML = `<div style="padding:10px; border:1px dashed var(--border); border-radius:8px; font-size:11px; color:var(--muted); text-align:center;">${_esc(meta.emptyMsg)}</div>`;
        return;
      }
      wrap.innerHTML = items.map(src => _renderSourceCard(src, tab)).join('');
    });
  }

  function _configureEditorForTab(tabName, overridePool) {
    const meta = TAB_META[tabName] || TAB_META.searxng;
    _activeTab = tabName;
    const pool = overridePool || meta.defaultPool;

    const hintEl = document.getElementById('src-editor-pool-hint');
    if (hintEl) hintEl.textContent = `Destination: ${meta.hint}`;

    const poolWrap = document.getElementById('src-form-pool-wrap');
    const importPoolWrap = document.getElementById('src-import-pool-wrap');
    const isDomains = (tabName === 'domains');
    if (poolWrap) poolWrap.style.display = isDomains ? '' : 'none';
    if (importPoolWrap) importPoolWrap.style.display = isDomains ? '' : 'none';

    const poolSel = document.getElementById('src-form-pool');
    const importPoolSel = document.getElementById('src-import-pool');
    if (poolSel) poolSel.value = pool;
    if (importPoolSel) importPoolSel.value = pool;
  }

  function setActiveTab(tabName) {
    if (!TAB_META[tabName]) return;
    const prevTab = _activeTab;
    _activeTab = tabName;
    const panel = document.getElementById('src-editor-panel');
    if (panel && panel.style.display !== 'none' && !_editingSourceId && prevTab !== tabName) {
      panel.style.display = 'none';
    }
  }

  function openAddFormForTab(tabName, defaultPool) {
    const targetTab = TAB_META[tabName] ? tabName : _activeTab;
    if (typeof window.switchNetSearchEndpointTab === 'function' && _activeTab !== targetTab) {
      window.switchNetSearchEndpointTab(targetTab);
    }
    clearForm();
    const meta = TAB_META[targetTab] || TAB_META.searxng;
    _configureEditorForTab(targetTab, defaultPool || meta.defaultPool);

    const fmtSel = document.getElementById('src-form-format');
    const importFmtSel = document.getElementById('src-import-format');
    if (fmtSel) fmtSel.value = meta.defaultFormat || 'auto';
    if (importFmtSel) importFmtSel.value = meta.defaultFormat || 'auto';

    const titleEl = document.getElementById('src-editor-title');
    if (titleEl) {
      titleEl.innerHTML = `<i class="fas fa-plus-circle" style="color:var(--accent-emerald, #10b981); margin-right:5px;"></i> ${_esc(meta.addTitle)}`;
    }
    const panel = document.getElementById('src-editor-panel');
    if (panel) {
      panel.style.display = 'block';
      panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    document.getElementById('src-form-name')?.focus();
  }

  function closeEditor() {
    clearForm();
    const panel = document.getElementById('src-editor-panel');
    if (panel) panel.style.display = 'none';
    const box = document.getElementById('src-preview-box');
    if (box) box.style.display = 'none';
  }

  async function setDomainRole(sourceId, newRole) {
    try {
      const res = await fetch('/api/hsearch/domains/role', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_id: sourceId, role: newRole })
      }).then(r => r.json());
      if (res && res.ok) {
        _domainSummary = res.domain_summary || _domainSummary;
        _notify(`Role updated to "${newRole}" (${Number(res.count || 0).toLocaleString()} domains).`, 'success');
        await load();
        if (typeof window.reloadNetSearchEndpoints === 'function') window.reloadNetSearchEndpoints();
      } else {
        _notify('Failed to switch domain role: ' + (res?.error || 'Unknown error'), 'error');
      }
    } catch (e) {
      _notify('Role switch error: ' + e.message, 'error');
    }
  }

  async function quickAddPreset(presetId) {
    const preset = _presets.find(p => p.preset_id === presetId);
    if (!preset) return;
    _notify(`Adding & syncing "${preset.name}"...`, 'info');
    try {
      const res = await fetch('/api/hsearch/sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...preset, sync_now: true, force: true })
      }).then(r => r.json());
      if (res.ok) {
        const st = res.sync?.stats || {};
        _notify(`"${preset.name}" synced: +${st.added || 0} added, ${st.skipped_duplicates || 0} duplicates skipped.`, 'success');
        await load();
        if (typeof window.reloadNetSearchEndpoints === 'function') window.reloadNetSearchEndpoints();
      } else {
        _notify('Failed to add preset: ' + (res.error || 'Unknown error'), 'error');
      }
    } catch (e) {
      _notify('Preset error: ' + e.message, 'error');
    }
  }

  function _readForm() {
    const meta = TAB_META[_activeTab] || TAB_META.searxng;
    return {
      id: _editingSourceId || undefined,
      name: (document.getElementById('src-form-name')?.value || '').trim(),
      location: (document.getElementById('src-form-location')?.value || '').trim(),
      format: document.getElementById('src-form-format')?.value || meta.defaultFormat || 'auto',
      target_pool: document.getElementById('src-form-pool')?.value || meta.defaultPool || 'auto',
      interval_hours: parseInt(document.getElementById('src-form-interval')?.value || '12', 10) || 12,
      auto_update: document.getElementById('src-form-autoupdate')?.checked !== false,
      use_tor: document.getElementById('src-form-usetor')?.checked === true,
      enabled: true,
    };
  }

  function clearForm() {
    _editingSourceId = '';
    ['src-form-name', 'src-form-location'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    const meta = TAB_META[_activeTab] || TAB_META.searxng;
    const fmt = document.getElementById('src-form-format');
    if (fmt) fmt.value = meta.defaultFormat || 'auto';
    const pool = document.getElementById('src-form-pool');
    if (pool) pool.value = meta.defaultPool || 'auto';
    const iv = document.getElementById('src-form-interval');
    if (iv) iv.value = '12';
    const au = document.getElementById('src-form-autoupdate');
    if (au) au.checked = true;
    const ut = document.getElementById('src-form-usetor');
    if (ut) ut.checked = (_activeTab === 'dark');
    const cancelBtn = document.getElementById('src-form-cancel-btn');
    if (cancelBtn) cancelBtn.style.display = 'none';
    const saveBtnLabel = document.getElementById('src-form-save-label');
    if (saveBtnLabel) saveBtnLabel.textContent = 'Add & Sync Source';
  }

  function edit(sourceId) {
    const src = _sources.find(s => s.id === sourceId);
    if (!src) return;
    const tab = _tabForItem(src);
    _editingSourceId = src.id;
    if (typeof window.switchNetSearchEndpointTab === 'function') {
      window.switchNetSearchEndpointTab(tab);
    }
    _configureEditorForTab(tab, src.target_pool || TAB_META[tab].defaultPool);

    document.getElementById('src-form-name').value = src.name || '';
    document.getElementById('src-form-location').value = src.location || '';
    document.getElementById('src-form-format').value = src.format || 'auto';
    document.getElementById('src-form-pool').value = src.target_pool || 'auto';
    document.getElementById('src-form-interval').value = String(src.interval_hours || 12);
    document.getElementById('src-form-autoupdate').checked = src.auto_update !== false;
    document.getElementById('src-form-usetor').checked = src.use_tor === true;

    const titleEl = document.getElementById('src-editor-title');
    if (titleEl) {
      titleEl.innerHTML = `<i class="fas fa-pen" style="color:var(--accent-cyan, #06b6d4); margin-right:5px;"></i> Edit Source: ${_esc(src.name || src.id)}`;
    }
    const cancelBtn = document.getElementById('src-form-cancel-btn');
    if (cancelBtn) cancelBtn.style.display = 'inline-flex';
    const saveBtnLabel = document.getElementById('src-form-save-label');
    if (saveBtnLabel) saveBtnLabel.textContent = 'Update & Sync Source';

    const panel = document.getElementById('src-editor-panel');
    if (panel) {
      panel.style.display = 'block';
      panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    document.getElementById('src-form-location')?.focus();
  }

  function _showPreview(res) {
    const box = document.getElementById('src-preview-box');
    if (!box) return;
    if (!res || !res.ok) {
      box.style.display = 'block';
      box.innerHTML = `<span style="color:#f87171;"><i class="fas fa-exclamation-circle"></i> Preview error: ${_esc(res?.error || 'Unknown')}</span>`;
      return;
    }
    const st = res.stats || {};
    const sample = Array.isArray(st.preview) ? st.preview.slice(0, 8) : [];
    const sampleHtml = sample.map(it =>
      `<div style="font-family:monospace; font-size:10px; color:var(--text);">[${_esc(it.pool)}] ${_esc(it.name)} -> ${_esc(it.url)}</div>`
    ).join('');
    box.style.display = 'block';
    box.innerHTML = `
      <div style="font-size:11px; margin-bottom:4px;">
        <strong>Format:</strong> ${_esc((res.detected_format || 'auto').toUpperCase())} &nbsp;|&nbsp;
        <strong>Parsed:</strong> ${st.parsed || 0} &nbsp;|&nbsp;
        <strong style="color:#34d399;">New unique: +${st.added || 0}</strong> &nbsp;|&nbsp;
        <strong style="color:#fbbf24;">Duplicates skipped: ${st.skipped_duplicates || 0}</strong>
      </div>
      ${sampleHtml}
    `;
  }

  async function previewUrl() {
    const data = _readForm();
    if (!data.location) {
      _notify('Enter a URL, GitHub raw link, OpenSearch URL, or local file path first.', 'warning');
      return;
    }
    const box = document.getElementById('src-preview-box');
    if (box) {
      box.style.display = 'block';
      box.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Fetching and checking duplicates...';
    }
    try {
      const res = await fetch('/api/hsearch/sources/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      }).then(r => r.json());
      _showPreview(res);
    } catch (e) {
      _showPreview({ ok: false, error: e.message });
    }
  }

  async function saveFromForm() {
    const data = _readForm();
    if (!data.location) {
      _notify('Enter a URL or local file path for the source.', 'warning');
      return;
    }
    _notify('Saving and syncing source...', 'info');
    try {
      const res = await fetch('/api/hsearch/sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...data, sync_now: true, force: true })
      }).then(r => r.json());
      if (res.ok) {
        const sync = res.sync || {};
        if (sync.ok === false) {
          _notify(`Source saved, sync warning: ${sync.error || sync.status}`, 'warning');
        } else {
          const st = sync.stats || {};
          _notify(`Source synced: +${st.added || 0} new, ${st.skipped_duplicates || 0} duplicates skipped.`, 'success');
        }
        closeEditor();
        await load();
        if (typeof window.reloadNetSearchEndpoints === 'function') window.reloadNetSearchEndpoints();
      } else {
        _notify('Error saving source: ' + (res.error || 'Unknown'), 'error');
      }
    } catch (e) {
      _notify('Save error: ' + e.message, 'error');
    }
  }

  async function syncOne(sourceId) {
    _notify('Syncing source...', 'info');
    try {
      const res = await fetch(`/api/hsearch/sources/${encodeURIComponent(sourceId)}/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: true })
      }).then(r => r.json());
      if (res.ok) {
        const st = res.stats || {};
        _notify(`Sync complete (${res.status}): +${st.added || 0} added, ${st.skipped_duplicates || 0} duplicates skipped.`, 'success');
      } else {
        _notify(`Sync failed: ${res.error || res.status || 'Unknown error'}`, 'error');
      }
      await load();
      if (typeof window.reloadNetSearchEndpoints === 'function') window.reloadNetSearchEndpoints();
    } catch (e) {
      _notify('Sync error: ' + e.message, 'error');
    }
  }

  async function syncAll() {
    _notify('Syncing all enabled compilation sources...', 'info');
    try {
      const res = await fetch('/api/hsearch/sources/sync_all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: false })
      }).then(r => r.json());
      if (res.ok) {
        _notify(`Synced ${res.synced_count || 0} sources: +${res.total_added || 0} added, ${res.total_skipped_duplicates || 0} duplicates skipped.`, 'success');
      } else {
        _notify('Sync all failed: ' + (res.error || 'Unknown'), 'error');
      }
      await load();
      if (typeof window.reloadNetSearchEndpoints === 'function') window.reloadNetSearchEndpoints();
    } catch (e) {
      _notify('Sync all error: ' + e.message, 'error');
    }
  }

  async function toggle(sourceId, enabled) {
    try {
      const res = await fetch(`/api/hsearch/sources/${encodeURIComponent(sourceId)}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !!enabled })
      }).then(r => r.json());
      if (res.ok) {
        _notify(`Source ${enabled ? 'enabled' : 'disabled'} (${res.affected_endpoints || 0} endpoints updated).`, 'success');
        await load();
        if (typeof window.reloadNetSearchEndpoints === 'function') window.reloadNetSearchEndpoints();
      } else {
        _notify('Toggle failed: ' + (res.error || 'Unknown'), 'error');
      }
    } catch (e) {
      _notify('Toggle error: ' + e.message, 'error');
    }
  }

  async function remove(sourceId) {
    if (!confirm('Remove this source AND delete all entries/endpoints imported from it?')) return;
    try {
      const res = await fetch(`/api/hsearch/sources/${encodeURIComponent(sourceId)}`, { method: 'DELETE' }).then(r => r.json());
      if (res.ok) {
        _notify(`Source removed (${res.removed_endpoints || 0} imported entries deleted).`, 'success');
        if (_editingSourceId === sourceId) closeEditor();
        await load();
        if (typeof window.reloadNetSearchEndpoints === 'function') window.reloadNetSearchEndpoints();
      } else {
        _notify('Remove failed: ' + (res.error || 'Unknown'), 'error');
      }
    } catch (e) {
      _notify('Remove error: ' + e.message, 'error');
    }
  }

  async function setGlobalAutoUpdate(enabled) {
    try {
      const res = await fetch('/api/hsearch/sources/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_update_enabled: !!enabled })
      }).then(r => r.json());
      if (res.ok) {
        _notify(`Automatic background source updates ${enabled ? 'enabled' : 'paused'}.`, 'success');
      }
    } catch (e) {
      _notify('Settings update failed: ' + e.message, 'error');
    }
  }

  function updateImportFileLabel() {
    const fileInput = document.getElementById('src-import-file');
    const lbl = document.getElementById('src-import-file-label');
    if (!lbl) return;
    const f = fileInput?.files?.[0];
    lbl.textContent = f ? f.name : 'No file selected';
    lbl.style.color = f ? 'var(--text)' : 'var(--muted)';
  }

  async function importRawOrFile(dryRun = false) {
    const fileInput = document.getElementById('src-import-file');
    const textInput = document.getElementById('src-import-text');
    const fmt = document.getElementById('src-import-format')?.value || 'auto';
    const meta = TAB_META[_activeTab] || TAB_META.searxng;
    const pool = document.getElementById('src-import-pool')?.value || meta.defaultPool || 'auto';
    const file = fileInput?.files?.[0];
    const text = (textInput?.value || '').trim();

    if (!file && !text) {
      _notify('Select a file (.json, .csv, .yaml, .sqlite, .xml, .txt) or paste list content first.', 'warning');
      return;
    }

    const endpoint = dryRun ? '/api/hsearch/sources/preview' : '/api/hsearch/sources/import';
    try {
      let res;
      if (file) {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('format', fmt);
        fd.append('target_pool', pool);
        fd.append('name', file.name);
        if (dryRun) fd.append('dry_run', 'true');
        res = await fetch(endpoint, { method: 'POST', body: fd }).then(r => r.json());
      } else {
        res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: text, format: fmt, target_pool: pool, dry_run: !!dryRun })
        }).then(r => r.json());
      }

      if (dryRun) {
        _showPreview(res);
      } else if (res.ok) {
        const st = res.stats || {};
        _notify(`Imported (${(res.detected_format || 'auto').toUpperCase()}): +${st.added || 0} new, ${st.skipped_duplicates || 0} duplicates skipped.`, 'success');
        if (fileInput) { fileInput.value = ''; updateImportFileLabel(); }
        if (textInput) textInput.value = '';
        closeEditor();
        await load();
        if (typeof window.reloadNetSearchEndpoints === 'function') window.reloadNetSearchEndpoints();
      } else {
        _notify('Import failed: ' + (res.error || 'Unknown'), 'error');
      }
    } catch (e) {
      _notify('Import error: ' + e.message, 'error');
    }
  }

  return {
    load,
    setActiveTab,
    openAddFormForTab,
    closeEditor,
    setDomainRole,
    quickAddPreset,
    previewUrl,
    saveFromForm,
    clearForm,
    edit,
    syncOne,
    syncAll,
    toggle,
    remove,
    setGlobalAutoUpdate,
    updateImportFileLabel,
    importRawOrFile,
  };
})();

