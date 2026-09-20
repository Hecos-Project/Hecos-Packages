/**
 * Hecos Template Manager — Core API
 * ================================================
 * Defines the shared TemplateManager namespace and core functions.
 */

window.TemplateManager = window.TemplateManager || {};

Object.assign(window.TemplateManager, {
  _allTemplates: [],        // flat list from last fetch
  _activeId: null,          // currently selected template id
  _activeChannel: 'email',  // channel of the template currently open
  _dirty: false,            // unsaved changes flag
  _grapeEditor: null,       // GrapeJS instance (email only)

  /* Active-ID helpers */
  _getActiveId() { return this._activeId; },
  _setActiveId(v) {
    this._activeId = v;
    try {
      const desc = Object.getOwnPropertyDescriptor(TemplateManager, '_activeId');
      if (desc && desc.set) desc.set.call(TemplateManager, v);
    } catch (_) {}
  },

  /* ── DOM helpers ──────────────────────────────────────────────────────────── */
  $: id => document.getElementById(id),
  _getVal: id => { const el = document.getElementById(id); return el ? el.value : ''; },
  _setVal: (id, v) => { const el = document.getElementById(id); if (el) el.value = v; },

  _showSection(id) {
    ['tpl-list-section', 'tpl-editor-section', 'tpl-empty-section'].forEach(s => {
      const el = this.$(s);
      if (el) el.style.display = (s === id) ? '' : 'none';
    });
  },

  _toast(msg, type = 'success') {
    if (window.toast) { window.toast(type, msg); return; }
    console.info('[Templates]', msg);
  },

  _esc(s) {
    if (!s) return '';
    const div = document.createElement('div');
    div.innerText = s;
    return div.innerHTML;
  },
  
  _shortDate(isoString) {
    if (!isoString) return '';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return isoString;
    }
  },

  /* ── API calls ────────────────────────────────────────────────────────────── */
  async _apiFetch(path, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch('/api/templates' + path, opts);
    return res.json();
  },

  /* ── Init ─────────────────────────────────────────────────────────────────── */
  init() {
    this.loadTemplates();
    // Lazily load history when the History tab is first clicked
    const histTab = this.$('tpl-tab-history');
    if (histTab && !histTab._tplHistoryBound) {
      histTab._tplHistoryBound = true;
      histTab.addEventListener('click', () => this.loadHistory());
    }
  }
});
