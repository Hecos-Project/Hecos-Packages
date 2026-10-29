/**
 * document_maker — Plugin Panel JS
 * Auto-save on change (debounced 600ms).
 * Live Interactive Template Preview + Dynamic Photo Count selector.
 * Also hooks into Hecos global saveConfig() so the hub footer Save button works too.
 */

// Default override directive text
const DOCS_DEFAULT_OVERRIDE = `CRITICAL RULES & OPERATIONAL RECIPE FOR DOCUMENT GENERATION (READ CAREFULLY):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. RECIPE & WORKFLOW FOR DOCUMENTS (MANDATORY SEQUENCE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When creating a document that requires illustrations or photos (e.g. "Ecos News", magazines, fotoromanzi, articles, illustrated reports):

• PHASE 1: GENERATE IMAGES FIRST (MATCHING USER-REQUESTED COUNT)
  1. If the user specifies a photo count (e.g. "con 2 foto", "con 6 foto", "metti 8 foto", "fanne 12", "mettimi 20 foto"), call IMAGE_GEN__generate_image exactly N times before calling the document generator.
  2. Storage & Paths: Generated photos are automatically saved in media/images/ and served via /api/images/FILENAME.png.
  3. Image Aliases: You can reference generated images either by their exact filename or by sequential aliases: /api/images/image_1.png, /api/images/image_2.png, ... /api/images/image_N.png. Document Maker automatically maps these aliases in order to the newly generated photos.
  4. DO NOT stop after generating images! You must immediately continue to Phase 2 to produce the final document.

• PHASE 2: CALL DOCS__generate_pdf
  Choose the correct mode below:

  [MODE A: TEMPLATE MODE — DEFAULT & STRONGLY PREFERRED]
  Use this whenever a template is requested (e.g. "segui il template di default", "fotoromanzo", "rivista", "report"), or by default.
  - Pass template_id: The template ID or name (or "default" for the configured default template).
  - Pass template_vars: A JSON string containing ALL required template variables populated with rich, realistic content.
    * Dynamic Photo Count: Pass img1..imgN and caption1..captionN for however many photos were requested/generated! Document Maker automatically scales the gallery grid and paginates across pages.
    * For image variables (e.g. img1, img2...): Pass the image path or alias string (e.g. "/api/images/image_1.png" or "/api/images/FILENAME.png").
    * For rich text variables (e.g. editorial_intro, section1_body): You can embed inline images using <img src="/api/images/image_1.png">.
  - CRITICAL: DO NOT provide html_content when using a template! Keep html_content empty so the template engine formats the document.

  [MODE B: FREEFORM HTML MODE — ONLY FOR CUSTOM RAW HTML]
  Use this ONLY when the user explicitly requests a 100% custom HTML layout from scratch without any template.
  - Provide html_content containing the complete HTML structure.
  - DO NOT provide template_id or template_vars.
  - Wrap pages in <div class="page">...</div>. Full text max 2500 chars/page; with 1 image max 1200 chars. Images: max-height: 180mm, width: 100%, object-fit: cover, page-break-inside: avoid.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. RESPONSE FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
After generating the document, DO NOT output raw HTML, long code blocks, or duplicate images in the chat. Confirm with a brief, friendly summary and provide the file path / link of the generated PDF/HTML.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. AVAILABLE PRE-DESIGNED TEMPLATES & VARIANTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- "Fotoromanzo Classico — 2 Foto (Dittico)" (ID: 00000000-0000-0000-0000-000000000012): 2 story photo panels + narrative captions.
- "Fotoromanzo Classico — 4 Foto" (ID: 00000000-0000-0000-0000-000000000010): 4 story photo panels + narrative captions (Standard).
- "Fotoromanzo Classico — 6 Foto" (ID: 00000000-0000-0000-0000-000000000013): 6 story photo panels + narrative captions (Racconto Esteso).
- "Rivista Glamour — 2 Foto (Cover & Hero)" (ID: 00000000-0000-0000-0000-000000000015): 2 maxi photo layouts + 2-col text.
- "Rivista Glamour — 4 Foto (Editoriale)" (ID: 00000000-0000-0000-0000-000000000016): Hero photo + 3 grid photos with captions.
- "Rivista Glamour — 6 Foto" (ID: 00000000-0000-0000-0000-000000000011): Hero photo + 5 grid photos, captions, editorial intro, closing.
- "Portfolio Fotografico — Dark Gallery" (ID: doc-portfolio-dark-001): Dark luxury photography showcase.
- "Quotidiano Storico — Vintage Broadsheet" (ID: doc-newspaper-vintage-001): Classic newspaper with masthead, news columns and vintage photo cards.
- "Executive Report Dark Premium" (ID: doc-report-executive-001): Corporate dark theme with 4 KPI cards and sections.
- "Report Editoriale Clean Light" (ID: doc-report-editorial-001): Multi-section editorial report with author bio, abstract, drop caps.
- "Lettera Formale" (ID: doc-letter-formal-001): Formal letterhead, date, subject, salutation, body and closing.
- "Fattura / Ricevuta Premium" (ID: doc-invoice-premium-001): Structured invoice with line items, tax and totals.`;


