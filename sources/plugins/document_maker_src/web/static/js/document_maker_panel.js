/**
 * document_maker — Plugin Panel JS
 * Auto-save on change (debounced 600ms). No manual save button.
 * Also hooks into Hecos global saveConfig() so the hub footer Save button works too.
 */

// Default override directive text
const DOCS_DEFAULT_OVERRIDE = `IMPORTANT RULES FOR DOCUMENT GENERATION:

1. RESPONSE FORMAT: After generating the file, DO NOT output raw HTML code or duplicate images/links in your chat response. The UI automatically renders a rich preview and file card. Just provide a brief confirmation message with the file path.

2. FORMATTING: When creating HTML documents, ALWAYS include complete CSS styling:
   - Use @page { size: A4; margin: 0; } for PDF pagination control.
   - Set body { margin: 0; padding: 20mm; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt; line-height: 1.6; color: #222; } as default.
   - Use * { box-sizing: border-box; } to prevent layout overflow.
   - For multi-page documents, use CSS page-break-before/after to control pagination.
   - All content must fit within A4 dimensions (210mm x 297mm).

3. IMAGES: Previously generated images are stored in media/images/. Use <img src="/api/images/FILENAME"> to include them. If the user asks to reuse existing images, do NOT generate new ones — just reference the filenames directly. Only call IMAGE_GEN if the user explicitly asks for NEW images.

4. WORKFLOW: Always call DOCS__generate_pdf to produce the final document. Never stop after generating images without producing the document.`;


// ── Autosave debouncer ────────────────────────────────────────────────────────
let _docsSaveTimer = null;

window.docsDebounceSave = function() {
    clearTimeout(_docsSaveTimer);
    _docsSaveTimer = setTimeout(() => { window.saveDocsConfig(); }, 600);
};

// ── Load config ────────────────────────────────────────────────────────────────
window.loadDocsConfig = async function() {
    try {
        const res = await fetch('/hecos/api/plugins/document_maker/config');
        if (!res.ok) return;
        const data = await res.json();
        const pathEl = document.getElementById('docs-pdf-save-path');
        if (pathEl) pathEl.value = data.pdf_save_path || 'media/documents';

        const enabledEl = document.getElementById('docs-override-enabled');
        if (enabledEl) enabledEl.checked = data.override_enabled !== false; // default true

        const htmlEl = document.getElementById('docs-generate-html');
        if (htmlEl) htmlEl.checked = data.generate_html !== false; // default true

        const pdfEl = document.getElementById('docs-generate-pdf');
        if (pdfEl) pdfEl.checked = data.generate_pdf !== false; // default true

        const directiveEl = document.getElementById('docs-override-generate-pdf');
        if (directiveEl) {
            // If override_directive is missing (first load), populate with the default
            directiveEl.value = (data.override_directive !== undefined)
                ? data.override_directive
                : DOCS_DEFAULT_OVERRIDE;
        }
    } catch(e) {
        console.warn('[DocsMaker] Failed to load config:', e);
    }
};

// ── Save config ────────────────────────────────────────────────────────────────
window.saveDocsConfig = async function(silent = false) {
    const pathEl = document.getElementById('docs-pdf-save-path');
    if (!pathEl) return;

    const enabledEl = document.getElementById('docs-override-enabled');
    const htmlEl = document.getElementById('docs-generate-html');
    const pdfEl = document.getElementById('docs-generate-pdf');
    const directiveEl = document.getElementById('docs-override-generate-pdf');

    const payload = {
        pdf_save_path: pathEl.value.trim() || 'media/documents',
        override_enabled: enabledEl ? enabledEl.checked : true,
        generate_html: htmlEl ? htmlEl.checked : true,
        generate_pdf: pdfEl ? pdfEl.checked : true,
        override_directive: directiveEl ? directiveEl.value.trim() : DOCS_DEFAULT_OVERRIDE
    };

    try {
        const res = await fetch('/hecos/api/plugins/document_maker/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok && !silent) {
            const statusEl = document.getElementById('docs-save-status');
            if (statusEl) {
                statusEl.style.display = 'flex';
                clearTimeout(window._docsSaveStatusTimer);
                window._docsSaveStatusTimer = setTimeout(() => {
                    statusEl.style.display = 'none';
                }, 2500);
            }
        }
    } catch(e) {
        console.error('[DocsMaker] Save error:', e);
        if (window.showToast) window.showToast('Document Maker: failed to save settings', 'error');
    }
};

// ── Hook into Hecos Central Hub global save button ─────────────────────────────
// The hub footer "Save" button calls window.saveConfig() globally.
// We wrap it to also save our plugin config.
(function() {
    const _origSaveConfig = window.saveConfig;
    window.saveConfig = async function(...args) {
        await window.saveDocsConfig(true);
        if (typeof _origSaveConfig === 'function') return _origSaveConfig(...args);
    };
})();

// ── Init on panel load ────────────────────────────────────────────────────────
(function init() {
    if (document.getElementById('docs-pdf-save-path')) {
        window.loadDocsConfig();
    } else {
        // Panel might be lazy-loaded — wait for DOM
        document.addEventListener('DOMContentLoaded', () => {
            if (document.getElementById('docs-pdf-save-path')) window.loadDocsConfig();
        });
    }
})();
