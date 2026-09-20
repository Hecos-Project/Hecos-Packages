/**
 * Hecos Template Manager — Sidebar Logic
 * ================================================
 */

window.TemplateManager = window.TemplateManager || {};

Object.assign(window.TemplateManager, {

  async loadTemplates() {
    try {
      const data = await this._apiFetch('/');
      this._allTemplates = data.templates || [];
      this._renderSidebar();
      if (!this._getActiveId()) {
        this._showSection('tpl-empty-section');
      }
    } catch (e) {
      this._toast('Error loading templates: ' + e, 'error');
    }
  },

  _renderSidebar() {
    const channels = ['email', 'whatsapp', 'telegram', 'discord', 'document'];
    channels.forEach(ch => {
      const list = this.$('tpl-list-' + ch);
      const countSpan = this.$('tpl-count-' + ch);
      if (!list) return;
      const items = this._allTemplates.filter(t => t.channel === ch);
      
      if (countSpan) {
        countSpan.textContent = items.length > 0 ? `(${items.length})` : '';
      }

      list.innerHTML = items.length === 0
        ? `<div class="tpl-sidebar-empty">No templates yet</div>`
        : items.map(t => `
            <div class="tpl-sidebar-item ${t.id === this._getActiveId() ? 'active' : ''}"
                 data-id="${t.id}" onclick="TemplateManager.openTemplate('${t.id}')">
              <span class="tpl-sidebar-name">${this._esc(t.name)}</span>
              <span class="tpl-sidebar-date">${this._shortDate(t.updated_at)}</span>
            </div>`).join('');
    });

    const exportSelect = this.$('tpl-single-export-select');
    if (exportSelect) {
      exportSelect.innerHTML = this._allTemplates.length === 0
        ? `<option value="" disabled selected>No templates available</option>`
        : `<option value="" disabled selected>Select a template...</option>` +
          this._allTemplates.map(t => `<option value="${t.id}">${this._esc(t.name)} (${t.channel})</option>`).join('');
    }
  }

});