// ── Built-in Document Templates (guaranteed fallback) ────────────────────────
const DEFAULT_BUILTIN_DOC_TEMPLATES = [
    {
        id: "00000000-0000-0000-0000-000000000010",
        name: "Fotoromanzo Classico — 4 Foto con Didascalia",
        channel: "document",
        description: "Classic photo-novel layout with 4 photographic panels and narrative dialog blocks.",
        variables: ["title", "subtitle", "description", "img1", "img2", "img3", "img4", "caption1", "caption2", "caption3", "caption4", "footer_text"]
    },
    {
        id: "00000000-0000-0000-0000-000000000012",
        name: "Fotoromanzo Classico — 2 Foto (Dittico)",
        channel: "document",
        description: "Two-panel narrative photo story with large visual focus and dialog blocks.",
        variables: ["title", "subtitle", "description", "img1", "img2", "caption1", "caption2", "footer_text"]
    },
    {
        id: "00000000-0000-0000-0000-000000000013",
        name: "Fotoromanzo Classico — 6 Foto (Racconto Esteso)",
        channel: "document",
        description: "Extended six-panel photo story with auto multi-page layout and narrative captions.",
        variables: ["title", "subtitle", "description", "img1", "img2", "img3", "img4", "img5", "img6", "caption1", "caption2", "caption3", "caption4", "caption5", "caption6", "footer_text"]
    },
    {
        id: "00000000-0000-0000-0000-000000000011",
        name: "Rivista Glamour — 6 Foto Editoriale",
        channel: "document",
        description: "Editorial magazine layout featuring hero photo + 5 grid photos with captions, author credits, and intro text.",
        variables: ["title", "subtitle", "editorial_intro", "img1", "img2", "img3", "img4", "img5", "img6", "caption1", "caption2", "caption3", "caption4", "caption5", "caption6", "author_name", "closing_text"]
    },
    {
        id: "00000000-0000-0000-0000-000000000015",
        name: "Rivista Glamour — 2 Foto (Cover & Hero)",
        channel: "document",
        description: "High-impact magazine layout with 2 full-sized editorial photos and two-column article text.",
        variables: ["title", "subtitle", "editorial_intro", "img1", "img2", "caption1", "caption2", "author_name", "closing_text"]
    },
    {
        id: "00000000-0000-0000-0000-000000000016",
        name: "Rivista Glamour — 4 Foto (Editoriale Compatto)",
        channel: "document",
        description: "Hero cover photo + 3 grid photos with author credits and editorial introduction.",
        variables: ["title", "subtitle", "editorial_intro", "img1", "img2", "img3", "img4", "caption1", "caption2", "caption3", "caption4", "author_name", "closing_text"]
    },
    {
        id: "doc-portfolio-dark-001",
        name: "Portfolio Fotografico — Dark Gallery",
        channel: "document",
        description: "Dark luxury photography portfolio showcasing full bleed image cards and artist statement.",
        variables: ["title", "subtitle", "artist_statement", "img1", "img2", "img3", "img4", "caption1", "caption2", "caption3", "caption4", "artist_name", "footer_text"]
    },
    {
        id: "doc-newspaper-vintage-001",
        name: "Quotidiano Storico — Vintage Broadsheet",
        channel: "document",
        description: "Authentic historical newspaper broadsheet with masthead, news columns, and vintage photos.",
        variables: ["newspaper_name", "issue_date", "headline", "subheadline", "article_lead", "article_body", "img1", "img2", "caption1", "caption2", "editorial_opinion", "footer_text"]
    },
    {
        id: "doc-report-executive-001",
        name: "Executive Report — Dark Premium",
        channel: "document",
        description: "Corporate dark theme report with executive summary and 4 key KPI metric cards.",
        variables: ["company", "report_title", "report_date", "author", "executive_summary", "kpi1_label", "kpi1_value", "kpi2_label", "kpi2_value", "kpi3_label", "kpi3_value", "kpi4_label", "kpi4_value", "section1_title", "section1_content", "section2_title", "section2_content", "footer_text"]
    },
    {
        id: "doc-report-editorial-001",
        name: "Editorial Report — Clean Light",
        channel: "document",
        description: "Structured multi-section report with light aesthetic, abstract, and author info.",
        variables: ["title", "subtitle", "category", "date", "author_name", "author_bio", "abstract", "section1_title", "section1_body", "section2_title", "section2_body", "section3_title", "section3_body", "conclusion", "footer_text"]
    },
    {
        id: "doc-letter-formal-001",
        name: "Formal Letter — Letterhead",
        channel: "document",
        description: "Corporate letterhead layout with sender details, recipient info, and formal closing.",
        variables: ["company_name", "company_address", "company_email", "company_phone", "recipient_name", "recipient_title", "recipient_company", "recipient_address", "city", "date", "reference", "subject", "salutation", "body_paragraph1", "body_paragraph2", "body_paragraph3", "closing", "sender_name", "sender_title"]
    },
    {
        id: "doc-invoice-premium-001",
        name: "Invoice / Receipt — Premium",
        channel: "document",
        description: "Commercial invoice with line items, tax breakdown, and banking payment info.",
        variables: ["company_name", "company_address", "company_vat", "company_email", "client_name", "client_address", "client_vat", "invoice_number", "invoice_date", "due_date", "item1_desc", "item1_qty", "item1_price", "item2_desc", "item2_qty", "item2_price", "item3_desc", "item3_qty", "item3_price", "subtotal", "tax_rate", "tax_amount", "total", "notes", "bank_details"]
    }
];

