/**
 * Central Hub SQLite Domain & Stream Role Controls
 * Shared rendering helpers for SearchSources (Domains SQLite & Live Streams SQLite tabs).
 */
window.SearchSourcesSqliteUI = (function () {
  function renderDomainRoleSwitch(src, esc) {
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
            title="${esc(r.title)}"
            onclick="window.SearchSources.setDomainRole('${esc(src.id)}', '${r.id}')">
            ${esc(r.label)}
          </button>
        `).join('')}
      </div>
    `;
  }

  function renderDomainStats(domainSummary) {
    const byRole = (domainSummary && domainSummary.by_role) ? domainSummary.by_role : {};
    const fmtNum = (v) => Number(v || 0).toLocaleString();
    const dEl = document.getElementById('domain-cnt-directory');
    const bEl = document.getElementById('domain-cnt-blocklist');
    const aEl = document.getElementById('domain-cnt-allowlist');
    if (dEl) dEl.textContent = fmtNum(byRole.directory);
    if (bEl) bEl.textContent = fmtNum(byRole.blocklist);
    if (aEl) aEl.textContent = fmtNum(byRole.allowlist);
  }

  function renderStreamRoleSwitch(src, esc) {
    const curPool = String(src.target_pool || 'stream_tv');
    const curRole = curPool.startsWith('stream_') ? curPool.replace('stream_', '') : 'tv';
    const roles = [
      { id: 'tv', label: 'TV / IPTV', title: 'Index streams in this list under TV / IPTV channels in SQLite' },
      { id: 'radio', label: 'Radio', title: 'Index streams in this list under Radio & Icecast stations in SQLite' },
      { id: 'webcam', label: 'Webcams', title: 'Index streams in this list under Public Live Webcams in SQLite' },
      { id: 'raw', label: 'Raw', title: 'Index streams in this list under Raw RTSP / M3U8 feeds in SQLite' }
    ];
    return `
      <div class="ns-role-btn-group" title="Switch the Live Stream category for this SQLite compilation in 1 click">
        ${roles.map(r => `
          <button type="button" class="ns-role-btn ${curRole === r.id ? 'active' : ''}"
            title="${esc(r.title)}"
            onclick="window.SearchSources.setStreamRole('${esc(src.id)}', '${r.id}')">
            ${esc(r.label)}
          </button>
        `).join('')}
      </div>
    `;
  }

  function renderStreamStats(streamSummary) {
    const byRole = (streamSummary && streamSummary.by_role) ? streamSummary.by_role : {};
    const fmtNum = (v) => Number(v || 0).toLocaleString();
    const tvEl = document.getElementById('stream-cnt-tv');
    const radEl = document.getElementById('stream-cnt-radio');
    const camEl = document.getElementById('stream-cnt-webcam');
    const rawEl = document.getElementById('stream-cnt-raw');
    const manualNodes = document.querySelectorAll('#endp-streams-nodes-wrap .endpoint-card').length;
    if (tvEl) tvEl.textContent = fmtNum(byRole.tv);
    if (radEl) radEl.textContent = fmtNum(byRole.radio);
    if (camEl) camEl.textContent = fmtNum(byRole.webcam);
    if (rawEl) rawEl.textContent = fmtNum(Number(byRole.raw || 0) + manualNodes);
  }

  return {
    renderDomainRoleSwitch,
    renderDomainStats,
    renderStreamRoleSwitch,
    renderStreamStats,
  };
})();
