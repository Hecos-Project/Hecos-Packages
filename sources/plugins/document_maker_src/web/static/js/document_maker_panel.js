/**
 * document_maker — Plugin Panel JS
 * Auto-save on change (debounced 600ms). No manual save button.
 * Also hooks into Hecos global saveConfig() so the hub footer Save button works too.
 */

// Default override directive text
const DOCS_DEFAULT_OVERRIDE = `CRITICAL RULES FOR DOCUMENT GENERATION (READ CAREFULLY BEFORE GENERATING):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. RESPONSE FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
After generating the file, DO NOT output raw HTML or duplicate images/links in the chat. Just confirm with a brief message and the file path.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. PAGE STRUCTURE — MANDATORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Wrap EVERY page in: <div class="page">...</div>
- Each .page div MUST be exactly one A4 page worth of content — never more.
- CSS: .page { page-break-after: always; width: 210mm; min-height: 297mm; max-height: 297mm; overflow: hidden; padding: 20mm; box-sizing: border-box; }
- ALWAYS include: @page { size: A4; margin: 0; } body { margin: 0; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt; line-height: 1.6; color: #222; } * { box-sizing: border-box; }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. TEXT LENGTH LIMITS PER PAGE (A4, 11pt, padding 20mm)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Usable area per page: 170mm × 257mm.
- Full text page (no images): MAX 2500 characters
- Page with 1 full-width image (height ~80mm): MAX 1200 characters of text
- Page with 2 side-by-side images: MAX 800 characters of text
- Page with a title/cover: MAX 400 characters of body text
- NEVER put more text than the limits above — it will overflow into the next page and break the PDF layout.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. IMAGE SIZING RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Full-width image: max-height: 180mm; width: 100%; object-fit: cover;
- Half-width image: max-height: 130mm; width: 48%; object-fit: cover;
- ALWAYS add: page-break-inside: avoid; on every image container div.
- NEVER let an image bleed across a page boundary.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5. ANTI-BREAK RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Add to CSS: h1, h2, h3 { page-break-after: avoid; } .photo-card, .photo-grid, .gallery, .card { page-break-inside: avoid; }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
6. IMAGES IN DOCUMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use <img src="/api/images/FILENAME"> for generated images. Do NOT generate new images if the user asks to reuse existing ones.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
7. WORKFLOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Always call DOCS__generate_pdf to finalize. Never stop after images without producing the document.`;


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