// ── Template list state & handlers ───────────────────────────────────────────
window._docsTemplatesList = [];
window._docsSavedDefaultTemplateId = "";

window.docsFetchTemplates = async function(manualToast = false) {
    let fetched = [];
    try {
        // Attempt 1: templates library direct endpoint
        let res = await fetch('/api/templates/?channel=document');
        if (res.ok) {
            const data = await res.json();
            if (data.ok && Array.isArray(data.templates) && data.templates.length > 0) {
                fetched = data.templates;
            }
        }
        // Attempt 2: document_maker plugin route
        if (fetched.length === 0) {
            res = await fetch('/hecos/api/plugins/document_maker/templates');
            if (res.ok) {
                const data = await res.json();
                if (data.ok && Array.isArray(data.templates) && data.templates.length > 0) {
                    fetched = data.templates;
                }
            }
        }
    } catch(e) {
        console.warn('[DocsMaker] API fetch templates failed, using built-ins:', e);
    }

    // Merge or fallback to built-ins if API returned empty
    let templates = [...fetched];
    if (templates.length === 0) {
        templates = [...DEFAULT_BUILTIN_DOC_TEMPLATES];
    } else {
        DEFAULT_BUILTIN_DOC_TEMPLATES.forEach(builtin => {
            if (!templates.some(t => t.id === builtin.id)) {
                templates.push(builtin);
            }
        });
    }

    window._docsTemplatesList = templates;

    const sel = document.getElementById('docs-default-template');
    if (sel) {
        const currentVal = window._docsSavedDefaultTemplateId || sel.value || "";
        sel.innerHTML = '<option value="">-- No Default Template (Freeform HTML / Generative AI) --</option>';

        templates.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = `${t.name} [${(t.channel || 'document').toUpperCase()}]`;
            sel.appendChild(opt);
        });

        sel.value = currentVal;
        window.docsOnTemplateChange(false);
    }

    if (manualToast) {
        const msg = `Templates list updated (${templates.length} available)`;
        if (window.showToast) window.showToast(msg, 'success');
        else if (typeof toast === 'function') toast('success', msg);
    }
};

