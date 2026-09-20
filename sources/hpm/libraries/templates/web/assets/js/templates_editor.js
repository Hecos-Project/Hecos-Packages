/**
 * Hecos Template Manager — Editor Logic
 * ================================================
 */

window.TemplateManager = window.TemplateManager || {};

Object.assign(window.TemplateManager, {

  async openTemplate(id) {
    if (this._dirty && !confirm('You have unsaved changes. Discard them?')) return;
    try {
      const data = await this._apiFetch('/' + id);
      if (!data.ok) { this._toast('Template not found', 'error'); return; }
      this._setActiveId(id);
      this._dirty = false;
      this._activeChannel = data.template.channel;
      this._populateEditor(data.template);
      this._showSection('tpl-editor-section');
      this._renderSidebar();
    } catch (e) {
      this._toast('Error loading template: ' + e, 'error');
    }
  },

  _populateEditor(tpl) {
    this._setVal('tpl-edit-name',        tpl.name        || '');
    this._setVal('tpl-edit-description', tpl.description || '');

    const defaultCb = this.$('tpl-edit-is-default');
    if (defaultCb) defaultCb.checked = !!tpl.is_default;

    if (tpl.channel === 'email') {
      this._setVal('tpl-edit-subject', tpl.subject || '');
      this._setChannel(tpl.channel, tpl.body_html || tpl.body_text || '');
    } else if (tpl.channel === 'document') {
      this._setVal('tpl-edit-subject-doc', tpl.subject || '');
      this._setVal('tpl-doc-body', tpl.body_html || '');
      this._setChannel(tpl.channel);
      this._previewDocumentHtml();
    } else {
      this._setChannel(tpl.channel);
      this._setVal('tpl-edit-header',    tpl.header    || '');
      this._setVal('tpl-edit-body-text', tpl.body_text || '');
      this._setVal('tpl-edit-footer',    tpl.footer    || '');
      this._renderTextPreview(tpl.header || '', tpl.body_text || '', tpl.footer || '');
    }

    this._renderVariables(tpl.variables || []);
    if (this._renderHistory) this._renderHistory([]);
  },

  _previewDocumentHtml() {
    const html = this.$('tpl-doc-body')?.value || '';
    const w = window.open('', '_blank');
    if (w) { w.document.write(html); w.document.close(); }
  },

  _setChannel(ch, emailHtml) {
    this._activeChannel = ch;
    ['email', 'whatsapp', 'telegram', 'discord', 'document'].forEach(c => {
      const el = this.$('tpl-editor-' + c);
      if (el) el.style.display = (c === ch) ? '' : 'none';
    });
    const chSel = this.$('tpl-edit-channel');
    if (chSel) chSel.value = ch;

    if (ch === 'email' && this._initGrapeJS) {
      this._initGrapeJS(emailHtml || '');
    }
  },

  onChannelChange(ch) {
    this._setChannel(ch);
    this._dirty = true;
  },

  /* ── Variables ───────────────────────────────────────────────────────────── */

  _extractVars(text) {
    const matches = (text || '').match(/\{\{\s*(\w+)\s*\}\}/g) || [];
    const seen = new Set();
    return matches
      .map(m => m.replace(/\{\{\s*|\s*\}\}/g, ''))
      .filter(v => { if (seen.has(v)) return false; seen.add(v); return true; });
  },

  _renderVariables(vars) {
    const box = this.$('tpl-variables-list');
    if (!box) return;
    if (!vars || vars.length === 0) {
      box.innerHTML = '<span style="opacity:.5;font-size:.75rem">No variables detected</span>';
      return;
    }
    box.innerHTML = vars.map(v =>
      `<span class="tpl-var-chip" onclick="TemplateManager.insertVar('{{ ${v} }}')" title="Click to copy/insert">{{ ${v} }}</span>`
    ).join('');
  },

  insertVar(placeholder) {
    const ta = this.$('tpl-edit-body-text');
    if (ta && (document.activeElement === ta || ta.matches(':focus'))) {
      const s = ta.selectionStart, e = ta.selectionEnd;
      ta.value = ta.value.slice(0, s) + placeholder + ta.value.slice(e);
      ta.selectionStart = ta.selectionEnd = s + placeholder.length;
      ta.focus();
    } else {
      navigator.clipboard.writeText(placeholder)
        .then(() => this._toast(`Copied: ${placeholder}`))
        .catch(() => this._toast(`Variable: ${placeholder}`));
    }
    this._dirty = true;
  },

  async loadFlowVariables() {
    try {
      const res = await fetch('/api/flows/variables');
      if (!res.ok) { this._toast('Could not fetch variables', 'error'); return; }
      const data = await res.json();
      const vars = data.variables || [];
      if (vars.length) {
        this._renderVariables(vars);
        this._toast(`Loaded ${vars.length} variable(s) from saved flows`);
      } else {
        this._toast('No variables found in any flow', 'info');
      }
    } catch (e) {
      this._toast('Could not load flow variables: ' + e, 'error');
    }
  },

  _renderTextPreview(header, text, footer) {
    const prev = this.$('tpl-text-preview');
    if (!prev) return;
    const headerVal = header !== undefined ? header : (this._getVal('tpl-edit-header') || '');
    const footerVal = footer  !== undefined ? footer  : (this._getVal('tpl-edit-footer')  || '');
    const parts = [headerVal, text, footerVal].filter(Boolean);
    prev.textContent = parts.join('\n\n') || '(empty)';
  },

  onTextBodyInput(val) {
    this._renderTextPreview(undefined, val, undefined);
    this._dirty = true;
    this._renderVariables(this._extractVars(val));
  },

  /* ── Save and Delete ─────────────────────────────────────────────────────── */

  _stripHtml(html) {
    const tmp = document.createElement('div');
    tmp.innerHTML = html;
    return (tmp.textContent || tmp.innerText || '').trim();
  },

  newTemplate(channel) {
    if (this._dirty && !confirm('You have unsaved changes. Discard them?')) return;
    this._setActiveId(null);
    this._dirty = false;
    
    let defaultEmailHtml = '';
    const ch = channel || 'email';
    if (ch === 'email') {
      defaultEmailHtml = `
<table class="main" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f9f9f9; padding: 20px;">
  <tr><td align="center" valign="top">
      <table width="600" cellspacing="0" cellpadding="0" border="0" style="background-color: #ffffff; border: 2px dashed #00d4ff; border-radius: 8px; margin-bottom: 20px;">
        <tr><td align="center" style="padding: 20px;">
            <div style="color: #888; font-size: 12px; text-transform: uppercase; margin-bottom: 10px; font-family: sans-serif;">Header</div>
            <h2 style="color:#333; margin:0; font-family: sans-serif;">Company Logo / Title</h2>
        </td></tr>
      </table>
      <table width="600" cellspacing="0" cellpadding="0" border="0" style="background-color: #ffffff; border: 2px dashed #6366f1; border-radius: 8px; margin-bottom: 20px;">
        <tr><td style="padding: 30px; font-family: sans-serif; color: #333; line-height: 1.6;">
            <div style="color: #888; font-size: 12px; text-transform: uppercase; margin-bottom: 10px; text-align:center;">Body</div>
            <h3 style="margin-top:0;">Hello {{ nome }},</h3>
            <p>Write your message here. Double click to edit.</p>
        </td></tr>
      </table>
      <table width="600" cellspacing="0" cellpadding="0" border="0" style="background-color: #ffffff; border: 2px dashed #ccc; border-radius: 8px;">
        <tr><td align="center" style="padding: 20px;">
            <div style="color: #888; font-size: 12px; text-transform: uppercase; margin-bottom: 10px; font-family: sans-serif;">Footer</div>
            <p style="margin:0; font-family: sans-serif; font-size: 13px; color: #777;">
              Best regards,<br><strong>The Hecos Team</strong>
            </p>
        </td></tr>
      </table>
  </td></tr>
</table>`;
    }

    this._populateEditor({ channel: ch, body_html: defaultEmailHtml });
    this._showSection('tpl-editor-section');
    this._renderSidebar();
    this.$('tpl-edit-name')?.focus();
  },

  async saveTemplate() {
    const name    = this._getVal('tpl-edit-name').trim();
    const channel = this._getVal('tpl-edit-channel');
    if (!name) { this._toast('Name is required', 'error'); return; }

    let bodyHtml = '', bodyText = '', subject = '', footer = '';

    if (channel === 'email') {
      subject  = this._getVal('tpl-edit-subject');
      bodyHtml = this._getEmailBody ? this._getEmailBody() : '';
      bodyText = this._stripHtml(bodyHtml);
    } else if (channel === 'document') {
      subject  = this._getVal('tpl-edit-subject-doc');
      bodyHtml = this._getVal('tpl-doc-body');
      bodyText = this._stripHtml(bodyHtml);
    } else {
      bodyText = this._getVal('tpl-edit-body-text');
      footer   = this._getVal('tpl-edit-footer');
    }
    const header = (channel !== 'email' && channel !== 'document') ? this._getVal('tpl-edit-header') : '';
    const isDefaultCb = this.$('tpl-edit-is-default');
    const isDefault = isDefaultCb ? isDefaultCb.checked : false;

    const vars = this._extractVars([subject, bodyHtml, bodyText].join(' '));

    const payload = {
      id:          this._getActiveId() || undefined,
      name,
      channel,
      description: this._getVal('tpl-edit-description'),
      subject,
      body_html:   bodyHtml,
      body_text:   bodyText,
      header,
      footer,
      is_default:  isDefault,
      variables:   vars,
    };

    try {
      const aid    = this._getActiveId();
      const method = aid ? 'PUT'  : 'POST';
      const path   = aid ? '/' + aid : '/';
      const res    = await this._apiFetch(path, method, payload);
      if (!res.ok) { this._toast('Save error: ' + res.error, 'error'); return; }
      this._setActiveId(res.template.id);
      this._dirty = false;
      this._toast('Template saved!');
      await this.loadTemplates();
      this._showSection('tpl-editor-section');
      this._renderSidebar();
    } catch (e) {
      this._toast('Save failed: ' + e, 'error');
    }
  },

  async deleteTemplate(id) {
    if (!id) { this._toast('No template selected', 'error'); return; }
    const tpl = this._allTemplates.find(t => t.id === id);
    if (!confirm(`Delete template "${tpl?.name || id}"? This cannot be undone.`)) return;
    try {
      const res = await this._apiFetch('/' + id, 'DELETE');
      if (!res.ok) { this._toast('Delete error: ' + res.error, 'error'); return; }
      if (this._getActiveId() === id) {
        this._setActiveId(null);
        this._dirty = false;
        this._showSection('tpl-empty-section');
      }
      this._toast('Template deleted');
      await this.loadTemplates();
    } catch (e) {
      this._toast('Delete failed: ' + e, 'error');
    }
  }

});
