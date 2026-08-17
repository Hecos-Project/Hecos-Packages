/* ── Templates Manager — Client Logic ────────────────────────────────── */
(function () {
  'use strict';

  const API = '/api/templates';

  /* ── helpers ─────────────────────────────────────────────────────── */
  function _show(id)  { const el = document.getElementById(id); if (el) el.style.display = ''; }
  function _hide(id)  { const el = document.getElementById(id); if (el) el.style.display = 'none'; }
  function _val(id)   { const el = document.getElementById(id); return el ? el.value : ''; }
  function _set(id,v) { const el = document.getElementById(id); if (el) el.value = v; }
  function _text(id,v){ const el = document.getElementById(id); if (el) el.textContent = v; }
  function _html(id,v){ const el = document.getElementById(id); if (el) el.innerHTML = v; }
  async function api(method, path, body) {
    const opts = { method, headers: {'Content-Type':'application/json'} };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(API + path, opts);
    return res.json();
  }

  /* ── state ───────────────────────────────────────────────────────── */
  let _templates = [];   // flat list from server
  let _activeId  = null;
  let _dirty     = false;
  let _grapes    = null; // GrapeJS instance
  let _currentTemplate = null;

  /* ── public API ──────────────────────────────────────────────────── */
  const TM = {
    _activeId,
    _dirty,

    /* init — called after tab becomes visible */
    init() {
      this.loadAll();
    },

    /* ── LOAD ──────────────────────────────────────────────────────── */
    async loadAll() {
      const res = await api('GET', '/');
      if (!res.ok) return;
      _templates = res.templates || [];
      this._renderSidebar();
    },

    _renderSidebar() {
      const channels = ['email','whatsapp','telegram','discord'];
      channels.forEach(ch => {
        const list = document.getElementById('tpl-list-' + ch);
        const countSpan = document.getElementById('tpl-count-' + ch);
        if (!list) return;
        const items = _templates.filter(t => t.channel === ch);
        if (countSpan) countSpan.textContent = '(' + items.length + ')';
        if (!items.length) {
          list.innerHTML = '<div class="tpl-sidebar-empty">No templates</div>';
          return;
        }
        list.innerHTML = items.map(t => `
          <div class="tpl-channel-item ${t.id === _activeId ? 'active' : ''}"
               onclick="TemplateManager.openTemplate('${t.id}')">
            <i class="fas fa-file-alt"></i>
            <span>${t.name || 'Unnamed'}</span>
          </div>`).join('');
      });
      // Populate single-export select
      const sel = document.getElementById('tpl-single-export-select');
      if (sel) {
        sel.innerHTML = _templates.map(t =>
          `<option value="${t.id}">[${t.channel}] ${t.name}</option>`
        ).join('');
      }
    },

    /* ── OPEN ──────────────────────────────────────────────────────── */
    async openTemplate(id) {
      if (_dirty && !(await tplShowConfirm('You have unsaved changes. Discard?'))) return;
      _activeId = id;
      _dirty = false;
      const res = await api('GET', '/' + id);
      if (!res.ok) { window.showToast && window.showToast('Could not load template', 'error'); return; }
      const t = res.template;
      _currentTemplate = t;
      this._renderEditor(t);
      this._renderSidebar();
      // GrapeJS sets dirty=true when components are loaded programmatically.
      // Reset it after a short delay to ignore the initial load event.
      setTimeout(() => { _dirty = false; TM._dirty = false; }, 100);
    },

    _renderEditor(t) {
      _set('tpl-edit-name', t.name || '');
      _set('tpl-edit-description', t.description || '');
      const isDefaultEl = document.getElementById('tpl-edit-is-default');
      if (isDefaultEl) isDefaultEl.checked = !!t.is_default;
      const chSel = document.getElementById('tpl-edit-channel');
      if (chSel) chSel.value = t.channel || 'email';
      this.onChannelChange(t.channel || 'email', t);

      const delBtn = document.getElementById('tpl-delete-btn');
      if (delBtn) delBtn.style.display = '';

      _hide('tpl-empty-section');
      _show('tpl-editor-section');

      // History tab
      this._renderHistory(t.versions || []);
    },

    onChannelChange(ch, tpl) {
      ['email','whatsapp','telegram','discord'].forEach(c => {
        const el = document.getElementById('tpl-editor-' + c);
        if (el) el.style.display = (c === ch) ? '' : 'none';
      });
      if (ch === 'email') {
        let fullHtml = tpl ? (tpl.body_html || '') : '';
        if (tpl && tpl.body_text) {
          fullHtml = '<style>' + tpl.body_text + '</style>\n' + fullHtml;
        }
        this._initGrapes(fullHtml);
        
        // Populate header and footer for email
        const container = document.getElementById('tpl-editor-email');
        if (container) {
          const headerTa = container.querySelector('.tpl-header-textarea');
          const footerTa = container.querySelector('.tpl-footer-textarea');
          if (headerTa) headerTa.value = tpl ? (tpl.header || '') : '';
          if (footerTa) footerTa.value = tpl ? (tpl.footer || '') : '';
        }
      } else {
        const container = document.getElementById('tpl-editor-' + ch);
        if (!container) return;
        // Fill the 3 sections: header, body (body_text), footer
        const headerTa = container.querySelector('.tpl-header-textarea');
        const bodyTa   = container.querySelector('.tpl-main-textarea');
        const footerTa = container.querySelector('.tpl-footer-textarea');
        if (headerTa) headerTa.value = tpl ? (tpl.header || '') : '';
        if (bodyTa)   { bodyTa.value = tpl ? (tpl.body_text || '') : ''; tplUpdateCharCount(bodyTa); }
        if (footerTa) footerTa.value = tpl ? (tpl.footer || '') : '';
      }
    },

    _initGrapes(html) {
      if (_grapes) {
          // If GrapeJS is already init, we must set components AND styles.
          // By passing a string with <style>, GrapeJS parses both.
          _grapes.setComponents(html);
          return;
      }
      if (typeof grapesjs === 'undefined') return;
      const loading = document.getElementById('tpl-grapes-loading');
      if (loading) loading.style.display = 'none';
      _grapes = grapesjs.init({
        container: '#tpl-grapes-container',
        fromElement: false,
        components: html,
        blockManager: { appendTo: '#tpl-grapes-blocks' },
        styleManager: { appendTo: '#tpl-grapes-styles' },
        traitManager:  { appendTo: '#tpl-grapes-traits' },
        panels: { defaults: [] },
        storageManager: false,
      });
      _grapes.on('change:changesCount', () => { _dirty = true; });
    },

    /* ── NEW ───────────────────────────────────────────────────────── */
    async newTemplate(ch) {
      if (_dirty && !(await tplShowConfirm('Discard unsaved changes?'))) return;
      _activeId = null;
      _dirty = false;
      _currentTemplate = null;
      this._renderEditor({ name:'', description:'', channel: ch||'email', body:'', body_html:'', is_default:false, versions:[] });
      const delBtn = document.getElementById('tpl-delete-btn');
      if (delBtn) delBtn.style.display = 'none';
    },

    /* ── SAVE ─────────────────────────────────────────────────────── */
    async saveTemplate() {
      const ch = _val('tpl-edit-channel');
      let body_text = '';
      let body_html = '';
      let header = '';
      let footer = '';
      if (ch === 'email') {
        body_html = _grapes ? _grapes.getHtml() : '';
        body_text = _grapes ? _grapes.getCss() : '';
        // Read header and footer from the textareas
        const container = document.getElementById('tpl-editor-email');
        if (container) {
          header = (container.querySelector('.tpl-header-textarea') || {}).value || '';
          footer = (container.querySelector('.tpl-footer-textarea') || {}).value || '';
        }
      } else {
        const container = document.getElementById('tpl-editor-' + ch);
        if (container) {
          header    = (container.querySelector('.tpl-header-textarea') || {}).value || '';
          body_text = (container.querySelector('.tpl-main-textarea')   || {}).value || '';
          footer    = (container.querySelector('.tpl-footer-textarea') || {}).value || '';
        }
      }
      const isDefaultEl = document.getElementById('tpl-edit-is-default');
      const payload = {
        name: _val('tpl-edit-name'),
        description: _val('tpl-edit-description'),
        channel: ch,
        header,
        body_text,
        body_html,
        footer,
        is_default: isDefaultEl ? isDefaultEl.checked : false,
      };
      if (!payload.name) { window.showToast && window.showToast('Template name is required', 'warning'); return; }

      let res;
      if (_activeId) {
        res = await api('PUT', '/' + _activeId, payload);
      } else {
        res = await api('POST', '/', payload);
      }
      if (res.ok) {
        _dirty = false;
        _activeId = res.template ? res.template.id : _activeId;
        window.showToast && window.showToast('Template saved', 'success');
        await this.loadAll();
        // Re-render history
        if (_activeId) {
          const tRes = await api('GET', '/' + _activeId);
          if (tRes.ok) this._renderHistory(tRes.template.versions || []);
        }
      } else {
        window.showToast && window.showToast('Save failed: ' + (res.error||'unknown'), 'error');
      }
    },

    /* ── DELETE ────────────────────────────────────────────────────── */
    async deleteTemplate(id) {
      id = id || _activeId;
      if (!id) return;
      if (!(await tplShowConfirm('Delete this template?', 'Delete'))) return;
      const res = await api('DELETE', '/' + id);
      if (res.ok) {
        _activeId = null;
        _dirty = false;
        _hide('tpl-editor-section');
        _show('tpl-empty-section');
        window.showToast && window.showToast('Template deleted', 'success');
        await this.loadAll();
      } else {
        window.showToast && window.showToast('Delete failed', 'error');
      }
    },

    /* ── HISTORY ───────────────────────────────────────────────────── */
    _renderHistory(versions) {
      const list = document.getElementById('tpl-history-list');
      if (!list) return;
      if (!versions.length) {
        list.innerHTML = '<div class="tpl-history-empty">No versions yet</div>';
        return;
      }
      list.innerHTML = versions.map((v, i) => `
        <div class="tpl-history-item">
          <span>${v.saved_at || ('Version ' + (versions.length - i))}</span>
          <button class="tpl-btn" onclick="TemplateManager.restoreVersion('${_activeId}',${i})">
            <i class="fas fa-undo"></i> Restore
          </button>
        </div>`).join('');
    },

    async restoreVersion(id, idx) {
      if (!(await tplShowConfirm('Restore this version?', 'Restore'))) return;
      const res = await api('POST', '/' + id + '/restore/' + idx);
      if (res.ok) {
        window.showToast && window.showToast('Version restored', 'success');
        await this.openTemplate(id);
      }
    },

    /* ── VARIABLES ─────────────────────────────────────────────────── */
    loadFlowVariables() {
      window.showToast && window.showToast('Flow variables import not available in this context', 'info');
    },

    /* ── EXPORT / IMPORT ───────────────────────────────────────────── */
    async exportTemplates() {
      const res = await api('GET', '/');
      if (!res.ok) return;
      const blob = new Blob([JSON.stringify(res.templates, null, 2)], {type:'application/json'});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'hecos_templates_backup.json';
      a.click();
    },

    async exportSingleTemplate() {
      const id = document.getElementById('tpl-single-export-select')?.value;
      if (!id) return;
      const res = await api('GET', '/' + id);
      if (!res.ok) return;
      const blob = new Blob([JSON.stringify(res.template, null, 2)], {type:'application/json'});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (res.template.name || id) + '.json';
      a.click();
    },

    importTemplates(event) {
      const file = event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async e => {
        try {
          const templates = JSON.parse(e.target.result);
          const arr = Array.isArray(templates) ? templates : [templates];
          for (const t of arr) {
            await api('POST', '/', t);
          }
          window.showToast && window.showToast(`Imported ${arr.length} template(s)`, 'success');
          await this.loadAll();
        } catch(err) {
          window.showToast && window.showToast('Import failed: invalid JSON', 'error');
        }
      };
      reader.readAsText(file);
    },

    importSingleFile(event) { this.importTemplates(event); },

    importSingleDrop(event) {
      event.preventDefault();
      const dt = event.dataTransfer;
      if (!dt || !dt.files.length) return;
      const fakeEvent = { target: { files: dt.files } };
      this.importTemplates(fakeEvent);
      event.currentTarget.classList.remove('drag-over');
    },

    /* ── PREVIEW ───────────────────────────────────────────────────── */
    async previewRender() {
      if (!_activeId) return;
      if (_dirty) {
        await this.saveTemplate();
      }
      let variables = {};
      try { variables = JSON.parse(_val('tpl-preview-vars') || '{}'); } catch(e) {}
      const res = await api('POST', '/' + _activeId + '/render', { variables });
      if (!res.ok) { window.showToast && window.showToast('Preview failed', 'error'); return; }
      
      const rendered = res.rendered || {};
      _text('tpl-preview-subject', rendered.subject || '—');
      
      const ch = _val('tpl-edit-channel');
      if (ch === 'email' && rendered.body_html) {
        const iframe = document.getElementById('tpl-preview-iframe');
        const autoResize = () => {
          try {
            if (iframe.contentWindow && iframe.contentWindow.document && iframe.contentWindow.document.body) {
              const body = iframe.contentWindow.document.body;
              const html = iframe.contentWindow.document.documentElement;
              const h = Math.max(body.scrollHeight, body.offsetHeight, html.clientHeight, html.scrollHeight, html.offsetHeight);
              if (h > 50) iframe.style.height = (h + 5) + 'px';
            }
          } catch(e) {}
        };
        iframe.onload = () => {
          autoResize();
          try { new ResizeObserver(autoResize).observe(iframe.contentWindow.document.body); } catch(e) {}
        };
        iframe.style.display = '';
        document.getElementById('tpl-preview-text').style.display = 'none';
        iframe.srcdoc = rendered.body_html;
        setTimeout(autoResize, 50);
        setTimeout(autoResize, 300);
        setTimeout(autoResize, 1000);
      } else {
        document.getElementById('tpl-preview-iframe').style.display = 'none';
        const pre = document.getElementById('tpl-preview-text');
        pre.style.display = '';
        pre.textContent = rendered.body_text || rendered.body_html || '';
      }
    },
  };

  /* Expose globally */
  window.TemplateManager = TM;

  /* ── utility functions ───────────────────────────────────────────── */
  window.tplShowConfirm = function(msg, btnText = 'Confirm') {
    return new Promise(resolve => {
      let overlay = document.getElementById('tpl-hecos-confirm-modal');
      if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'tpl-hecos-confirm-modal';
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);z-index:99999;display:flex;align-items:center;justify-content:center;opacity:0;transition:opacity 0.2s;';
        overlay.innerHTML = `
          <div style="background:var(--bg2,#1e1e1e);border:1px solid var(--border,#333);border-radius:12px;padding:24px;max-width:400px;text-align:center;box-shadow:0 10px 30px rgba(0,0,0,0.5);transform:translateY(20px);transition:transform 0.3s;">
              <h2 style="margin-top:0;font-size:1.4em;color:var(--text);"><i class="fas fa-exclamation-triangle" style="color:#ff4a4a;margin-right:8px;"></i>Confirm</h2>
              <p id="tpl-confirm-msg" style="margin:20px 0;color:var(--text);font-size:1.05em;"></p>
              <div style="display:flex;justify-content:center;gap:15px;margin-top:24px;">
                  <button type="button" class="btn btn-secondary" id="tpl-confirm-cancel">Cancel</button>
                  <button type="button" class="btn btn-danger" style="background:#ff4a4a;color:white;border:none;" id="tpl-confirm-btn"></button>
              </div>
          </div>`;
        document.body.appendChild(overlay);
      }
      
      document.getElementById('tpl-confirm-msg').innerHTML = msg;
      const obtn = document.getElementById('tpl-confirm-btn');
      obtn.textContent = btnText;
      const cbtn = document.getElementById('tpl-confirm-cancel');
      
      const cleanup = () => {
        overlay.style.opacity = '0';
        setTimeout(() => overlay.style.display = 'none', 200);
        obtn.onclick = null;
        cbtn.onclick = null;
      };
      
      cbtn.onclick = () => { cleanup(); resolve(false); };
      obtn.onclick = () => { cleanup(); resolve(true); };
      
      overlay.style.display = 'flex';
      setTimeout(() => { 
        overlay.style.opacity = '1'; 
        overlay.querySelector('div').style.transform = 'translateY(0)'; 
      }, 10);
    });
  };

  window.tplSwitchTab = function(btn, targetId) {
    const tabs = btn.closest('.tpl-tabs');
    if (tabs) tabs.querySelectorAll('.tpl-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    const editor = document.getElementById('tpl-editor-section');
    if (editor) editor.querySelectorAll('.tpl-tab-pane').forEach(p => {
      p.style.display = p.id === targetId ? '' : 'none';
      p.classList.toggle('active', p.id === targetId);
    });
    if (targetId === 'tpl-tab-preview') {
      window.TemplateManager.previewRender();
    }
  };

  window.tplUpdateCharCount = function(ta) {
    const countEl = ta.closest('.tpl-textarea-wrap')?.querySelector('.tpl-char-num');
    if (countEl) countEl.textContent = ta.value.length;
    // Auto-detect variables
    const matches = ta.value.match(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g) || [];
    const vars = [...new Set(matches.map(m => m.replace(/\{\{\s*|\s*\}\}/g, '')))];
    const list = document.getElementById('tpl-variables-list');
    if (list) {
      list.innerHTML = vars.length
        ? vars.map(v => `<span class="tpl-var-chip" onclick="tplInsertVar('${v}')"><i class="fas fa-code"></i>${v}</span>`).join('')
        : '<span style="opacity:.5;font-size:.75rem">No variables detected</span>';
    }
  };

  window.tplInsertVar = function(v) {
    const active = document.activeElement;
    const snippet = '{{ ' + v + ' }}';
    if (active && active.tagName === 'TEXTAREA') {
      const s = active.selectionStart, e = active.selectionEnd;
      active.value = active.value.slice(0,s) + snippet + active.value.slice(e);
      active.selectionStart = active.selectionEnd = s + snippet.length;
    } else {
      navigator.clipboard && navigator.clipboard.writeText(snippet);
      window.showToast && window.showToast('Copied to clipboard: ' + snippet, 'info');
    }
  };

  /* ── Auto-init via MutationObserver ─────────────────────────────── */
  // The panel is injected dynamically — DOMContentLoaded fires too early.
  // We watch for the templates panel to appear, then call TM.init().
  let _tplInitDone = false;

  function _tryInit() {
    if (_tplInitDone) return;
    const panel = document.getElementById('tab-templates');
    if (!panel) return;
    // Only init if the panel is actually visible
    if (panel.offsetParent === null && panel.style.display === 'none') return;
    _tplInitDone = true;
    console.log('[TEMPLATES] Panel ready — initializing TemplateManager');
    TM.init();
  }

  // Also hook into tab click events on the sidebar nav
  function _hookTabClick() {
    // Hecos uses data-target or similar for tab switching
    document.addEventListener('click', function(e) {
      const btn = e.target.closest('[data-target="templates"], [href="#templates"], [onclick*="templates"]');
      if (btn) {
        setTimeout(() => {
          _tplInitDone = false; // allow re-init on tab switch
          _tryInit();
        }, 150);
      }
    });
  }

  const _observer = new MutationObserver(() => {
    _tryInit();
  });
  _observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });

  _hookTabClick();
  // Try immediately in case panel already exists
  _tryInit();

})();