window.docsOnTemplateChange = function(triggerSave = true) {
    const sel = document.getElementById('docs-default-template');
    if (!sel) return;
    const tplId = sel.value;
    const editBtn = document.getElementById('docs-btn-edit-tpl');
    const infoBox = document.getElementById('docs-template-info');
    const previewCard = document.getElementById('docs-template-preview-card');

    if (editBtn) editBtn.disabled = !tplId;

    if (!tplId) {
        if (infoBox) infoBox.style.display = 'none';
        if (previewCard) previewCard.style.display = 'none';
    } else {
        const tpl = (window._docsTemplatesList || []).find(t => t.id === tplId);
        if (tpl && infoBox) {
            infoBox.style.display = 'block';
            const nameEl = document.getElementById('docs-tpl-info-name');
            const idEl = document.getElementById('docs-tpl-info-id');
            const descEl = document.getElementById('docs-tpl-info-desc');
            const varsEl = document.getElementById('docs-tpl-info-vars');

            if (nameEl) nameEl.textContent = tpl.name || 'Template';
            if (idEl) idEl.textContent = `ID: ${tpl.id}`;
            if (descEl) descEl.textContent = tpl.description || 'No description available.';

            if (varsEl) {
                const vars = tpl.variables || [];
                if (vars.length > 0) {
                    varsEl.innerHTML = vars.map(v => 
                        `<span style="background:var(--bg3); padding:2px 8px; border-radius:12px; font-size:10px; border:1px solid var(--border); color:var(--text); font-family:monospace;">{{ ${v} }}</span>`
                    ).join('');
                } else {
                    varsEl.innerHTML = '<span style="font-size:11px; color:var(--muted); font-style:italic;">No dynamic variables required.</span>';
                }
            }

            // Render live visual preview
            window.docsRenderTemplatePreview();
        }
    }

    if (triggerSave) {
        window.docsDebounceSave();
    }
};

