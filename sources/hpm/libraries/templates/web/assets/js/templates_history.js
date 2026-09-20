/**
 * Hecos Template Manager — History & Preview Logic
 * ================================================
 */

window.TemplateManager = window.TemplateManager || {};

Object.assign(window.TemplateManager, {

  async loadHistory() {
    const aid = this._getActiveId();
    if (!aid) return;
    try {
      const data = await this._apiFetch('/' + aid + '/history');
      this._renderHistory(data.history || []);
    } catch (e) {
      this._toast('Error loading history: ' + e, 'error');
    }
  },

  _renderHistory(history) {
    const box = this.$('tpl-history-list');
    if (!box) return;
    if (!history.length) {
      box.innerHTML = '<div class="tpl-history-empty">No versions yet</div>';
      return;
    }
    box.innerHTML = history.map((v, i) => `
      <div class="tpl-history-item">
        <span class="tpl-history-date">${this._shortDate(v.snapshot_at)}</span>
        <span class="tpl-history-name">${this._esc(v.name)}</span>
        <button class="tpl-history-restore" onclick="TemplateManager.restoreVersion(${i})">
          <i class="fas fa-undo"></i> Restore
        </button>
      </div>`).join('');
  },

  async restoreVersion(index) {
    const aid = this._getActiveId();
    if (!aid) return;
    if (!confirm(`Restore version #${index + 1}? Current state will be saved first.`)) return;
    try {
      const res = await this._apiFetch('/' + aid + '/restore/' + index, 'POST');
      if (!res.ok) { this._toast('Restore error: ' + res.error, 'error'); return; }
      this._dirty = false;
      this._populateEditor(res.template);
      this._toast('Version restored!');
      await this.loadHistory();
    } catch (e) {
      this._toast('Restore failed: ' + e, 'error');
    }
  },

  async previewRender() {
    const aid = this._getActiveId();
    if (!aid) { this._toast('Save the template first', 'info'); return; }
    const varsRaw = this._getVal('tpl-preview-vars');
    let variables = {};
    try { variables = JSON.parse(varsRaw || '{}'); }
    catch { this._toast('Invalid JSON for variables', 'error'); return; }
    try {
      const res = await this._apiFetch('/' + aid + '/render', 'POST', { variables });
      if (!res.ok) { this._toast('Render error: ' + res.error, 'error'); return; }
      const r = res.rendered;
      const iframe = this.$('tpl-preview-iframe');
      if (this._activeChannel === 'email' && iframe) {
        iframe.srcdoc = r.body_html || `<pre>${this._esc(r.body_text)}</pre>`;
        iframe.style.display = '';
      }
      const prev = this.$('tpl-preview-text');
      if (prev) {
        const parts = [r.header, r.body_text, r.footer].filter(Boolean);
        prev.textContent = parts.join('\n\n') || '';
      }
      const subj = this.$('tpl-preview-subject');
      if (subj) subj.textContent = r.subject || '—';
    } catch (e) {
      this._toast('Preview failed: ' + e, 'error');
    }
  }

});
