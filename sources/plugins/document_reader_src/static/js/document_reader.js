/**
 * Hecos Document Reader — Main JS
 * Fullscreen document reader with Web Speech API TTS and PDF.js text extraction.
 * 
 * Features:
 *  - Read entire document aloud
 *  - Read selected text (mouse selection)
 *  - Read individual sentences/words on click
 *  - Audiobook-style transport controls (play, pause, prev, next sentence)
 *  - Adjustable speed, pitch, volume, voice
 *  - Fullscreen with ESC to exit
 *  - PDF text extraction via PDF.js
 */

(function() {
    'use strict';

    // ── State ────────────────────────────────────────────────────────────────
    const STATE = {
        isOpen: false,
        isReading: false,
        isPaused: false,
        currentPath: null,
        sentences: [],          // Array of {text, el, pageIdx, pageNum} objects
        currentIndex: 0,        // Currently reading sentence index
        rate: 1.0,
        pitch: 1.0,
        volume: 1.0,
        voiceSource: 'hecos',   // 'hecos' | 'browser'
        hecosPresetId: 'current', // 'current' | specific preset ID
        selectedVoice: null,    // Browser voice name (when voiceSource === 'browser')
        fontSize: 1.1,          // em (used in text mode)
        visualZoom: 1.0,        // zoom factor for canvas (used in visual mode)
        viewMode: 'visual',     // 'visual' | 'split' | 'text'
        docType: 'pdf',         // 'pdf' | 'html' | 'md' | 'txt'
        utterance: null,
        _currentAudio: null,    // HTML5 Audio instance for Hecos local TTS
        _audioCache: new Map(), // sentenceIndex -> audioUrl
        _prefetchSet: new Set(),// Indices currently being pre-fetched
        availablePresets: [],   // Hecos presets list from backend
        activePresetName: '',   // Name of active preset in chat
        sidebarOpen: false,
        pages: [],              // Page-separated content
        wordHighlight: true,    // Enable word-by-word highlighting
    };

    // ── PDF.js Loader ────────────────────────────────────────────────────────
    let _pdfjsLoaded = false;
    function _loadPDFJS(callback) {
        if (window.pdfjsLib) {
            if (!window.pdfjsLib.GlobalWorkerOptions.workerSrc) {
                window.pdfjsLib.GlobalWorkerOptions.workerSrc = 
                    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
            }
            _pdfjsLoaded = true;
            callback();
            return;
        }
        const fallbackScript = document.createElement('script');
        fallbackScript.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
        fallbackScript.onload = () => {
            if (window.pdfjsLib) {
                window.pdfjsLib.GlobalWorkerOptions.workerSrc = 
                    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
                _pdfjsLoaded = true;
                callback();
            }
        };
        fallbackScript.onerror = () => {
            console.error('[DocReader] Failed to load PDF.js');
        };
        document.head.appendChild(fallbackScript);
    }

    // ── Load PDF Document (Full Visual Pages + Text) ──────────────────────────
    async function loadPDFDocument(url, sessionId) {
        return new Promise((resolve, reject) => {
            _loadPDFJS(async () => {
                try {
                    const loadingTask = window.pdfjsLib.getDocument({ url: url, withCredentials: true });
                    const pdf = await loadingTask.promise;
                    if (sessionId && STATE._sessionId !== sessionId) {
                        try { pdf.destroy(); } catch (e) {}
                        return reject(new Error('Document session expired'));
                    }
                    const pages = [];
                    
                    for (let i = 1; i <= pdf.numPages; i++) {
                        if (sessionId && STATE._sessionId !== sessionId) {
                            try { pdf.destroy(); } catch (e) {}
                            return reject(new Error('Document session expired'));
                        }
                        const page = await pdf.getPage(i);
                        const textContent = await page.getTextContent();
                        const pageText = textContent.items
                            .map(item => item.str)
                            .join(' ')
                            .replace(/\s+/g, ' ')
                            .trim();
                        // Always include page so images & canvas render even for pure comic/image pages!
                        pages.push({
                            pageNum: i,
                            text: pageText || '',
                            pdfPage: page,
                            textContent: textContent
                        });
                    }
                    resolve({ pages: pages, pdfDoc: pdf, docType: 'pdf' });
                } catch (e) {
                    reject(e);
                }
            });
        });
    }

    // ── Load HTML/MD/TXT Documents (With Rich Elements & Images) ─────────────
    async function loadTextDocument(url, ext, rawFilePath) {
        const response = await fetch(url);
        const text = await response.text();
        
        if (ext === 'html' || ext === 'htm') {
            const parser = new DOMParser();
            const doc = parser.parseFromString(text, 'text/html');
            doc.querySelectorAll('script').forEach(el => el.remove());

            // Rewrite relative images to /api/local_file
            const basePath = rawFilePath ? rawFilePath.substring(0, rawFilePath.lastIndexOf('/') + 1) : '';
            doc.querySelectorAll('img').forEach(img => {
                const src = img.getAttribute('src');
                if (src && !src.startsWith('http://') && !src.startsWith('https://') && !src.startsWith('data:') && !src.startsWith('/api/')) {
                    if (basePath) {
                        img.src = `/api/local_file?path=${encodeURIComponent(basePath + src)}`;
                    }
                }
                img.style.maxWidth = '100%';
                img.style.borderRadius = '8px';
                img.style.margin = '12px 0';
                img.style.boxShadow = '0 4px 16px rgba(0,0,0,0.3)';
            });

            const bodyHtml = doc.body ? doc.body.innerHTML : text;
            const bodyText = doc.body ? doc.body.innerText : text;
            return {
                pages: [{
                    pageNum: 1,
                    text: bodyText.trim(),
                    htmlContent: bodyHtml
                }],
                docType: 'html'
            };
        }

        if (ext === 'md') {
            const basePath = rawFilePath ? rawFilePath.substring(0, rawFilePath.lastIndexOf('/') + 1) : '';
            let renderedHtml = text
                .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, src) => {
                    let fullSrc = src;
                    if (!src.startsWith('http') && !src.startsWith('data:') && !src.startsWith('/api/')) {
                        if (basePath) fullSrc = `/api/local_file?path=${encodeURIComponent(basePath + src)}`;
                    }
                    return `<div style="text-align:center;margin:16px 0;"><img src="${fullSrc}" alt="${alt}" style="max-width:100%;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.4);"/><div style="font-size:0.8em;opacity:0.6;margin-top:4px;">${alt}</div></div>`;
                })
                .replace(/^### (.*$)/gim, '<h3 style="color:#c4b5fd;margin:16px 0 8px;">$1</h3>')
                .replace(/^## (.*$)/gim, '<h2 style="color:#a78bfa;margin:20px 0 10px;">$1</h2>')
                .replace(/^# (.*$)/gim, '<h1 style="color:#8b5cf6;margin:24px 0 12px;">$1</h1>')
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>');

            return {
                pages: [{
                    pageNum: 1,
                    text: text.trim(),
                    htmlContent: renderedHtml
                }],
                docType: 'md'
            };
        }

        return {
            pages: [{ pageNum: 1, text: text.trim() }],
            docType: 'txt'
        };
    }

    // ── Split text into sentences ────────────────────────────────────────────
    function splitIntoSentences(text) {
        // Split on sentence-ending punctuation followed by space or end
        const raw = text.match(/[^.!?…]+[.!?…]+[\s]?|[^.!?…]+$/g) || [text];
        return raw
            .map(s => s.trim())
            .filter(s => s.length > 0);
    }

    // ── Create overlay DOM ───────────────────────────────────────────────────
    function _createOverlay() {
        let overlay = document.getElementById('docreader-overlay');
        if (overlay) return overlay;

        overlay = document.createElement('div');
        overlay.id = 'docreader-overlay';
        overlay.className = 'docreader-overlay';
        overlay.innerHTML = `
            <!-- Header -->
            <div class="docreader-header">
                <div class="docreader-header-left">
                    <div class="docreader-logo">
                        <i class="fas fa-book-reader"></i>
                        <span>Document Reader</span>
                    </div>
                    <span class="docreader-filename" id="docreader-filename"></span>
                    <div class="docreader-status" id="docreader-status">
                        <div class="docreader-status-dot" id="docreader-status-dot"></div>
                        <span id="docreader-status-text">Ready</span>
                    </div>
                </div>
                <div class="docreader-header-right">
                    <!-- View Mode Selector (Visual vs Split vs Text) -->
                    <div class="docreader-view-modes" id="docreader-view-modes">
                        <button class="docreader-view-btn active" id="docreader-mode-visual" onclick="window.DocReader.setViewMode('visual')" title="Visual Document (displays all images, artwork & layout)">
                            <i class="fas fa-image"></i> Visual
                        </button>
                        <button class="docreader-view-btn" id="docreader-mode-split" onclick="window.DocReader.setViewMode('split')" title="Split View (visual + text side-by-side)">
                            <i class="fas fa-columns"></i> Split
                        </button>
                        <button class="docreader-view-btn" id="docreader-mode-text" onclick="window.DocReader.setViewMode('text')" title="Reading Flow (text only)">
                            <i class="fas fa-align-left"></i> Text
                        </button>
                    </div>

                    <div class="docreader-font-controls">
                        <button class="docreader-font-btn" onclick="window.DocReader.changeFontSize(-0.1)" title="Zoom out / decrease text size">
                            <i class="fas fa-minus"></i>
                        </button>
                        <button class="docreader-font-btn" onclick="window.DocReader.changeFontSize(0.1)" title="Zoom in / increase text size">
                            <i class="fas fa-plus"></i>
                        </button>
                    </div>
                    <button class="docreader-btn-icon" onclick="window.DocReader.toggleSidebar()" title="Table of Contents & Page Thumbnails">
                        <i class="fas fa-list-ul"></i>
                    </button>
                    <button class="docreader-btn docreader-btn-close" onclick="window.DocReader.close()">
                        <i class="fas fa-times"></i> Close
                    </button>
                </div>
            </div>

            <!-- Body -->
            <div class="docreader-body">
                <div class="docreader-document" id="docreader-document">
                    <div class="docreader-content" id="docreader-content">
                        <div class="docreader-loading" id="docreader-loading">
                            <div class="docreader-spinner"></div>
                            <div class="docreader-loading-text">Loading document...</div>
                        </div>
                    </div>
                </div>
                <div class="docreader-sidebar" id="docreader-sidebar">
                    <div class="docreader-sidebar-header">
                        <i class="fas fa-bookmark"></i> Pages
                    </div>
                    <div class="docreader-sidebar-content" id="docreader-toc"></div>
                </div>
            </div>

            <!-- Player Bar -->
            <div class="docreader-player">
                <!-- Transport -->
                <div class="docreader-transport">
                    <button class="docreader-transport-btn" onclick="window.DocReader.prevSentence()" title="Previous sentence">
                        <i class="fas fa-step-backward"></i>
                    </button>
                    <button class="docreader-transport-btn play-btn" id="docreader-play-btn" onclick="window.DocReader.togglePlayPause()" title="Play / Pause">
                        <i class="fas fa-play" id="docreader-play-icon"></i>
                    </button>
                    <button class="docreader-transport-btn" onclick="window.DocReader.nextSentence()" title="Next sentence">
                        <i class="fas fa-step-forward"></i>
                    </button>
                    <button class="docreader-transport-btn" onclick="window.DocReader.stop()" title="Stop">
                        <i class="fas fa-stop"></i>
                    </button>
                </div>

                <!-- Progress -->
                <div class="docreader-progress-wrap">
                    <div class="docreader-progress-bar" id="docreader-progress-bar" onclick="window.DocReader.seekProgress(event)">
                        <div class="docreader-progress-fill" id="docreader-progress-fill"></div>
                    </div>
                    <div class="docreader-progress-info">
                        <span id="docreader-progress-current">0 / 0</span>
                        <span id="docreader-progress-page">Page -</span>
                    </div>
                </div>

                <!-- Controls -->
                <div class="docreader-controls">
                    <!-- Speed -->
                    <div class="docreader-control-group">
                        <span class="docreader-control-label">Speed</span>
                        <button class="docreader-speed-btn" id="docreader-speed-btn" onclick="window.DocReader.cycleSpeed()" title="Cycle speed">
                            1.0×
                        </button>
                    </div>

                    <!-- Voice Source / Voice Selection -->
                    <div class="docreader-control-group">
                        <span class="docreader-control-label">Voice</span>
                        <select class="docreader-voice-select" id="docreader-voice-select" onchange="window.DocReader.changeVoiceSource(this.value)" title="Choose Voice Engine or Browser Voice">
                            <optgroup label="Hecos Neural Voice (Local)">
                                <option value="hecos_current" selected>✨ Current Hecos Voice (Local)</option>
                                <option value="hecos_preset">🎙️ Select Hecos Preset...</option>
                            </optgroup>
                            <optgroup label="Browser Voices (Web Speech)" id="docreader-browser-optgroup">
                            </optgroup>
                        </select>
                    </div>

                    <!-- Hecos Preset Selector (visible when Hecos is active) -->
                    <div class="docreader-control-group" id="docreader-preset-group">
                        <span class="docreader-control-label">Preset</span>
                        <select class="docreader-preset-select" id="docreader-preset-select" onchange="window.DocReader.changeHecosPreset(this.value)" title="Choose a Hecos character preset">
                            <option value="current">Active Chat Voice</option>
                        </select>
                    </div>

                    <!-- Volume -->
                    <div class="docreader-control-group">
                        <span class="docreader-control-label"><i class="fas fa-volume-up"></i></span>
                        <input type="range" class="docreader-volume-slider" id="docreader-volume" 
                               min="0" max="1" step="0.05" value="1" 
                               oninput="window.DocReader.changeVolume(this.value)">
                    </div>
                </div>
            </div>

            <!-- Live Read-Along Karaoke HUD -->
            <div class="docreader-readalong-hud" id="docreader-readalong-hud">
                <div class="docreader-readalong-badge" id="docreader-readalong-badge">Page 1</div>
                <div class="docreader-readalong-content" id="docreader-readalong-content">
                    Ready to read document...
                </div>
            </div>

            <!-- Selection Tooltip -->
            <div class="docreader-selection-tooltip" id="docreader-selection-tooltip">
                <button onclick="window.DocReader.readSelection()">
                    <i class="fas fa-volume-up"></i> Read Selection
                </button>
                <button onclick="window.DocReader.readFromHere()">
                    <i class="fas fa-play"></i> Read From Here
                </button>
            </div>
        `;
        document.body.appendChild(overlay);

        // ESC key handler fallback (if HKS is not active)
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && STATE.isOpen) {
                e.preventDefault();
                e.stopPropagation();
                if (STATE.isReading) {
                    window.DocReader.stop();
                    if (window.showToast) window.showToast('🔇 Document Reader voice stopped', 'info');
                } else {
                    window.DocReader.close();
                }
            }
        });

        // Selection tooltip handler
        const docEl = overlay.querySelector('#docreader-document');
        docEl.addEventListener('mouseup', _handleSelectionTooltip);
        docEl.addEventListener('mousedown', () => {
            const tooltip = document.getElementById('docreader-selection-tooltip');
            if (tooltip) tooltip.classList.remove('visible');
        });

        // Initialize voices, presets, and config
        _loadConfig();
        _loadHecosPresets();
        _populateVoices();
        if (speechSynthesis.onvoiceschanged !== undefined) {
            speechSynthesis.onvoiceschanged = _populateVoices;
        }

        return overlay;
    }

    // ── Load Hecos Presets from Backend ──────────────────────────────────────
    async function _loadHecosPresets() {
        try {
            // Fetch from core /api/souls and /hecos/config which are always available
            const [soulsRes, cfgRes] = await Promise.all([
                fetch('/api/souls', { cache: 'no-store' }).catch(() => null),
                fetch('/hecos/config', { cache: 'no-store' }).catch(() => null)
            ]);

            let souls = [];
            if (soulsRes && soulsRes.ok) {
                const soulsData = await soulsRes.json();
                if (soulsData.ok && Array.isArray(soulsData.souls)) {
                    souls = soulsData.souls;
                }
            }

            let activeId = 'urania_9800_gp';
            if (cfgRes && cfgRes.ok) {
                const cfgData = await cfgRes.json();
                if (cfgData.ai && cfgData.ai.active_global_preset) {
                    activeId = cfgData.ai.active_global_preset;
                }
            }

            if (souls.length === 0) {
                try {
                    const res = await fetch('/hecos/api/plugins/document_reader/presets');
                    if (res.ok) {
                        const data = await res.json();
                        if (data.ok && Array.isArray(data.presets)) {
                            STATE.availablePresets = data.presets;
                            STATE.activePresetName = data.active_preset_name || 'Urania 9800 GP';
                            _populatePresetSelect();
                            _syncVoiceUI();
                            return;
                        }
                    }
                } catch (e) {}
            }

            if (souls.length > 0) {
                const matchedActive = souls.find(s => s.meta && s.meta.id === activeId);
                if (matchedActive && matchedActive.meta && matchedActive.meta.name) {
                    STATE.activePresetName = matchedActive.meta.name;
                } else {
                    STATE.activePresetName = 'Urania 9800 GP';
                }

                souls.sort((a, b) => (a.meta?.name || '').localeCompare(b.meta?.name || ''));
                STATE.availablePresets = souls.map(s => ({
                    id: s.meta.id,
                    name: s.meta.name,
                    engine: s.voice?.tts_engine ? s.voice.tts_engine.toUpperCase() : 'LOCAL',
                    voice: s.voice?.tts_voice || ''
                }));

                _populatePresetSelect();
                _syncVoiceUI();
            }
        } catch (e) {
            console.warn('[DocReader] Failed to load Hecos presets:', e);
        }
    }

    function _populatePresetSelect() {
        const pSelect = document.getElementById('docreader-preset-select');
        if (!pSelect) return;
        pSelect.innerHTML = '';

        const currOptInVoice = document.querySelector('#docreader-voice-select option[value="hecos_current"]');
        if (currOptInVoice) {
            currOptInVoice.textContent = `✨ Current Hecos Voice (Local) [${STATE.activePresetName || 'Active Chat'}]`;
        }

        const currOpt = document.createElement('option');
        currOpt.value = 'current';
        currOpt.textContent = `✨ Active Chat (${STATE.activePresetName || 'Hecos'})`;
        pSelect.appendChild(currOpt);

        STATE.availablePresets.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = `${p.name} (${p.engine}${p.voice ? ' · ' + p.voice : ''})`;
            pSelect.appendChild(opt);
        });

        if (STATE.hecosPresetId) {
            pSelect.value = STATE.hecosPresetId;
        }
    }

    // ── Load User Saved Config ───────────────────────────────────────────────
    async function _loadConfig() {
        try {
            const res = await fetch('/hecos/api/plugins/document_reader/config');
            if (!res.ok) return;
            const cfg = await res.json();
            if (cfg.voice_source) STATE.voiceSource = cfg.voice_source;
            if (cfg.hecos_preset) STATE.hecosPresetId = cfg.hecos_preset;
            if (cfg.default_voice) STATE.selectedVoice = cfg.default_voice;
            if (cfg.default_rate) STATE.rate = parseFloat(cfg.default_rate);
            if (cfg.default_pitch) STATE.pitch = parseFloat(cfg.default_pitch);
            if (cfg.default_volume) STATE.volume = parseFloat(cfg.default_volume);
            if (cfg.highlight_color) {
                document.documentElement.style.setProperty('--docreader-highlight-color', cfg.highlight_color);
            }
            if (typeof cfg.word_highlight === 'boolean') STATE.wordHighlight = cfg.word_highlight;

            // Update UI elements to reflect config
            const speedBtn = document.getElementById('docreader-speed-btn');
            if (speedBtn) speedBtn.textContent = STATE.rate + '×';
            const volSlider = document.getElementById('docreader-volume');
            if (volSlider) volSlider.value = STATE.volume;

            _syncVoiceUI();
        } catch (e) {
            console.warn('[DocReader] Failed to load config:', e);
        }
    }

    // ── Sync UI Selects with State ───────────────────────────────────────────
    function _syncVoiceUI() {
        const vSelect = document.getElementById('docreader-voice-select');
        const pGroup = document.getElementById('docreader-preset-group');
        const pSelect = document.getElementById('docreader-preset-select');
        if (!vSelect) return;

        const currVoiceOpt = vSelect.querySelector('option[value="hecos_current"]');
        if (currVoiceOpt && STATE.activePresetName) {
            currVoiceOpt.textContent = `✨ Current Hecos Voice (${STATE.activePresetName})`;
        }

        if (STATE.voiceSource === 'hecos') {
            if (STATE.hecosPresetId === 'current') {
                vSelect.value = 'hecos_current';
            } else {
                vSelect.value = 'hecos_preset';
            }
            if (pGroup) pGroup.style.display = 'flex';
            if (pSelect && STATE.hecosPresetId) {
                pSelect.value = STATE.hecosPresetId;
                const pOpt = pSelect.options[pSelect.selectedIndex];
                const pPresetOpt = vSelect.querySelector('option[value="hecos_preset"]');
                if (pPresetOpt && pOpt && STATE.hecosPresetId !== 'current') {
                    pPresetOpt.textContent = `🎙️ Preset: ${pOpt.textContent.split('(')[0].trim()}`;
                }
            }
        } else {
            if (STATE.selectedVoice) {
                vSelect.value = 'browser:' + STATE.selectedVoice;
            }
            if (pGroup) pGroup.style.display = 'none';
        }
    }

    // ── Populate TTS voices ──────────────────────────────────────────────────
    function _populateVoices() {
        const select = document.getElementById('docreader-voice-select');
        if (!select) return;

        let browserGroup = document.getElementById('docreader-browser-optgroup');
        if (!browserGroup) {
            browserGroup = document.createElement('optgroup');
            browserGroup.id = 'docreader-browser-optgroup';
            browserGroup.label = "Browser Voices (Web Speech)";
            select.appendChild(browserGroup);
        }
        browserGroup.innerHTML = '';

        const voices = speechSynthesis.getVoices();
        if (voices && voices.length > 0) {
            const priority = ['it', 'en', 'es', 'fr', 'de', 'pt'];
            const sortedVoices = [...voices].sort((a, b) => {
                const aLang = a.lang.split('-')[0].toLowerCase();
                const bLang = b.lang.split('-')[0].toLowerCase();
                const aIdx = priority.indexOf(aLang);
                const bIdx = priority.indexOf(bLang);
                if (aIdx !== -1 && bIdx !== -1) return aIdx - bIdx;
                if (aIdx !== -1) return -1;
                if (bIdx !== -1) return 1;
                return a.name.localeCompare(b.name);
            });

            sortedVoices.forEach(v => {
                const opt = document.createElement('option');
                opt.value = 'browser:' + v.name;
                opt.textContent = `${v.name} (${v.lang})`;
                browserGroup.appendChild(opt);
            });
        }

        _syncVoiceUI();
    }

    // ── Selection tooltip logic ──────────────────────────────────────────────
    function _handleSelectionTooltip(e) {
        const sel = window.getSelection();
        const selectedText = sel.toString().trim();
        const tooltip = document.getElementById('docreader-selection-tooltip');
        if (!tooltip) return;

        if (selectedText.length > 2) {
            STATE._selectedText = selectedText;
            
            // Position tooltip near selection
            const range = sel.getRangeAt(0);
            const rect = range.getBoundingClientRect();
            tooltip.style.top = (rect.bottom + 8) + 'px';
            tooltip.style.left = Math.max(10, rect.left) + 'px';
            tooltip.classList.add('visible');
        } else {
            tooltip.classList.remove('visible');
        }
    }

    // ── Render pages and content area ────────────────────────────────────────
    function _renderContent(docData, sessionId) {
        if (sessionId && STATE._sessionId !== sessionId) return;
        const contentEl = document.getElementById('docreader-content');
        const tocEl = document.getElementById('docreader-toc');
        if (!contentEl) return;

        contentEl.innerHTML = '';
        tocEl.innerHTML = '';
        STATE.sentences = [];
        let globalIdx = 0;

        const pages = docData.pages || [];
        const isPdf = docData.docType === 'pdf';
        const isHtml = docData.docType === 'html';
        const isMd = docData.docType === 'md';

        // Default view mode: 'visual' for PDF and HTML, 'text' for pure text
        const defaultMode = (isPdf || isHtml) ? 'visual' : 'text';
        STATE.viewMode = defaultMode;

        // Container with view mode class
        const container = document.createElement('div');
        container.className = `docreader-pages-container docreader-view-${defaultMode}`;
        container.id = 'docreader-pages-container';
        contentEl.appendChild(container);

        // Update view mode header buttons
        const modeGroup = document.getElementById('docreader-view-modes');
        if (modeGroup) {
            modeGroup.style.display = isPdf ? 'flex' : 'none';
            document.querySelectorAll('.docreader-view-btn').forEach(b => b.classList.remove('active'));
            const activeBtn = document.getElementById(`docreader-mode-${defaultMode}`);
            if (activeBtn) activeBtn.classList.add('active');
        }

        pages.forEach((page, pageIdx) => {
            // Page Card
            const pageCard = document.createElement('div');
            pageCard.className = 'docreader-page-card';
            pageCard.id = `docreader-page-${page.pageNum}`;
            pageCard.dataset.pageIdx = pageIdx;
            pageCard.dataset.pageNum = page.pageNum;

            // Page Header Bar
            const pageHeader = document.createElement('div');
            pageHeader.className = 'docreader-page-header';
            pageHeader.innerHTML = `
                <span class="docreader-page-badge"><i class="fas fa-file-alt"></i> Page ${page.pageNum} of ${pages.length}</span>
                <span style="font-size:0.75em;color:rgba(255,255,255,0.4);"><i class="fas fa-mouse-pointer"></i> Click to read</span>
            `;
            pageCard.appendChild(pageHeader);

            // If PDF: Add Canvas Wrapper
            if (isPdf) {
                const canvasWrap = document.createElement('div');
                canvasWrap.className = 'docreader-canvas-wrap';
                canvasWrap.id = `docreader-canvas-wrap-${page.pageNum}`;
                canvasWrap.innerHTML = `
                    <div class="docreader-canvas-loader">
                        <div class="docreader-spinner" style="width:20px;height:20px;border-width:2px;"></div>
                        <span>Rendering Page ${page.pageNum}...</span>
                    </div>
                `;
                pageCard.appendChild(canvasWrap);
            } else if (isHtml || isMd) {
                if (page.htmlContent) {
                    const richWrap = document.createElement('div');
                    richWrap.className = 'docreader-canvas-wrap';
                    richWrap.style.background = 'transparent';
                    richWrap.style.boxShadow = 'none';
                    richWrap.style.padding = '0';
                    richWrap.style.display = 'block';
                    richWrap.innerHTML = page.htmlContent;
                    pageCard.appendChild(richWrap);
                }
            }

            // Text Strip for reading & sentence highlighting
            const textStrip = document.createElement('div');
            textStrip.className = 'docreader-page-text-strip';
            textStrip.id = `docreader-text-strip-${page.pageNum}`;

            const sentences = splitIntoSentences(page.text || '');
            if (sentences.length === 0) {
                textStrip.innerHTML = '<span style="opacity:0.4;font-style:italic;font-size:0.85em;">Page contains visual elements or illustrations without extractable text.</span>';
            } else {
                sentences.forEach(sentenceText => {
                    const span = document.createElement('span');
                    span.className = 'docreader-sentence';
                    span.dataset.sentenceIdx = globalIdx;

                    const words = sentenceText.split(/(\s+)/);
                    words.forEach(word => {
                        if (/^\s+$/.test(word)) {
                            span.appendChild(document.createTextNode(word));
                        } else {
                            const wordSpan = document.createElement('span');
                            wordSpan.className = 'docreader-word';
                            wordSpan.textContent = word;
                            wordSpan.onclick = (e) => {
                                e.stopPropagation();
                                _readSingleWord(word);
                            };
                            span.appendChild(wordSpan);
                        }
                    });

                    span.onclick = (e) => {
                        e.stopPropagation();
                        window.DocReader.readFromIndex(parseInt(span.dataset.sentenceIdx));
                    };

                    textStrip.appendChild(span);
                    textStrip.appendChild(document.createTextNode(' '));

                    STATE.sentences.push({
                        text: sentenceText,
                        el: span,
                        pageIdx: pageIdx,
                        pageNum: page.pageNum
                    });
                    globalIdx++;
                });
            }

            pageCard.appendChild(textStrip);
            container.appendChild(pageCard);

            // TOC item in Sidebar with visual thumbnail placeholder
            const tocItem = document.createElement('div');
            tocItem.className = 'docreader-toc-item';
            if (pageIdx === 0) tocItem.classList.add('active');
            tocItem.dataset.pageIdx = pageIdx;
            const snippet = (page.text || '').replace(/\s+/g, ' ').trim().substring(0, 38);

            tocItem.innerHTML = `
                <div class="docreader-toc-thumb-wrap" id="docreader-toc-thumb-wrap-${page.pageNum}">
                    <div class="docreader-toc-thumb-placeholder"><i class="fas fa-image"></i></div>
                </div>
                <div class="docreader-toc-info">
                    <div class="docreader-toc-title"><i class="fas fa-file-alt"></i> Page ${page.pageNum}</div>
                    <div class="docreader-toc-snippet">${snippet ? snippet + '…' : 'Visual Page'}</div>
                </div>
            `;
            tocItem.onclick = () => _scrollToPage(pageIdx);
            tocEl.appendChild(tocItem);
        });

        // Automatically open the sidebar if document has multiple pages
        if (pages.length > 1) {
            const sidebar = document.getElementById('docreader-sidebar');
            if (sidebar) {
                sidebar.classList.add('open');
                STATE.sidebarOpen = true;
            }
        }

        _updateProgress();

        // Render PDF Page Canvases & Thumbnails progressively
        if (isPdf) {
            (async () => {
                for (let pIdx = 0; pIdx < pages.length; pIdx++) {
                    if (sessionId && STATE._sessionId !== sessionId) return;
                    await _renderPdfPageCanvas(pages[pIdx], pIdx, sessionId);
                    if (sessionId && STATE._sessionId !== sessionId) return;
                    _renderPdfPageThumb(pages[pIdx], pIdx, sessionId);
                }
            })();
        }
    }

    // ── Render High-DPI PDF Page to Canvas ────────────────────────────────────
    async function _renderPdfPageCanvas(pageData, pageIdx, sessionId) {
        if (sessionId && STATE._sessionId !== sessionId) return;
        const page = pageData.pdfPage;
        if (!page) return;

        const wrap = document.getElementById(`docreader-canvas-wrap-${pageData.pageNum}`);
        if (!wrap) return;

        try {
            const baseViewport = page.getViewport({ scale: 1.0 });
            const docPane = document.getElementById('docreader-document');
            const availWidth = docPane ? Math.max(500, docPane.clientWidth - 100) : 840;
            const targetWidth = Math.min(880, availWidth);
            const scale = targetWidth / baseViewport.width;
            const viewport = page.getViewport({ scale: scale });
            const dpr = Math.min(window.devicePixelRatio || 1, 2);

            const canvas = document.createElement('canvas');
            canvas.className = 'docreader-pdf-canvas';
            canvas.width = Math.floor(viewport.width * dpr);
            canvas.height = Math.floor(viewport.height * dpr);
            const cssW = Math.floor(viewport.width);
            const cssH = Math.floor(viewport.height);
            canvas.style.width = cssW + 'px';
            canvas.style.height = cssH + 'px';
            canvas.dataset.baseWidth = cssW;
            canvas.dataset.baseHeight = cssH;

            const ctx = canvas.getContext('2d');
            ctx.imageSmoothingEnabled = true;
            ctx.imageSmoothingQuality = 'high';

            const renderContext = {
                canvasContext: ctx,
                transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : null,
                viewport: viewport
            };

            await page.render(renderContext).promise;
            if (sessionId && STATE._sessionId !== sessionId) return;

            wrap.innerHTML = '';
            wrap.appendChild(canvas);

            if (STATE.visualZoom && STATE.visualZoom !== 1.0) {
                canvas.style.width = Math.floor(cssW * STATE.visualZoom) + 'px';
                canvas.style.height = Math.floor(cssH * STATE.visualZoom) + 'px';
            }

            canvas.style.cursor = 'pointer';
            canvas.title = `Click to start reading page ${pageData.pageNum}`;
            canvas.onclick = () => {
                document.querySelectorAll('.docreader-page-card.reading-page').forEach(c => c.classList.remove('reading-page'));
                const pc = document.getElementById(`docreader-page-${pageData.pageNum}`);
                if (pc) pc.classList.add('reading-page');
                let sIdx = STATE.sentences.findIndex(s => s.pageNum === pageData.pageNum);
                if (sIdx === -1) {
                    sIdx = STATE.sentences.findIndex(s => s.pageNum >= pageData.pageNum);
                }
                if (sIdx !== -1) {
                    window.DocReader.readFromIndex(sIdx);
                }
            };
        } catch (err) {
            if (sessionId && STATE._sessionId !== sessionId) return;
            console.error(`[DocReader] Failed to render page ${pageData.pageNum}:`, err);
            if (wrap) {
                wrap.innerHTML = `<div class="docreader-canvas-loader" style="color:#ef4444;"><i class="fas fa-exclamation-triangle"></i> Error rendering page image</div>`;
            }
        }
    }

    // ── Render Thumbnail in TOC Sidebar ───────────────────────────────────────
    async function _renderPdfPageThumb(pageData, pageIdx, sessionId) {
        if (sessionId && STATE._sessionId !== sessionId) return;
        const page = pageData.pdfPage;
        if (!page) return;

        const thumbWrap = document.getElementById(`docreader-toc-thumb-wrap-${pageData.pageNum}`);
        if (!thumbWrap) return;

        try {
            const baseViewport = page.getViewport({ scale: 1.0 });
            const thumbScale = 96 / baseViewport.width;
            const thumbViewport = page.getViewport({ scale: thumbScale });

            const canvas = document.createElement('canvas');
            canvas.className = 'docreader-toc-canvas';
            canvas.width = Math.floor(thumbViewport.width);
            canvas.height = Math.floor(thumbViewport.height);

            const ctx = canvas.getContext('2d');
            await page.render({
                canvasContext: ctx,
                viewport: thumbViewport
            }).promise;
            if (sessionId && STATE._sessionId !== sessionId) return;

            thumbWrap.innerHTML = '';
            thumbWrap.appendChild(canvas);
        } catch(e) {
            // Non-fatal
        }
    }

    // ── Update Karaoke Read-Along HUD ─────────────────────────────────────────
    function _updateReadAlongHud(sentenceData, wordIndex = -1) {
        const hud = document.getElementById('docreader-readalong-hud');
        const badge = document.getElementById('docreader-readalong-badge');
        const content = document.getElementById('docreader-readalong-content');
        if (!hud || !content || !sentenceData) return;

        hud.classList.add('visible');
        if (badge) badge.textContent = `Page ${sentenceData.pageNum}`;

        const words = sentenceData.text.split(/(\s+)/);
        let wCount = 0;
        content.innerHTML = '';
        words.forEach(w => {
            if (/^\s+$/.test(w)) {
                content.appendChild(document.createTextNode(w));
            } else {
                const sp = document.createElement('span');
                sp.className = 'docreader-hud-word';
                if (wCount === wordIndex) sp.classList.add('active-word');
                sp.textContent = w;
                content.appendChild(sp);
                wCount++;
            }
        });
    }

    function _scrollToPage(pageIdx) {
        const pages = document.querySelectorAll('.docreader-page-card, .docreader-page');
        if (pages[pageIdx]) {
            pages[pageIdx].scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        document.querySelectorAll('.docreader-toc-item').forEach(el => {
            el.classList.toggle('active', parseInt(el.dataset.pageIdx) === pageIdx);
        });
    }

    // ── Update progress display ──────────────────────────────────────────────
    function _updateProgress() {
        const currentEl = document.getElementById('docreader-progress-current');
        const pageEl = document.getElementById('docreader-progress-page');
        const fillEl = document.getElementById('docreader-progress-fill');
        
        if (currentEl) {
            currentEl.textContent = `${STATE.currentIndex + 1} / ${STATE.sentences.length}`;
        }
        if (pageEl && STATE.sentences[STATE.currentIndex]) {
            pageEl.textContent = `Page ${STATE.sentences[STATE.currentIndex].pageNum}`;
        }
        if (fillEl && STATE.sentences.length > 0) {
            const pct = ((STATE.currentIndex + 1) / STATE.sentences.length) * 100;
            fillEl.style.width = pct + '%';
        }
    }

    // ── Update status display ────────────────────────────────────────────────
    function _updateStatus(status, text) {
        const dot = document.getElementById('docreader-status-dot');
        const txt = document.getElementById('docreader-status-text');
        if (dot) {
            dot.className = 'docreader-status-dot';
            if (status === 'reading') dot.classList.add('reading');
            else if (status === 'paused') dot.classList.add('paused');
        }
        if (txt) txt.textContent = text || 'Ready';
    }

    // ── Update play button ───────────────────────────────────────────────────
    function _updatePlayBtn() {
        const btn = document.getElementById('docreader-play-btn');
        const icon = document.getElementById('docreader-play-icon');
        if (!btn || !icon) return;

        if (STATE.isReading && !STATE.isPaused) {
            icon.className = 'fas fa-pause';
            btn.classList.add('active');
        } else {
            icon.className = 'fas fa-play';
            btn.classList.remove('active');
        }
    }

    // ── Highlight current sentence & page ─────────────────────────────────────
    function _highlightSentence(index, clear = false) {
        // Clear all highlights
        document.querySelectorAll('.docreader-sentence.reading').forEach(el => {
            el.classList.remove('reading');
        });
        document.querySelectorAll('.docreader-word.active-word').forEach(el => {
            el.classList.remove('active-word');
        });

        if (clear || index < 0 || index >= STATE.sentences.length) {
            const hud = document.getElementById('docreader-readalong-hud');
            if (hud) hud.classList.remove('visible');
            document.querySelectorAll('.docreader-page-card.reading-page').forEach(c => c.classList.remove('reading-page'));
            return;
        }

        const sentenceData = STATE.sentences[index];
        if (sentenceData) {
            if (sentenceData.el) {
                sentenceData.el.classList.add('reading');
                if (STATE.viewMode === 'text') {
                    sentenceData.el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }

            // Highlight page card and scroll
            const pageCard = document.getElementById(`docreader-page-${sentenceData.pageNum}`);
            if (pageCard) {
                document.querySelectorAll('.docreader-page-card.reading-page').forEach(c => c.classList.remove('reading-page'));
                pageCard.classList.add('reading-page');
                if (STATE.viewMode !== 'text') {
                    pageCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            }

            _updateReadAlongHud(sentenceData);
        }
    }

    // ── TTS: Speak a sentence ────────────────────────────────────────────────
    function _speakSentence(index, onEnd) {
        if (index < 0 || index >= STATE.sentences.length) {
            if (onEnd) onEnd(true); // done = true
            return;
        }

        const sentenceData = STATE.sentences[index];
        STATE.currentIndex = index;
        _highlightSentence(index);
        _updateProgress();

        // Update TOC active
        document.querySelectorAll('.docreader-toc-item').forEach(el => {
            el.classList.toggle('active', 
                parseInt(el.dataset.pageIdx) === sentenceData.pageIdx);
        });

        if (STATE.voiceSource === 'browser') {
            _speakWithWebSpeech(sentenceData, onEnd);
        } else {
            _speakWithHecosLocal(index, sentenceData, onEnd);
        }
    }

    // ── Mode A: Web Speech API (Browser) ─────────────────────────────────────
    function _speakWithWebSpeech(sentenceData, onEnd) {
        const utterance = new SpeechSynthesisUtterance(sentenceData.text);
        utterance.rate = STATE.rate;
        utterance.pitch = STATE.pitch;
        utterance.volume = STATE.volume;

        if (STATE.selectedVoice) {
            const voices = speechSynthesis.getVoices();
            const v = voices.find(v => v.name === STATE.selectedVoice);
            if (v) utterance.voice = v;
        }

        if (STATE.wordHighlight) {
            utterance.onboundary = (event) => {
                if (event.name === 'word') {
                    const wordElements = sentenceData.el.querySelectorAll('.docreader-word');
                    wordElements.forEach(w => w.classList.remove('active-word'));
                    
                    const charIdx = event.charIndex;
                    const text = sentenceData.text;
                    let wordCount = 0;
                    let i = 0;
                    while (i < charIdx) {
                        if (/\s/.test(text[i])) {
                            while (i < charIdx && /\s/.test(text[i])) i++;
                            wordCount++;
                        } else {
                            i++;
                        }
                    }
                    if (wordElements[wordCount]) {
                        wordElements[wordCount].classList.add('active-word');
                    }
                    _updateReadAlongHud(sentenceData, wordCount);
                }
            };
        }

        utterance.onend = () => {
            STATE.utterance = null;
            if (onEnd) onEnd(false);
        };

        utterance.onerror = (e) => {
            if (e.error !== 'interrupted' && e.error !== 'canceled') {
                console.error('[DocReader] Browser TTS error:', e.error);
            }
            STATE.utterance = null;
            if (onEnd) onEnd(true);
        };

        STATE.utterance = utterance;
        speechSynthesis.speak(utterance);
    }

    // ── Cache Key Helper ─────────────────────────────────────────────────────
    function _getAudioCacheKey(index, sentenceData) {
        const text = sentenceData && sentenceData.text ? sentenceData.text.trim() : '';
        const path = STATE.currentPath || 'doc';
        const preset = STATE.hecosPresetId || 'current';
        const rate = STATE.rate || 1.0;
        return `${path}:::${preset}:::${rate}:::${index}:::${text}`;
    }

    // ── Mode B: Hecos Neural TTS (Local Kokoro / XTTS2 / Fish Speech) ─────────
    async function _speakWithHecosLocal(index, sentenceData, onEnd) {
        if (!STATE.isReading) return;

        const cacheKey = _getAudioCacheKey(index, sentenceData);
        let audioUrl = STATE._audioCache.get(cacheKey);
        if (!audioUrl) {
            _updateStatus('loading', 'Synthesizing voice...');
            try {
                const res = await fetch('/hecos/api/plugins/document_reader/tts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: sentenceData.text,
                        preset_id: STATE.hecosPresetId || 'current',
                        rate: STATE.rate || 1.0
                    })
                });
                if (!res.ok) throw new Error('TTS server status ' + res.status);
                const data = await res.json();
                if (!data.ok || !data.audio_url) throw new Error(data.error || 'No audio returned');
                audioUrl = data.audio_url;
                STATE._audioCache.set(cacheKey, audioUrl);
            } catch (err) {
                console.warn('[DocReader] Hecos TTS error:', err);
                _updateStatus('error', 'Voice synthesis error, continuing...');
                setTimeout(() => {
                    if (STATE.isReading && onEnd) onEnd(false);
                }, 1000);
                return;
            }
        }

        if (!STATE.isReading) return;

        const audio = new Audio(audioUrl);
        audio.playbackRate = STATE.rate || 1.0;
        audio.volume = STATE.volume !== undefined ? STATE.volume : 1.0;
        STATE._currentAudio = audio;

        audio.onplay = () => {
            _updateStatus('reading', 'Reading (Hecos Local)...');
            // Pre-fetch next sentence for gapless audio flow
            _prefetchNextSentence(index + 1);
        };

        audio.onended = () => {
            STATE._currentAudio = null;
            if (onEnd) onEnd(false);
        };

        audio.onerror = (e) => {
            console.warn('[DocReader] Audio play error:', e);
            STATE._currentAudio = null;
            if (onEnd) onEnd(false);
        };

        audio.play().catch(err => {
            console.warn('[DocReader] Play error:', err);
            STATE._currentAudio = null;
            if (onEnd) onEnd(false);
        });
    }

    // ── Pre-fetch Next Sentence Audio in Background ──────────────────────────
    async function _prefetchNextSentence(nextIdx) {
        if (nextIdx >= STATE.sentences.length) return;
        if (STATE.voiceSource !== 'hecos') return;
        const nextSentence = STATE.sentences[nextIdx];
        if (!nextSentence || !nextSentence.text) return;

        const cacheKey = _getAudioCacheKey(nextIdx, nextSentence);
        if (STATE._audioCache.has(cacheKey)) return;
        if (STATE._prefetchSet.has(cacheKey)) return;

        STATE._prefetchSet.add(cacheKey);

        try {
            const res = await fetch('/hecos/api/plugins/document_reader/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: nextSentence.text,
                    preset_id: STATE.hecosPresetId || 'current',
                    rate: STATE.rate || 1.0
                })
            });
            if (res.ok) {
                const data = await res.json();
                if (data.ok && data.audio_url) {
                    STATE._audioCache.set(cacheKey, data.audio_url);
                }
            }
        } catch (e) {
            // Silently ignore prefetch errors
        } finally {
            STATE._prefetchSet.delete(cacheKey);
        }
    }

    // ── Read single word ─────────────────────────────────────────────────────
    function _readSingleWord(word) {
        if (!word) return;
        if (STATE.voiceSource === 'browser') {
            speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(word);
            utterance.rate = STATE.rate;
            utterance.pitch = STATE.pitch;
            utterance.volume = STATE.volume;
            if (STATE.selectedVoice) {
                const voices = speechSynthesis.getVoices();
                const v = voices.find(v => v.name === STATE.selectedVoice);
                if (v) utterance.voice = v;
            }
            STATE.isReading = true;
            utterance.onend = () => { STATE.isReading = false; };
            utterance.onerror = () => { STATE.isReading = false; };
            speechSynthesis.speak(utterance);
        } else {
            if (STATE._currentAudio) {
                try { STATE._currentAudio.pause(); } catch (e) {}
                STATE._currentAudio = null;
            }
            STATE.isReading = true;
            fetch('/hecos/api/plugins/document_reader/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: word,
                    preset_id: STATE.hecosPresetId || 'current',
                    rate: STATE.rate || 1.0
                })
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok && data.audio_url) {
                    const audio = new Audio(data.audio_url);
                    audio.playbackRate = STATE.rate || 1.0;
                    audio.volume = STATE.volume !== undefined ? STATE.volume : 1.0;
                    STATE._currentAudio = audio;
                    audio.onended = () => { STATE._currentAudio = null; STATE.isReading = false; };
                    audio.onerror = () => { STATE._currentAudio = null; STATE.isReading = false; };
                    audio.play().catch(e => { STATE.isReading = false; console.warn(e); });
                } else {
                    STATE.isReading = false;
                }
            })
            .catch(e => {
                STATE.isReading = false;
                console.warn('[DocReader] Word TTS error:', e);
            });
        }
    }

    // ── Public API ───────────────────────────────────────────────────────────
    window.DocReader = {
        // Open the reader with a document path
        open: async function(filePath) {
            if (!filePath) {
                console.error('[DocReader] open called with empty filePath');
                return;
            }

            // Clean, unwrap, and sanitize filePath
            if (typeof filePath === 'string') {
                filePath = filePath.trim();
                while (filePath.includes('?path=')) {
                    try {
                        const u = new URL(filePath, window.location.origin);
                        const p = u.searchParams.get('path');
                        if (p) filePath = decodeURIComponent(p);
                        else break;
                    } catch(e) {
                        const m = filePath.match(/[?&]path=([^&]+)/);
                        if (m) filePath = decodeURIComponent(m[1]);
                        else break;
                    }
                }
                if (filePath.startsWith('file:///')) {
                    filePath = decodeURIComponent(filePath.substring(8));
                } else if (filePath.startsWith('file://')) {
                    filePath = decodeURIComponent(filePath.substring(7));
                }
                filePath = filePath.replace(/\\/g, '/');
            }

            // 1. Immediately stop current playback and clear all caches
            this.stop();
            STATE._audioCache.clear();
            STATE._prefetchSet.clear();
            STATE.sentences = [];
            STATE.pages = [];
            if (STATE.pdfDoc && typeof STATE.pdfDoc.destroy === 'function') {
                try { STATE.pdfDoc.destroy(); } catch(e) {}
                STATE.pdfDoc = null;
            }

            // 2. Establish fresh document session ID to discard any in-flight async tasks
            const sessionId = Date.now();
            STATE._sessionId = sessionId;
            STATE.currentPath = filePath;
            STATE.isOpen = true;
            STATE.currentIndex = 0;

            const overlay = _createOverlay();
            overlay.classList.add('active');

            // Set clean filename
            let filename = filePath.split('/').pop() || 'document.pdf';
            let displayFilename = filename;
            if (/^[A-Za-z]:/i.test(displayFilename)) {
                displayFilename = displayFilename.substring(2);
                const lastUnder = displayFilename.lastIndexOf('documents');
                if (lastUnder !== -1) {
                    displayFilename = displayFilename.substring(lastUnder + 9);
                }
            }
            const filenameEl = document.getElementById('docreader-filename');
            if (filenameEl) filenameEl.textContent = displayFilename || filename;

            // Immediately reset content & TOC DOM to prevent showing previous document
            const contentEl = document.getElementById('docreader-content');
            const tocEl = document.getElementById('docreader-toc');
            if (tocEl) tocEl.innerHTML = '';
            if (contentEl) {
                contentEl.innerHTML = `
                    <div class="docreader-loading" id="docreader-loading">
                        <div class="docreader-spinner"></div>
                        <div class="docreader-loading-text">Loading document...</div>
                    </div>
                `;
            }

            try {
                const ext = (filename.match(/\.([a-z0-9]+)$/i) || ['', 'pdf'])[1].toLowerCase();
                const cleanFile = filePath.split('#')[0];
                const hash = filePath.includes('#') ? ('#' + filePath.split('#')[1]) : '';
                const sep = cleanFile.includes('?') ? '&' : '?';
                const apiUrl = (cleanFile.startsWith('http://') || cleanFile.startsWith('https://'))
                    ? `${cleanFile}${sep}_t=${sessionId}${hash}`
                    : `/api/local_file?path=${encodeURIComponent(cleanFile)}&_t=${sessionId}${hash}`;
                
                let docData;
                if (ext === 'pdf') {
                    docData = await loadPDFDocument(apiUrl, sessionId);
                } else {
                    docData = await loadTextDocument(apiUrl, ext, filePath);
                }

                if (STATE._sessionId !== sessionId) return;

                if (!docData || !docData.pages || docData.pages.length === 0) {
                    contentEl.innerHTML = `
                        <div class="docreader-loading">
                            <i class="fas fa-exclamation-triangle" style="font-size:2em; color:#fbbf24;"></i>
                            <div class="docreader-loading-text">No content found in this document.</div>
                        </div>
                    `;
                    return;
                }

                STATE.pages = docData.pages;
                STATE.docData = docData;
                STATE.pdfDoc = docData.pdfDoc || null;
                _renderContent(docData, sessionId);
                _updateStatus('ready', 'Ready');

            } catch (e) {
                if (STATE._sessionId !== sessionId) return;
                console.error('[DocReader] Failed to load document:', e);
                contentEl.innerHTML = `
                    <div class="docreader-loading">
                        <i class="fas fa-exclamation-triangle" style="font-size:2em; color:#ef4444;"></i>
                        <div class="docreader-loading-text">Failed to load document: ${e.message}</div>
                    </div>
                `;
            }
        },

        close: function() {
            this.stop();
            STATE._sessionId = Date.now();
            STATE._audioCache.clear();
            STATE._prefetchSet.clear();
            const overlay = document.getElementById('docreader-overlay');
            if (overlay) overlay.classList.remove('active');
            STATE.isOpen = false;
            STATE.sentences = [];
            STATE.pages = [];
            STATE.currentPath = null;
            if (STATE.pdfDoc && typeof STATE.pdfDoc.destroy === 'function') {
                try { STATE.pdfDoc.destroy(); } catch (e) {}
                STATE.pdfDoc = null;
            }
            const contentEl = document.getElementById('docreader-content');
            if (contentEl) contentEl.innerHTML = '';
            const tocEl = document.getElementById('docreader-toc');
            if (tocEl) tocEl.innerHTML = '';
            const tooltip = document.getElementById('docreader-selection-tooltip');
            if (tooltip) tooltip.classList.remove('visible');
            const hud = document.getElementById('docreader-readalong-hud');
            if (hud) hud.classList.remove('visible');
            document.querySelectorAll('.docreader-page-card.reading-page').forEach(c => c.classList.remove('reading-page'));
        },

        // Play/Pause toggle
        togglePlayPause: function() {
            if (STATE.isReading && !STATE.isPaused) {
                // Pause
                if (STATE.voiceSource === 'browser') {
                    speechSynthesis.pause();
                } else if (STATE._currentAudio) {
                    STATE._currentAudio.pause();
                }
                STATE.isPaused = true;
                _updatePlayBtn();
                _updateStatus('paused', 'Paused');
            } else if (STATE.isPaused) {
                // Resume
                if (STATE.voiceSource === 'browser') {
                    speechSynthesis.resume();
                } else if (STATE._currentAudio) {
                    STATE._currentAudio.play().catch(e => console.warn(e));
                }
                STATE.isPaused = false;
                _updatePlayBtn();
                _updateStatus('reading', 'Reading...');
            } else {
                // Start reading from current position
                this.readFromIndex(STATE.currentIndex);
            }
        },

        // Stop reading
        stop: function() {
            speechSynthesis.cancel();
            if (STATE._currentAudio) {
                try {
                    STATE._currentAudio.pause();
                    STATE._currentAudio.currentTime = 0;
                } catch (e) {}
                STATE._currentAudio = null;
            }
            STATE.isReading = false;
            STATE.isPaused = false;
            STATE.utterance = null;
            _highlightSentence(-1, true);
            _updatePlayBtn();
            _updateStatus('ready', 'Ready');
            const hud = document.getElementById('docreader-readalong-hud');
            if (hud) hud.classList.remove('visible');
            document.querySelectorAll('.docreader-page-card.reading-page').forEach(c => c.classList.remove('reading-page'));
        },

        // Read from a specific sentence index
        readFromIndex: function(index) {
            this.stop();
            STATE.isReading = true;
            STATE.currentIndex = index;
            _updatePlayBtn();
            _updateStatus('reading', 'Reading...');

            const readNext = (idx) => {
                if (!STATE.isReading || idx >= STATE.sentences.length) {
                    this.stop();
                    return;
                }
                STATE.currentIndex = idx;
                _speakSentence(idx, (done) => {
                    if (!done && STATE.isReading) {
                        readNext(idx + 1);
                    } else if (done) {
                        this.stop();
                    }
                });
            };

            readNext(index);
        },

        // Previous sentence
        prevSentence: function() {
            const wasReading = STATE.isReading;
            this.stop();
            STATE.currentIndex = Math.max(0, STATE.currentIndex - 1);
            _highlightSentence(STATE.currentIndex);
            _updateProgress();
            if (wasReading) {
                this.readFromIndex(STATE.currentIndex);
            }
        },

        // Next sentence
        nextSentence: function() {
            const wasReading = STATE.isReading;
            this.stop();
            STATE.currentIndex = Math.min(STATE.sentences.length - 1, STATE.currentIndex + 1);
            _highlightSentence(STATE.currentIndex);
            _updateProgress();
            if (wasReading) {
                this.readFromIndex(STATE.currentIndex);
            }
        },

        // Read selected text
        readSelection: function() {
            const text = STATE._selectedText;
            if (!text) return;

            this.stop();
            STATE.isReading = true;
            if (STATE.voiceSource === 'browser') {
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.rate = STATE.rate;
                utterance.pitch = STATE.pitch;
                utterance.volume = STATE.volume;
                if (STATE.selectedVoice) {
                    const voices = speechSynthesis.getVoices();
                    const v = voices.find(v => v.name === STATE.selectedVoice);
                    if (v) utterance.voice = v;
                }
                utterance.onstart = () => _updateStatus('reading', 'Reading selection...');
                utterance.onend = () => { STATE.isReading = false; _updateStatus('ready', 'Ready'); };
                utterance.onerror = () => { STATE.isReading = false; _updateStatus('ready', 'Ready'); };
                speechSynthesis.speak(utterance);
            } else {
                _updateStatus('loading', 'Synthesizing selection...');
                fetch('/hecos/api/plugins/document_reader/tts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: text,
                        preset_id: STATE.hecosPresetId || 'current',
                        rate: STATE.rate || 1.0
                    })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.ok && data.audio_url) {
                        const audio = new Audio(data.audio_url);
                        audio.playbackRate = STATE.rate || 1.0;
                        audio.volume = STATE.volume !== undefined ? STATE.volume : 1.0;
                        STATE._currentAudio = audio;
                        audio.onplay = () => _updateStatus('reading', 'Reading selection (Hecos Local)...');
                        audio.onended = () => { STATE._currentAudio = null; STATE.isReading = false; _updateStatus('ready', 'Ready'); };
                        audio.onerror = () => { STATE._currentAudio = null; STATE.isReading = false; _updateStatus('ready', 'Ready'); };
                        audio.play().catch(e => { STATE.isReading = false; console.warn(e); });
                    } else {
                        STATE.isReading = false;
                        _updateStatus('error', 'Synthesis failed');
                    }
                })
                .catch(err => {
                    STATE.isReading = false;
                    console.error('[DocReader] Selection TTS error:', err);
                    _updateStatus('error', 'Synthesis error');
                });
            }

            const tooltip = document.getElementById('docreader-selection-tooltip');
            if (tooltip) tooltip.classList.remove('visible');
        },

        // Read from the selection point to end
        readFromHere: function() {
            const sel = window.getSelection();
            if (!sel.rangeCount) return;

            const range = sel.getRangeAt(0);
            const startNode = range.startContainer;

            // Find the sentence element containing the selection
            let sentenceEl = startNode.nodeType === Node.TEXT_NODE 
                ? startNode.parentElement 
                : startNode;
            while (sentenceEl && !sentenceEl.classList?.contains('docreader-sentence')) {
                sentenceEl = sentenceEl.parentElement;
            }

            if (sentenceEl && sentenceEl.dataset.sentenceIdx !== undefined) {
                const idx = parseInt(sentenceEl.dataset.sentenceIdx);
                this.readFromIndex(idx);
            }

            const tooltip = document.getElementById('docreader-selection-tooltip');
            if (tooltip) tooltip.classList.remove('visible');
        },

        // Seek via progress bar click
        seekProgress: function(e) {
            const bar = document.getElementById('docreader-progress-bar');
            if (!bar || STATE.sentences.length === 0) return;
            
            const rect = bar.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            const idx = Math.floor(pct * STATE.sentences.length);
            
            const wasReading = STATE.isReading;
            this.stop();
            STATE.currentIndex = Math.max(0, Math.min(STATE.sentences.length - 1, idx));
            _highlightSentence(STATE.currentIndex);
            _updateProgress();
            
            if (wasReading) {
                this.readFromIndex(STATE.currentIndex);
            }
        },

        // Speed control
        cycleSpeed: function() {
            const speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0];
            const currentIdx = speeds.indexOf(STATE.rate);
            STATE.rate = speeds[(currentIdx + 1) % speeds.length];
            
            const btn = document.getElementById('docreader-speed-btn');
            if (btn) btn.textContent = STATE.rate + '×';
            
            if (STATE.voiceSource === 'hecos' && STATE._currentAudio) {
                STATE._currentAudio.playbackRate = STATE.rate;
            } else if (STATE.isReading && !STATE.isPaused) {
                const idx = STATE.currentIndex;
                this.stop();
                this.readFromIndex(idx);
            }
        },

        // Voice Source change (Current Hecos Voice, Preset, or Browser voice)
        changeVoiceSource: function(val) {
            if (val === 'hecos_current') {
                STATE.voiceSource = 'hecos';
                STATE.hecosPresetId = 'current';
            } else if (val === 'hecos_preset') {
                STATE.voiceSource = 'hecos';
                if (!STATE.hecosPresetId || STATE.hecosPresetId === 'current') {
                    if (STATE.availablePresets.length > 0) {
                        STATE.hecosPresetId = STATE.availablePresets[0].id;
                    }
                }
            } else if (val.startsWith('browser:')) {
                STATE.voiceSource = 'browser';
                STATE.selectedVoice = val.replace('browser:', '');
            }
            STATE._audioCache.clear();
            STATE._prefetchSet.clear();
            _syncVoiceUI();

            if (STATE.isReading && !STATE.isPaused) {
                const idx = STATE.currentIndex;
                this.stop();
                this.readFromIndex(idx);
            }
        },

        // Specific Hecos Preset change
        changeHecosPreset: function(presetId) {
            STATE.voiceSource = 'hecos';
            STATE.hecosPresetId = presetId;
            STATE._audioCache.clear();
            STATE._prefetchSet.clear();
            _syncVoiceUI();

            if (STATE.isReading && !STATE.isPaused) {
                const idx = STATE.currentIndex;
                this.stop();
                this.readFromIndex(idx);
            }
        },

        // Backward compatibility
        changeVoice: function(voiceName) {
            if (voiceName.startsWith('browser:') || voiceName.startsWith('hecos_')) {
                this.changeVoiceSource(voiceName);
            } else {
                this.changeVoiceSource('browser:' + voiceName);
            }
        },

        // Volume change
        changeVolume: function(val) {
            STATE.volume = parseFloat(val);
            if (STATE._currentAudio) {
                STATE._currentAudio.volume = STATE.volume;
            }
        },

        // Font size & Visual Zoom
        changeFontSize: function(delta) {
            STATE.fontSize = Math.max(0.7, Math.min(2.5, STATE.fontSize + delta));
            STATE.visualZoom = Math.max(0.5, Math.min(2.5, (STATE.visualZoom || 1.0) + delta));
            const content = document.getElementById('docreader-content');
            if (content) content.style.fontSize = STATE.fontSize + 'em';

            // Also scale canvases in visual mode
            document.querySelectorAll('.docreader-pdf-canvas').forEach(canvas => {
                const baseW = parseFloat(canvas.dataset.baseWidth);
                const baseH = parseFloat(canvas.dataset.baseHeight);
                if (baseW && baseH) {
                    canvas.style.width = Math.floor(baseW * STATE.visualZoom) + 'px';
                    canvas.style.height = Math.floor(baseH * STATE.visualZoom) + 'px';
                }
            });
        },

        // Switch View Mode: 'visual' | 'split' | 'text'
        setViewMode: function(mode) {
            if (!['visual', 'split', 'text'].includes(mode)) return;
            STATE.viewMode = mode;
            const container = document.getElementById('docreader-pages-container');
            if (container) {
                container.className = `docreader-pages-container docreader-view-${mode}`;
            }
            document.querySelectorAll('.docreader-view-btn').forEach(btn => {
                btn.classList.toggle('active', btn.id === `docreader-mode-${mode}`);
            });
            // Auto scroll to current reading position or active page
            if (STATE.sentences[STATE.currentIndex]) {
                _highlightSentence(STATE.currentIndex);
            }
        },

        // Toggle sidebar
        toggleSidebar: function() {
            STATE.sidebarOpen = !STATE.sidebarOpen;
            const sidebar = document.getElementById('docreader-sidebar');
            if (sidebar) sidebar.classList.toggle('open', STATE.sidebarOpen);
        },

        // Status queries for system & shortcuts
        isReading: function() {
            return !!(STATE.isReading && !STATE.isPaused);
        },

        isOpen: function() {
            return !!STATE.isOpen;
        },
    };

    // ── Load CSS ─────────────────────────────────────────────────────────────
    function _ensureCSS() {
        if (document.getElementById('docreader-css')) return;
        const link = document.createElement('link');
        link.id = 'docreader-css';
        link.rel = 'stylesheet';
        link.href = '/hpm_plugin/document_reader/static/css/document_reader.css';
        document.head.appendChild(link);
    }

    _ensureCSS();

    // ── Listen for SSE events from the backend ───────────────────────────────
    // The backend can send "document_reader_open" events to trigger the reader
    if (window.addEventListener) {
        window.addEventListener('hecos_sse', function(e) {
            if (!e.detail) return;
            if (e.detail.type === 'document_reader_open' && e.detail.path) {
                window.DocReader.open(e.detail.path);
            } else if (e.detail.type === 'document_reader_stop') {
                window.DocReader.stop();
            }
        });
    }

})();