// ── Live Interactive Template Preview Renderer ────────────────────────────────
window.docsRenderTemplatePreview = async function(forceRefresh = false) {
    const sel = document.getElementById('docs-default-template');
    if (!sel || !sel.value) {
        const previewCard = document.getElementById('docs-template-preview-card');
        if (previewCard) previewCard.style.display = 'none';
        return;
    }
    const tplId = sel.value;
    const previewCard = document.getElementById('docs-template-preview-card');
    const iframe = document.getElementById('docs-preview-iframe');
    const modalIframe = document.getElementById('docs-modal-preview-iframe');
    const loading = document.getElementById('docs-preview-loading');
    const badge = document.getElementById('docs-preview-badge');

    if (previewCard) previewCard.style.display = 'block';
    if (loading) loading.style.display = 'flex';

    try {
        let tpl = (window._docsTemplatesList || []).find(t => t.id === tplId);
        // Fetch full template with body_html if missing
        if (!tpl || !tpl.body_html) {
            try {
                const res = await fetch('/api/templates/' + tplId);
                if (res.ok) {
                    const data = await res.json();
                    if (data.ok && data.template) {
                        tpl = { ...(tpl || {}), ...data.template };
                        // Update in cache
                        const idx = (window._docsTemplatesList || []).findIndex(t => t.id === tplId);
                        if (idx >= 0) window._docsTemplatesList[idx] = tpl;
                    }
                }
            } catch(e) {
                console.warn('[DocsMaker] Fetch template detail failed:', e);
            }
        }

        if (!tpl || !tpl.body_html) {
            if (loading) loading.style.display = 'none';
            return;
        }

        const photoCountEl = document.getElementById('docs-default-photo-count');
        const photoCount = photoCountEl ? (parseInt(photoCountEl.value) || 0) : 0;

        // High-resolution thematic stock photos
        const samplePhotos = [
            "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&q=80", // Space / Nebula
            "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=800&q=80", // Fashion Model
            "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=800&q=80", // Lake & Mountain
            "https://images.unsplash.com/photo-1519741497674-611481863552?w=800&q=80", // Story Scene
            "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=800&q=80", // Space Station
            "https://images.unsplash.com/photo-1469474968028-56623f02e42e?w=800&q=80", // Forest light
            "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800&q=80", // Golden Beach
            "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=800&q=80", // Misty peaks
            "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=800&q=80", // Green rays
            "https://images.unsplash.com/photo-1516339901601-2e1b62dc0c45?w=800&q=80", // Starry sky
            "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=800&q=80", // Concept art
            "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800&q=80"  // Deep tech
        ];

        const roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"];

        let sampleVars = {
            title: tpl.name.replace(/—.*$/, '').replace(/–.*$/, '').trim() || "Documento Illustrato",
            subtitle: "Edizione Speciale & Anteprima di Layout",
            description: "Un'esplorazione dettagliata della composizione grafica con testi editoriali, contrasti bilanciati e resa fotografica ad alta fedeltà.",
            author_name: "Antonio Meloni",
            author: "Antonio Meloni",
            company: "HECOS INNOVATION LABS",
            company_name: "HECOS INNOVATION LABS",
            report_title: "Executive Strategic Report 2026",
            report_date: "Ottobre 2026",
            executive_summary: "Crescita costante registrata in tutti i settori dell'ecosistema, con un incremento del 38% nelle automazioni e una perfetta stabilizzazione dei servizi.",
            kpi1_label: "Fatturato Netto", kpi1_value: "€ 4.2M",
            kpi2_label: "Utenti Attivi", kpi2_value: "148K",
            kpi3_label: "Uptime Globale", kpi3_value: "99.98%",
            kpi4_label: "Soddisfazione", kpi4_value: "4.9/5",
            section1_title: "Espansione Architetturale",
            section1_content: "La convergenza dei moduli di generazione documentale e sintesi vocale ha raggiunto il massimo livello di affidabilità operativa.",
            section2_title: "Proiezioni Prossimo Trimestre",
            section2_content: "L'adozione di template dinamici consente la generazione istantanea di photobook e report personalizzati su scala industriale.",
            editorial_intro: "Nel cuore della nuova frontiera tecnologica, la bellezza dell'immagine incontra la precisione del codice. Questo numero speciale celebra l'armonia delle forme e l'eleganza compositiva.",
            closing_text: "Un ringraziamento speciale a tutti i lettori e collaboratori che hanno reso possibile questa straordinaria pubblicazione.",
            footer_text: "Edizione Speciale Hecos · Tutti i diritti riservati · Vietata la riproduzione non autorizzata.",
            artist_statement: "L'arte della visione risiede nell'equilibrio sottile tra luce, ombra e silenzio.",
            artist_name: "Antonio Meloni Studio",
            newspaper_name: "La Gazzetta di Hecos",
            issue_date: "Mercoledì, 28 Ottobre 2026",
            headline: "RIVOLUZIONE DOCUMENTALE: IL MOTORE DINAMICO È REALTÀ",
            subheadline: "Nuova era per l'editoria digitale con impaginazione fluida da 2 a 20 immagini",
            article_lead: "Oggi segna una svolta fondamentale nei sistemi di composizione automatica: il nuovo motore intelligente consente l'adattamento immediato a qualsiasi numero di scatti fotografici.",
            article_body: "Grazie alla sincronizzazione perfetta dei margini e delle didascalie narrative, ogni documento viene stampato e renderizzato con standard tipografici di altissimo profilo.",
            editorial_opinion: "L'innovazione autentica non si limita alla velocità, ma risiede nella cura maniacale di ogni singolo dettaglio visivo."
        };

        // Populate 20 image slots and captions
        for (let i = 1; i <= 20; i++) {
            sampleVars[`img${i}`] = samplePhotos[(i - 1) % samplePhotos.length];
            sampleVars[`caption${i}`] = `Scena ${roman[i - 1] || i}: Rappresentazione fotografica ad alta fedeltà della composizione visiva.`;
        }

        // Interpolate variables
        let html = tpl.body_html;
        Object.keys(sampleVars).forEach(k => {
            const re = new RegExp(`\\{\\{\\s*${k}\\s*\\}\\}`, 'g');
            html = html.replace(re, sampleVars[k]);
        });

        // Dynamic photo grid adaptation if photoCount is explicitly chosen
        if (photoCount > 0) {
            try {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const gallery = doc.querySelector('.gallery, .photo-grid, .grid');
                if (gallery) {
                    const cards = Array.from(gallery.querySelectorAll('.photo-card, .grid-item, .card'));
                    if (cards.length > 0) {
                        const blueprint = cards[0];
                        if (photoCount < cards.length) {
                            for (let c = photoCount; c < cards.length; c++) cards[c].remove();
                        } else if (photoCount > cards.length) {
                            for (let c = cards.length; c < photoCount; c++) {
                                const clone = blueprint.cloneNode(true);
                                const img = clone.querySelector('img');
                                if (img) img.src = samplePhotos[c % samplePhotos.length];
                                const cap = clone.querySelector('.caption, .item-caption, p');
                                if (cap) {
                                    const span = cap.querySelector('.scene-num, strong, span');
                                    if (span) span.textContent = `Scena ${roman[c] || (c + 1)}`;
                                    cap.innerHTML = (span ? span.outerHTML + ' ' : '') + `Composizione artistica #${c + 1}`;
                                }
                                gallery.appendChild(clone);
                            }
                        }
                    }
                }
                html = doc.documentElement.outerHTML;
            } catch(e) {
                console.warn('[DocsMaker] DOMParser gallery adaptation failed:', e);
            }
        }

        // Smooth scrollbar styling inside preview iframe
        const previewFix = `
            <style>
                html { overflow-y: auto !important; }
                ::-webkit-scrollbar { width: 6px; height: 6px; }
                ::-webkit-scrollbar-track { background: rgba(0,0,0,0.15); }
                ::-webkit-scrollbar-thumb { background: rgba(120,120,150,0.45); border-radius: 4px; }
            </style>
        `;
        if (html.includes('</head>')) {
            html = html.replace('</head>', previewFix + '</head>');
        } else {
            html = previewFix + html;
        }

        if (iframe) iframe.srcdoc = html;
        if (modalIframe) modalIframe.srcdoc = html;

        if (badge) {
            badge.textContent = photoCount > 0 ? `${photoCount} FOTO` : 'AUTO FOTO';
        }

    } catch(err) {
        console.error('[DocsMaker] Error rendering template preview:', err);
    } finally {
        if (loading) loading.style.display = 'none';
    }
};

