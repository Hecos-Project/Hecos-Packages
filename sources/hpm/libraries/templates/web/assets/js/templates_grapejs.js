/**
 * Hecos Template Manager — GrapeJS Logic
 * ================================================
 */

window.TemplateManager = window.TemplateManager || {};

Object.assign(window.TemplateManager, {

  _destroyGrapeJS() {
    if (this._grapeEditor) {
      try { this._grapeEditor.destroy(); } catch (_) {}
      this._grapeEditor = null;
    }
    ['tpl-grapes-container', 'tpl-grapes-blocks', 'tpl-grapes-styles', 'tpl-grapes-traits'].forEach(id => {
      const el = this.$(id);
      if (el) el.innerHTML = '';
    });
  },

  _initGrapeJS(pendingHtml) {
    if (typeof grapesjs === 'undefined') {
      console.warn('[Templates] GrapeJS not yet loaded, retrying…');
      setTimeout(() => this._initGrapeJS(pendingHtml), 300);
      return;
    }

    this._destroyGrapeJS();

    const loadingEl = this.$('tpl-grapes-loading');
    if (loadingEl) loadingEl.style.display = 'none';

    this._grapeEditor = grapesjs.init({
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

      canvasCss: `
        body { margin: 0; padding: 20px; background: #f4f4f4; font-family: sans-serif; }
        [data-gjs-type] { outline: 1px dashed transparent; transition: outline .15s; }
        [data-gjs-type]:hover { outline: 1px dashed rgba(0,212,255,0.5); }
      `,
    });

    this._grapeEditor.on('change:changesCount', () => { this._dirty = true; });

    this._grapeEditor.on('load', () => {
      const html = pendingHtml || window._tplPendingHtml || '';
      setTimeout(() => {
        if (html) {
          this._grapeEditor.setComponents(html);
        } else {
          this._grapeEditor.setComponents(this._defaultEmailTemplate());
        }
        delete window._tplPendingHtml;
        setTimeout(() => { this._dirty = false; }, 200);
      }, 80);
    });
  },

  _defaultEmailTemplate() {
    return `
<table class="email-wrapper" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f4; padding:20px;">
  <tr><td align="center">
    <!-- ── HEADER ── -->
    <table class="email-header" width="600" cellpadding="0" cellspacing="0"
           style="background:#ffffff; border:2px dashed #00d4ff; border-radius:8px; margin-bottom:16px;">
      <tr><td style="padding:16px; text-align:center; font-family:sans-serif;">
        <p style="margin:0; color:#9ca3af; font-size:11px; text-transform:uppercase; letter-spacing:.1em;">Header</p>
        <h2 style="margin:12px 0 0; color:#1f2937; font-size:22px;">Company Name</h2>
      </td></tr>
    </table>
    <!-- ── BODY ── -->
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
    <!-- ── FOOTER ── -->
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
  },

  _setEmailBody(html) {
    if (this._grapeEditor) {
      this._grapeEditor.setComponents(html || this._defaultEmailTemplate());
    } else {
      window._tplPendingHtml = html;
    }
  },

  _getEmailBody() {
    if (this._grapeEditor) {
      try { 
        const html = this._grapeEditor.getHtml();
        const css = this._grapeEditor.getCss();
        return html + (css ? `<style>${css}</style>` : ''); 
      }
      catch { return ''; }
    }
    return '';
  }

});
