/**
 * Hecos Template Manager â€” JavaScript API layer
 * ================================================
 * One function per concern. No global state pollution.
 * All state is encapsulated in the TemplateManager namespace.
 *
 * Public API (exposed via return):
 *   init, loadTemplates, openTemplate, newTemplate, saveTemplate,
 *   deleteTemplate, loadHistory, restoreVersion, previewRender,
 *   loadFlowVariables, onChannelChange, onTextBodyInput, insertVar
 *
 * _internal_activeId is synced to the external TemplateManager._activeId
 * property defined by _templates_logic.html to drive UI side-effects.
 */

window.TemplateManager = (() => {

  /* â”€â”€ Internal State â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
  let _allTemplates     = [];        // flat list from last fetch
  let _internal_activeId = null;     // currently selected template id
  let _grapeEditor      = null;      // GrapeJS instance (email only)
  let _activeChannel    = 'email';   // channel of the template currently open
  let _dirty            = false;     // unsaved changes flag

  /* Active-ID helpers */
  function _getActiveId() { return _internal_activeId; }
  function _setActiveId(v) {
    _internal_activeId = v;
    // Trigger the external property setter so _templates_logic.html can
    // show/hide the delete button without polling.
    try {
      const desc = Object.getOwnPropertyDescriptor(TemplateManager, '_activeId');
      if (desc && desc.set) desc.set.call(TemplateManager, v);
    } catch (_) {}
  }

  /* â”€â”€ DOM helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  const $ = id => document.getElementById(id);

  function _showSection(id) {
    ['tpl-list-section', 'tpl-editor-section', 'tpl-empty-section'].forEach(s => {
      const el = $(s);
      if (el) el.style.display = (s === id) ? '' : 'none';
    });
  }

  function _toast(msg, type = 'success') {
    if (window.toast) { window.toast(type, msg); return; }
    console.info('[Templates]', msg);
  }

  /* â”€â”€ API calls â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  async function _apiFetch(path, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch('/api/templates' + path, opts);
    return res.json();
  }

  /* â”€â”€ List templates â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  async function loadTemplates() {
    try {
      const data = await _apiFetch('/');
      _allTemplates = data.templates || [];
      _renderSidebar();
      if (!_getActiveId()) {
        _showSection('tpl-empty-section');
      }
    } catch (e) {
      _toast('Error loading templates: ' + e, 'error');
    }
  }

  function _renderSidebar() {
    const channels = ['email', 'whatsapp', 'telegram', 'discord', 'document'];
    channels.forEach(ch => {
      const list = $('tpl-list-' + ch);
      const countSpan = $('tpl-count-' + ch);
      if (!list) return;
      const items = _allTemplates.filter(t => t.channel === ch);
      
      if (countSpan) {
        countSpan.textContent = items.length > 0 ? `(${items.length})` : '';
      }

      list.innerHTML = items.length === 0
        ? `<div class="tpl-sidebar-empty">No templates yet</div>`
        : items.map(t => `
            <div class="tpl-sidebar-item ${t.id === _getActiveId() ? 'active' : ''}"
                 data-id="${t.id}"
                 style="cursor:pointer !important; font-size:0.83rem; user-select:none; display:flex; align-items:center; justify-content:space-between; padding:6px 14px; border-left:2px solid transparent; overflow:hidden; gap:8px;"
                 onclick="TemplateManager.openTemplate('${t.id}')">
              <span class="tpl-sidebar-name" style="cursor:pointer !important; flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:0.83rem; font-weight:400; user-select:none;">${_esc(t.name)}</span>
              <span class="tpl-sidebar-date" style="cursor:pointer !important; font-size:0.7rem; color:var(--muted); opacity:0.7; white-space:nowrap; user-select:none;">${_shortDate(t.updated_at)}</span>
            </div>`).join('');
    });

    const exportSelect = $('tpl-single-export-select');
    if (exportSelect) {
      exportSelect.innerHTML = _allTemplates.length === 0
        ? `<option value="" disabled selected>No templates available</option>`
        : `<option value="" disabled selected>Select a template...</option>` +
          _allTemplates.map(t => `<option value="${t.id}">${_esc(t.name)} (${t.channel})</option>`).join('');
    }
  }

  /* â”€â”€ Open / edit a template â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  async function openTemplate(id) {
    if (_dirty && !confirm('You have unsaved changes. Discard them?')) return;
    try {
      const data = await _apiFetch('/' + id);
      if (!data.ok) { _toast('Template not found', 'error'); return; }
      _setActiveId(id);
      _dirty         = false;
      _activeChannel = data.template.channel;
      _populateEditor(data.template);
      _showSection('tpl-editor-section');
      _renderSidebar();
    } catch (e) {
      _toast('Error loading template: ' + e, 'error');
    }
  }

  function _populateEditor(tpl) {
    _val('tpl-edit-name',        tpl.name        || '');
    _val('tpl-edit-description', tpl.description || '');

    const defaultCb = $('tpl-edit-is-default');
    if (defaultCb) defaultCb.checked = !!tpl.is_default;

    // Show template ID badge (for automations)
    _showTemplateId(_getActiveId());

    if (tpl.channel === 'email') {
      _val('tpl-edit-subject', tpl.subject || '');
      _setChannel(tpl.channel, tpl.body_html || tpl.body_text || '');
    } else if (tpl.channel === 'document') {
      _val('tpl-edit-subject-doc', tpl.subject || '');
      _setChannel(tpl.channel, tpl.body_html || '');
    } else {
      _setChannel(tpl.channel);
      _val('tpl-edit-header',    tpl.header    || '');
      _val('tpl-edit-body-text', tpl.body_text || '');
      _val('tpl-edit-footer',    tpl.footer    || '');
      _renderTextPreview(tpl.header || '', tpl.body_text || '', tpl.footer || '');
    }

    _renderVariables(tpl.variables || []);
    _renderHistory([]);
  }

  function _showTemplateId(id) {
    const badge = $('tpl-id-badge');
    if (!badge) return;
    if (!id) { badge.style.display = 'none'; return; }
    badge.style.display = 'inline-flex';
    const idSpan = badge.querySelector('.tpl-id-value');
    if (idSpan) idSpan.textContent = id;
  }


  function _previewDocumentHtml() {
    const html = $('tpl-doc-body')?.value || '';
    const w = window.open('', '_blank');
    if (w) { w.document.write(html); w.document.close(); }
  }

  /* â”€â”€ Channel switch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  function _setChannel(ch, html) {
    _activeChannel = ch;
    ['email', 'whatsapp', 'telegram', 'discord', 'document'].forEach(c => {
      const el = $('tpl-editor-' + c);
      if (el) el.style.display = (c === ch) ? '' : 'none';
    });
    const chSel = $('tpl-edit-channel');
    if (chSel) chSel.value = ch;

    // The shared GrapeJS wrapper is shown for both email and document
    const grapeWrapper = $('tpl-grapes-wrapper-shared');
    if (ch === 'email' || ch === 'document') {
      if (grapeWrapper) grapeWrapper.style.display = '';
      _initGrapeJS(html || '');
    } else {
      if (grapeWrapper) grapeWrapper.style.display = 'none';
      _destroyGrapeJS();
    }
  }

  function onChannelChange(ch) {
    _setChannel(ch);
    _dirty = true;
  }

  /* â”€â”€ GrapeJS (email editor) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  function _destroyGrapeJS() {
    if (_grapeEditor) {
      try { _grapeEditor.destroy(); } catch (_) {}
      _grapeEditor = null;
    }
    ['tpl-grapes-container', 'tpl-grapes-blocks', 'tpl-grapes-styles', 'tpl-grapes-traits'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = '';
    });
  }

  
  function _parseHtmlForGrapes(html) {
    if (!html) return { styles: '', body: '' };
    const isFullDoc = /<html[\s>]|<!doctype/i.test(html);
    if (!isFullDoc) {
      // Fragment: extract any inline <style> blocks so GrapeJS doesn't strip them
      const styleMatches = html.match(/<style[^>]*>([\s\S]*?)<\/style>/gi) || [];
      const styles = styleMatches.map(s => s.replace(/<\/?style[^>]*>/gi, '')).join('\n');
      const body   = html.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
      return { styles, body };
    }
    // Full HTML document: parse with DOMParser to safely extract head styles + body content
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const styleTexts = [];
    doc.querySelectorAll('style').forEach(el => styleTexts.push(el.textContent));
    const bodyHtml = doc.body ? doc.body.innerHTML : html;
    return { styles: styleTexts.join('\n'), body: bodyHtml };
  }

  function _initGrapeJS(pendingHtml) {
    if (typeof grapesjs === 'undefined') {
      console.warn('[Templates] GrapeJS not yet loaded, retrying...');
      setTimeout(() => _initGrapeJS(pendingHtml), 300);
      return;
    }

    _destroyGrapeJS();

    const loadingEl = $('tpl-grapes-loading');
    if (loadingEl) loadingEl.style.display = 'none';

    // Pre-parse so CSS variables from <style> blocks work inside the canvas iframe
    const parsed = _parseHtmlForGrapes(pendingHtml || '');
    const templateStyles = parsed.styles;
    const templateBody = parsed.body;

    _grapeEditor = grapesjs.init({
      container:  '#tpl-grapes-container',
      height:     '100%',
      width:      '100%',
      fromElement: false,
      storageManager: false,
      plugins:    [],
      pluginsOpts: {},

      blockManager:  { appendTo: '#tpl-grapes-blocks'  },
      styleManager:  {
        appendTo: '#tpl-grapes-styles',
        sectors: [
          { name: 'General',     open: true,  buildProps: ['float','display','position','top','right','left','bottom'] },
          { name: 'Flex',        open: false, buildProps: ['flex-direction','flex-wrap','justify-content','align-items','align-content','order','flex-basis','flex-grow','flex-shrink','align-self'] },
          { name: 'Dimension',   open: true,  buildProps: ['width','height','max-width','min-height','margin','padding'] },
          { name: 'Typography',  open: true,  buildProps: ['font-family','font-size','font-weight','letter-spacing','color','line-height','text-align','text-decoration','text-shadow'] },
          { name: 'Decorations', open: true,  buildProps: ['opacity','border-radius','border','box-shadow','background','background-color'] },
          { name: 'Extra',       open: false, buildProps: ['transition','perspective','transform'] },
        ],
      },
      traitManager:  { appendTo: '#tpl-grapes-traits' },
      panels: { defaults: [] },

      // Inject template's own CSS into canvas so custom properties (--ink, --accent...) resolve
      canvasCss: `
        body { margin: 0; padding: 20px; font-family: sans-serif; background: #f4f4f4; }
        [data-gjs-type] { outline: 1px dashed transparent; transition: outline .15s; }
        [data-gjs-type]:hover { outline: 1px dashed rgba(0,212,255,0.5); }
        ${templateStyles}
      `,
    });

    _grapeEditor.on('change:changesCount', () => { _dirty = true; });

    _grapeEditor.on('load', () => {
      const body = templateBody || window._tplPendingHtml || '';
      setTimeout(() => {
        if (body) {
          _grapeEditor.setComponents(body);
        } else {
          _grapeEditor.setComponents(_defaultEmailTemplate());
        }
        delete window._tplPendingHtml;
        setTimeout(() => { _dirty = false; }, 200);
      }, 80);
    });
  }


  function _defaultEmailTemplate() {
    return `
<table class="email-wrapper" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f4; padding:20px;">
  <tr><td align="center">

    <!-- â”€â”€ HEADER â”€â”€ -->
    <table class="email-header" width="600" cellpadding="0" cellspacing="0"
           style="background:#ffffff; border:2px dashed #00d4ff; border-radius:8px; margin-bottom:16px;">
      <tr><td style="padding:16px; text-align:center; font-family:sans-serif;">
        <p style="margin:0; color:#9ca3af; font-size:11px; text-transform:uppercase; letter-spacing:.1em;">Header</p>
        <h2 style="margin:12px 0 0; color:#1f2937; font-size:22px;">Company Name</h2>
      </td></tr>
    </table>

    <!-- â”€â”€ BODY â”€â”€ -->
    <table class="email-body" width="600" cellpadding="0" cellspacing="0"
           style="background:#ffffff; border:2px dashed #6366f1; border-radius:8px; margin-bottom:16px;">
      <tr><td style="padding:24px; font-family:sans-serif;">
        <p style="margin:0 0 4px; color:#9ca3af; font-size:11px; text-transform:uppercase; letter-spacing:.1em; text-align:center;">Body</p>
        <h3 style="margin:12px 0 8px; color:#1f2937; font-size:18px;">Hello {{ nome }},</h3>
        <p style="margin:0; color:#4b5563; line-height:1.7;">
          Scrivi qui il tuo messaggio. Clicca una volta per selezionare, doppio clic per modificare il testo.
        </p>
      </td></tr>
    </table>

    <!-- â”€â”€ FOOTER â”€â”€ -->
    <table class="email-footer" width="600" cellpadding="0" cellspacing="0"
           style="background:#ffffff; border:2px dashed #9ca3af; border-radius:8px;">
      <tr><td style="padding:16px; text-align:center; font-family:sans-serif;">
        <p style="margin:0 0 4px; color:#9ca3af; font-size:11px; text-transform:uppercase; letter-spacing:.1em;">Footer</p>
        <p style="margin:8px 0 0; color:#6b7280; font-size:13px;">
          Cordiali saluti,<br><strong>Il Team di Hecos</strong>
        </p>
      </td></tr>
    </table>

  </td></tr>
</table>`;
  }

  function _setEmailBody(html) {
    if (_grapeEditor) {
      _grapeEditor.setComponents(html || _defaultEmailTemplate());
    } else {
      window._tplPendingHtml = html;
    }
  }

  function _getEmailBody() {
    if (_grapeEditor) {
      try { 
        const html = _grapeEditor.getHtml();
        const css = _grapeEditor.getCss();
        return html + (css ? `<style>${css}</style>` : ''); 
      }
      catch { return ''; }
    }
    return '';
  }

  /* â”€â”€ Messenger plain-text editor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  function _renderTextPreview(header, text, footer) {
    const prev = $('tpl-text-preview');
    if (!prev) return;
    const headerVal = header !== undefined ? header : (_getVal('tpl-edit-header') || '');
    const footerVal = footer  !== undefined ? footer  : (_getVal('tpl-edit-footer')  || '');
    const parts = [headerVal, text, footerVal].filter(Boolean);
    prev.textContent = parts.join('\n\n') || '(empty)';
  }

  function onTextBodyInput(val) {
    _renderTextPreview(undefined, val, undefined);
    _dirty = true;
    _renderVariables(_extractVars(val));
  }

  /* â”€â”€ Variable extraction & picker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  function _extractVars(text) {
    const matches = (text || '').match(/\{\{\s*(\w+)\s*\}\}/g) || [];
    const seen = new Set();
    return matches
      .map(m => m.replace(/\{\{\s*|\s*\}\}/g, ''))
      .filter(v => { if (seen.has(v)) return false; seen.add(v); return true; });
  }

  function _renderVariables(vars) {
    const box = $('tpl-variables-list');
    if (!box) return;
    if (!vars || vars.length === 0) {
      box.innerHTML = '<span style="opacity:.5;font-size:.75rem">No variables detected</span>';
      return;
    }
    box.innerHTML = vars.map(v =>
      `<span class="tpl-var-chip" onclick="TemplateManager.insertVar('{{ ${v} }}')" title="Click to copy/insert">{{ ${v} }}</span>`
    ).join('');
  }

  function insertVar(placeholder) {
    const ta = $('tpl-edit-body-text');
    if (ta && (document.activeElement === ta || ta.matches(':focus'))) {
      const s = ta.selectionStart, e = ta.selectionEnd;
      ta.value = ta.value.slice(0, s) + placeholder + ta.value.slice(e);
      ta.selectionStart = ta.selectionEnd = s + placeholder.length;
      ta.focus();
    } else {
      navigator.clipboard.writeText(placeholder)
        .then(() => _toast(`Copied: ${placeholder}`))
        .catch(() => _toast(`Variable: ${placeholder}`));
    }
    _dirty = true;
  }

  /* â”€â”€ Flow variable picker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  async function loadFlowVariables() {
    try {
      const res = await fetch('/api/flows/variables');
      if (!res.ok) { _toast('Could not fetch variables', 'error'); return; }
      const data = await res.json();
      const vars = data.variables || [];
      if (vars.length) {
        _renderVariables(vars);
        _toast(`Loaded ${vars.length} variable(s) from saved flows`);
      } else {
        _toast('No variables found in any flow', 'info');
      }
    } catch (e) {
      _toast('Could not load flow variables: ' + e, 'error');
    }
  }

  /* â”€â”€ Save template â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  async function saveTemplate() {
    const name    = _getVal('tpl-edit-name').trim();
    const channel = _getVal('tpl-edit-channel');
    if (!name) { _toast('Name is required', 'error'); return; }

    let bodyHtml = '', bodyText = '', subject = '', footer = '';

    if (channel === 'email') {
      subject  = _getVal('tpl-edit-subject');
      bodyHtml = _getEmailBody();
      bodyText = _stripHtml(bodyHtml);
    } else if (channel === 'document') {
      subject  = _getVal('tpl-edit-subject-doc');
      bodyHtml = _getEmailBody();  // GrapeJS shared editor
      bodyText = _stripHtml(bodyHtml);
    } else {
      bodyText = _getVal('tpl-edit-body-text');
      footer   = _getVal('tpl-edit-footer');
    }
    const header = (channel !== 'email' && channel !== 'document') ? _getVal('tpl-edit-header') : '';
    const isDefaultCb = $('tpl-edit-is-default');
    const isDefault = isDefaultCb ? isDefaultCb.checked : false;

    const vars = _extractVars([subject, bodyHtml, bodyText].join(' '));

    const payload = {
      id:          _getActiveId() || undefined,
      name,
      channel,
      description: _getVal('tpl-edit-description'),
      subject,
      body_html:   bodyHtml,
      body_text:   bodyText,
      header,
      footer,
      is_default:  isDefault,
      variables:   vars,
    };

    try {
      const aid    = _getActiveId();
      const method = aid ? 'PUT'  : 'POST';
      const path   = aid ? '/' + aid : '/';
      const res    = await _apiFetch(path, method, payload);
      if (!res.ok) { _toast('Save error: ' + res.error, 'error'); return; }
      _setActiveId(res.template.id);
      _dirty = false;
      _toast('Template saved!');
      await loadTemplates();
      _showSection('tpl-editor-section');
      _renderSidebar();
    } catch (e) {
      _toast('Save failed: ' + e, 'error');
    }
  }

  /* â”€â”€ Delete template â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  async function deleteTemplate(id) {
    if (!id) { _toast('No template selected', 'error'); return; }
    const tpl = _allTemplates.find(t => t.id === id);
    if (!confirm(`Delete template "${tpl?.name || id}"? This cannot be undone.`)) return;
    try {
      const res = await _apiFetch('/' + id, 'DELETE');
      if (!res.ok) { _toast('Delete error: ' + res.error, 'error'); return; }
      if (_getActiveId() === id) {
        _setActiveId(null);
        _dirty = false;
        _showSection('tpl-empty-section');
      }
      _toast('Template deleted');
      await loadTemplates();
    } catch (e) {
      _toast('Delete failed: ' + e, 'error');
    }
  }

  function newTemplate(channel) {
    if (_dirty && !confirm('You have unsaved changes. Discard them?')) return;
    _setActiveId(null);
    _dirty = false;
    
    let defaultEmailHtml = '';
    const ch = channel || 'email';
    if (ch === 'email') {
      defaultEmailHtml = `
<table class="main" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f9f9f9; padding: 20px;">
  <tr>
    <td align="center" valign="top">
      
      <!-- HEADER -->
      <table width="600" cellspacing="0" cellpadding="0" border="0" style="background-color: #ffffff; border: 2px dashed #00d4ff; border-radius: 8px; margin-bottom: 20px;">
        <tr>
          <td align="center" style="padding: 20px;">
            <div style="color: #888; font-size: 12px; text-transform: uppercase; margin-bottom: 10px; font-family: sans-serif;">Header</div>
            <h2 style="color:#333; margin:0; font-family: sans-serif;">Company Logo / Title</h2>
          </td>
        </tr>
      </table>
      
      <!-- BODY -->
      <table width="600" cellspacing="0" cellpadding="0" border="0" style="background-color: #ffffff; border: 2px dashed #6366f1; border-radius: 8px; margin-bottom: 20px;">
        <tr>
          <td align="left" style="padding: 20px;">
            <div style="text-align: center; color: #888; font-size: 12px; text-transform: uppercase; margin-bottom: 10px; font-family: sans-serif;">Body</div>
            <div style="color:#444; line-height: 1.6; font-size: 16px; font-family: sans-serif;">
              <p>Hello {{ nome }},</p>
              <p>Trascina qui i blocchi per aggiungere contenuto. (Fai doppio-clic per modificare il testo)</p>
            </div>
          </td>
        </tr>
      </table>
      
      <!-- FOOTER -->
      <table width="600" cellspacing="0" cellpadding="0" border="0" style="background-color: #ffffff; border: 2px dashed #aaa; border-radius: 8px;">
        <tr>
          <td align="center" style="padding: 20px;">
            <div style="color: #888; font-size: 12px; text-transform: uppercase; margin-bottom: 10px; font-family: sans-serif;">Footer</div>
            <div style="color:#777; font-size: 13px; font-family: sans-serif;">
              <p>Regards,<br>Hecos Team</p>
            </div>
          </td>
        </tr>
      </table>

    </td>
  </tr>
</table>`;
    }

    _populateEditor({
      name: '', channel: ch, description: '',
      subject: '', body_html: defaultEmailHtml, body_text: '', header: '', footer: '', is_default: false, variables: []
    });
    _showSection('tpl-editor-section');
    _renderSidebar();
  }

  /* â”€â”€ Version history â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  async function loadHistory() {
    const aid = _getActiveId();
    if (!aid) return;
    try {
      const data = await _apiFetch('/' + aid + '/history');
      _renderHistory(data.history || []);
    } catch (e) {
      _toast('Error loading history: ' + e, 'error');
    }
  }

  function _renderHistory(history) {
    const box = $('tpl-history-list');
    if (!box) return;
    if (!history.length) {
      box.innerHTML = '<div class="tpl-history-empty">No versions yet</div>';
      return;
    }
    box.innerHTML = history.map((v, i) => `
      <div class="tpl-history-item">
        <span class="tpl-history-date">${_shortDate(v.snapshot_at)}</span>
        <span class="tpl-history-name">${_esc(v.name)}</span>
        <button class="tpl-history-restore" onclick="TemplateManager.restoreVersion(${i})">
          <i class="fas fa-undo"></i> Restore
        </button>
      </div>`).join('');
  }

  async function restoreVersion(index) {
    const aid = _getActiveId();
    if (!aid) return;
    if (!confirm(`Restore version #${index + 1}? Current state will be saved first.`)) return;
    try {
      const res = await _apiFetch('/' + aid + '/restore/' + index, 'POST');
      if (!res.ok) { _toast('Restore error: ' + res.error, 'error'); return; }
      _dirty = false;
      _populateEditor(res.template);
      _toast('Version restored!');
      await loadHistory();
    } catch (e) {
      _toast('Restore failed: ' + e, 'error');
    }
  }

  /* â”€â”€ Preview / render â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  async function previewRender() {
    const aid = _getActiveId();
    if (!aid) { _toast('Save the template first', 'info'); return; }
    const varsRaw = _getVal('tpl-preview-vars');
    let variables = {};
    try { variables = JSON.parse(varsRaw || '{}'); }
    catch { _toast('Invalid JSON for variables', 'error'); return; }
    try {
      const res = await _apiFetch('/' + aid + '/render', 'POST', { variables });
      if (!res.ok) { _toast('Render error: ' + res.error, 'error'); return; }
      const r = res.rendered;
      const iframe = $('tpl-preview-iframe');
      if (_activeChannel === 'email' && iframe) {
        iframe.srcdoc = r.body_html || `<pre>${_esc(r.body_text)}</pre>`;
        iframe.style.display = '';
      }
      // For messenger channels, combine header + body + footer
      const prev = $('tpl-preview-text');
      if (prev) {
        const parts = [r.header, r.body_text, r.footer].filter(Boolean);
        prev.textContent = parts.join('\n\n') || '';
      }
      const subj = $('tpl-preview-subject');
      if (subj) subj.textContent = r.subject || 'â€”';
    } catch (e) {
      _toast('Preview failed: ' + e, 'error');
    }
  }

  /* â”€â”€ Utility helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  function _val(id, v)  { const el = $(id); if (el && v !== undefined) el.value = v; }
  function _getVal(id)  { const el = $(id); return el ? el.value : ''; }
  function _esc(s)      { return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  function _shortDate(iso) {
    if (!iso) return '';
    try { return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
    catch { return iso.slice(0, 10); }
  }

  function _stripHtml(html) {
    const tmp = document.createElement('div');
    tmp.innerHTML = html;
    return (tmp.textContent || tmp.innerText || '').trim();
  }

  /* â”€â”€ Init â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

  function init() {
    loadTemplates();
    // Lazily load history when the History tab is first clicked
    const histTab = $('tpl-tab-history');
    if (histTab && !histTab._tplHistoryBound) {
      histTab._tplHistoryBound = true;
      histTab.addEventListener('click', loadHistory);
    }
  }

  /* â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
  return {
    // State (read by _templates_logic.html for the delete button)
    _internal_activeId: null,
    // Methods
    init,
    loadTemplates,
    openTemplate,
    newTemplate,
    saveTemplate,
    deleteTemplate,
    loadHistory,
    restoreVersion,
    previewRender,
    loadFlowVariables,
    onChannelChange,
    onTextBodyInput,
    insertVar,
    _previewDocumentHtml,
  };

})();

// Auto-init for Hecos dynamic loading
setTimeout(() => {
    if (window.TemplateManager) {
        window.TemplateManager.init();
    }
}, 500);

window.tplInsertVar = function(v) {
  if (window.TemplateManager && window.TemplateManager.insertVar) {
    window.TemplateManager.insertVar(v);
  }
};

// Tab switching helper
window.tplSwitchTab = function(btn, paneId) {
    const tabs = btn.parentElement.querySelectorAll('.tpl-tab');
    tabs.forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    
    ['tpl-tab-content', 'tpl-tab-variables', 'tpl-tab-preview', 'tpl-tab-history-pane'].forEach(p => {
        const el = document.getElementById(p);
        if (el) el.style.display = 'none';
    });
    
    const target = document.getElementById(paneId);
    if (target) target.style.display = 'block';
    
    if (paneId === 'tpl-tab-history-pane' && window.TemplateManager && window.TemplateManager.loadHistory) {
        window.TemplateManager.loadHistory();
    }
};

// Char count helper
window.tplUpdateCharCount = function(textarea) {
    const wrap = textarea.closest('.tpl-textarea-wrap');
    if (wrap) {
        const countSpan = wrap.querySelector('.tpl-char-num');
        if (countSpan) countSpan.textContent = textarea.value.length;
    }
};