window.docsOpenFullscreenPreview = function() {
    const modal = document.getElementById('docs-preview-modal');
    const sel = document.getElementById('docs-default-template');
    const modalTitle = document.getElementById('docs-modal-tpl-title');
    if (modal) modal.style.display = 'flex';
    if (modalTitle && sel && sel.selectedOptions[0]) {
        modalTitle.textContent = sel.selectedOptions[0].textContent;
    }
};

window.docsCloseFullscreenPreview = function() {
    const modal = document.getElementById('docs-preview-modal');
    if (modal) modal.style.display = 'none';
};

// Close modal on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        window.docsCloseFullscreenPreview();
    }
});


window.docsOpenInTemplateEditor = async function() {
    const sel = document.getElementById('docs-default-template');
    const tplId = sel ? sel.value : null;
    if (!tplId) {
        const msg = 'Please select a template to edit first.';
        if (window.showToast) window.showToast(msg, 'warning');
        else alert(msg);
        return;
    }

    // Switch to templates tab using Hecos hub showTab or DOM click
    if (typeof window.showTab === 'function') {
        await window.showTab('templates');
    } else {
        const tplTabBtn = document.querySelector('[data-tab="templates"], [onclick*="templates"]');
        if (tplTabBtn) tplTabBtn.click();
    }

    // After tab switches, instruct TemplateManager to open this template
    setTimeout(() => {
        if (window.TemplateManager && typeof window.TemplateManager.editTemplate === 'function') {
            window.TemplateManager.editTemplate(tplId);
        } else if (window.loadTemplateEditor && typeof window.loadTemplateEditor === 'function') {
            window.loadTemplateEditor(tplId);
        }
    }, 250);
};

window.docsCreateNewTemplate = async function() {
    if (typeof window.showTab === 'function') {
        await window.showTab('templates');
    } else {
        const tplTabBtn = document.querySelector('[data-tab="templates"], [onclick*="templates"]');
        if (tplTabBtn) tplTabBtn.click();
    }
    setTimeout(() => {
        if (window.TemplateManager && typeof window.TemplateManager.newTemplate === 'function') {
            window.TemplateManager.newTemplate('document');
        }
    }, 250);
};


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

        const formatEl = document.getElementById('docs-page-format');
        if (formatEl) formatEl.value = data.page_format || 'A4';

        const optEl = document.getElementById('docs-ai-optimization');
        if (optEl) optEl.value = data.ai_optimization || 'hybrid';

        const mtEl = document.getElementById('docs-margin-top');
        if (mtEl) mtEl.value = data.margin_top !== undefined ? data.margin_top : 20;
        
        const mbEl = document.getElementById('docs-margin-bottom');
        if (mbEl) mbEl.value = data.margin_bottom !== undefined ? data.margin_bottom : 20;

        const mlEl = document.getElementById('docs-margin-left');
        if (mlEl) mlEl.value = data.margin_left !== undefined ? data.margin_left : 20;

        const mrEl = document.getElementById('docs-margin-right');
        if (mrEl) mrEl.value = data.margin_right !== undefined ? data.margin_right : 20;

        const photoCountEl = document.getElementById('docs-default-photo-count');
        if (photoCountEl) photoCountEl.value = (data.default_photo_count !== undefined) ? String(data.default_photo_count) : "0";

        window._docsSavedDefaultTemplateId = data.default_template_id || "";
        const forceTplEl = document.getElementById('docs-force-default-template');
        if (forceTplEl) forceTplEl.checked = !!data.force_default_template;

        const directiveEl = document.getElementById('docs-override-generate-pdf');
        if (directiveEl) {
            directiveEl.value = (data.override_directive !== undefined)
                ? data.override_directive
                : DOCS_DEFAULT_OVERRIDE;
        }

        // Fetch templates and populate dropdown
        await window.docsFetchTemplates();
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

    const formatEl = document.getElementById('docs-page-format');
    const optEl = document.getElementById('docs-ai-optimization');
    const mtEl = document.getElementById('docs-margin-top');
    const mbEl = document.getElementById('docs-margin-bottom');
    const mlEl = document.getElementById('docs-margin-left');
    const mrEl = document.getElementById('docs-margin-right');

    const tplSel = document.getElementById('docs-default-template');
    const forceTplEl = document.getElementById('docs-force-default-template');
    const photoCountEl = document.getElementById('docs-default-photo-count');

    const payload = {
        pdf_save_path: pathEl.value.trim() || 'media/documents',
        override_enabled: enabledEl ? enabledEl.checked : true,
        generate_html: htmlEl ? htmlEl.checked : true,
        generate_pdf: pdfEl ? pdfEl.checked : true,
        page_format: formatEl ? formatEl.value : 'A4',
        ai_optimization: optEl ? optEl.value : 'hybrid',
        margin_top: mtEl ? parseInt(mtEl.value) || 0 : 20,
        margin_bottom: mbEl ? parseInt(mbEl.value) || 0 : 20,
        margin_left: mlEl ? parseInt(mlEl.value) || 0 : 20,
        margin_right: mrEl ? parseInt(mrEl.value) || 0 : 20,
        default_template_id: tplSel ? tplSel.value : "",
        force_default_template: forceTplEl ? forceTplEl.checked : false,
        default_photo_count: photoCountEl ? (parseInt(photoCountEl.value) || 0) : 0,
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
(function() {
    const _origSaveConfig = window.saveConfig;
    window.saveConfig = async function(...args) {
        await window.saveDocsConfig(true);
        if (typeof _origSaveConfig === 'function') return _origSaveConfig(...args);
    };
})();

// ── Tab Navigation Listeners & Auto-Init ─────────────────────────────────────
document.addEventListener('click', (e) => {
    const tabBtn = e.target.closest('[onclick*="docs"], [data-tab="docs"], [onclick*="document_maker"]');
    if (tabBtn) {
        setTimeout(() => {
            if (typeof window.loadDocsConfig === 'function') window.loadDocsConfig();
        }, 120);
    }
});

// Periodic observer to ensure lazy-loaded panel is populated
let _docsInitAttempts = 0;
const _docsInitInterval = setInterval(() => {
    _docsInitAttempts++;
    if (document.getElementById('docs-default-template')) {
        if (typeof window.loadDocsConfig === 'function') window.loadDocsConfig();
        if (_docsInitAttempts > 4) clearInterval(_docsInitInterval);
    }
    if (_docsInitAttempts > 25) clearInterval(_docsInitInterval);
}, 250);

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (typeof window.loadDocsConfig === 'function') window.loadDocsConfig();
    });
} else {
    if (typeof window.loadDocsConfig === 'function') window.loadDocsConfig();
}
