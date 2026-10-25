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
        hecosPresetId: 'current', // 'current' | specific GP preset ID
        audioEngine: 'auto',    // 'auto' | 'kokoro' | 'piper' | 'xtts2' | 'fish_speech' | 'browser'
        audioPreset: '',        // audio config preset name (e.g. 'Standard & Balanced')
        audioVoice: 'default',  // voice id / model name (e.g. 'im_base_man')
        audioPresetsMap: {},    // { kokoro: [...], xtts2: [...], fish_speech: [...] }
        audioVoicesMap: {},     // { kokoro: {...}, piper: {...}, xtts2: {...}, fish_speech: {...} }
        systemActiveEngine: 'kokoro',
        selectedVoice: null,    // Browser voice name (when voiceSource === 'browser')
        fontSize: 1.1,          // em (used in text mode)
        visualZoom: 1.0,        // zoom factor for canvas (used in visual mode)
        viewMode: 'visual',     // 'visual' | 'split' | 'text'
        docType: 'pdf',         // 'pdf' | 'html' | 'md' | 'txt'
        utterance: null,
        _currentAudio: null,    // HTML5 Audio instance for Hecos local TTS
        _audioCache: new Map(), // sentenceIndex -> audioUrl
        _prefetchSet: new Set(),// Indices currently being pre-fetched
        _synthesisInterval: null, // Timer interval for cold load TTS progress
        _loadedEngines: new Set(),// Tracks engines/presets already loaded in memory
        _pendingEngineSwitch: false, // Flag when switching to a different preset
        availablePresets: [],   // Hecos GP presets list from backend
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
                    <div class="docreader-progress-bar" id="docreader-progress-bar" onclick="window.DocReader.seekProgress(event)" title="Document Progress (Click to Seek)">
                        <div class="docreader-audio-buffer-fill" id="docreader-audio-buffer-fill"></div>
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
                    <div class="docreader-control-group docreader-speed-group" id="docreader-speed-group" title="Speed: Drag slider, scroll mouse wheel, or use keyboard arrows (0.5× – 3.0×)">
                        <span class="docreader-control-label" title="Reading speed"><i class="fas fa-tachometer-alt"></i></span>
                        <input type="range" class="docreader-speed-slider" id="docreader-speed-slider" 
                               min="0.5" max="3.0" step="0.05" value="1.0"
                               oninput="window.DocReader.changeSpeed(this.value)"
                               title="Reading Speed: 0.5× to 3.0× (Step 0.05)">
                        <button class="docreader-speed-badge" id="docreader-speed-badge" 
                                onclick="window.DocReader.resetSpeed()" 
                                title="Click to reset to 1.00× (or scroll wheel to adjust)">1.00×</button>
                    </div>

                    <!-- Global Preset (GP) -->
                    <div class="docreader-control-group docreader-gp-group" id="docreader-preset-group" title="Global Preset (AI Soul / Persona Profile)">
                        <span class="docreader-control-label" title="Global Preset (AI Soul / Persona Profile)">GP</span>
                        <select class="docreader-preset-select" id="docreader-preset-select" onchange="window.DocReader.changeHecosPreset(this.value)" title="Global Preset: Select AI Soul / Character Persona">
                            <option value="current">Active Chat GP</option>
                        </select>
                    </div>

                    <!-- TTS Audio Engine -->
                    <div class="docreader-control-group docreader-engine-group" title="Text-to-Speech Engine">
                        <span class="docreader-control-label" title="TTS Audio Engine">Engine</span>
                        <select class="docreader-engine-select" id="docreader-engine-select" onchange="window.DocReader.changeAudioEngine(this.value)" title="Select Text-to-Speech Engine">
                            <option value="auto">⚡ Auto (GP/Default)</option>
                            <option value="kokoro">Kokoro TTS</option>
                            <option value="piper">Piper ONNX</option>
                            <option value="xtts2">XTTS v2</option>
                            <option value="fish_speech">Fish Speech</option>
                            <option value="browser">🌐 Browser Voices</option>
                        </select>
                    </div>

                    <!-- Voice / Audio Preset Selection -->
                    <div class="docreader-control-group docreader-voice-group" title="Voice or Audio Engine Preset">
                        <span class="docreader-control-label" title="Voice or Audio Engine Preset">Voice</span>
                        <select class="docreader-voice-select" id="docreader-voice-select" onchange="window.DocReader.changeVoice(this.value)" title="Select Voice or Audio Configuration Preset">
                            <option value="default">✨ Default Voice</option>
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

        // Keyboard controls when Document Reader is open (Arrows for speed/navigation, Space, ESC)
        document.addEventListener('keydown', function(e) {
            if (!STATE.isOpen) return;

            // Do not intercept if user is typing in a text input or textarea
            const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
            if (tag === 'textarea' || (tag === 'input' && e.target.type !== 'range')) {
                return;
            }

            // ESC: Stop reading on 1st press, close reader on 2nd
            if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                if (STATE.isReading) {
                    window.DocReader.stop();
                    if (window.showToast) window.showToast('🔇 Document Reader voice stopped', 'info');
                } else {
                    window.DocReader.close();
                }
                return;
            }

            // Keyboard Arrows: Speed Control (ArrowUp / ArrowDown)
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                e.stopPropagation();
                window.DocReader.changeSpeedDelta(0.05, true);
                return;
            }

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                e.stopPropagation();
                window.DocReader.changeSpeedDelta(-0.05, true);
                return;
            }

            // Keyboard Arrows: Shift + ArrowRight / ArrowLeft for Speed
            if (e.key === 'ArrowRight' && e.shiftKey) {
                e.preventDefault();
                e.stopPropagation();
                window.DocReader.changeSpeedDelta(0.05, true);
                return;
            }

            if (e.key === 'ArrowLeft' && e.shiftKey) {
                e.preventDefault();
                e.stopPropagation();
                window.DocReader.changeSpeedDelta(-0.05, true);
                return;
            }

            // Keyboard Arrows: Sentence Navigation (ArrowRight / ArrowLeft)
            // (When the speed range slider is not focused)
            if (e.target !== document.getElementById('docreader-speed-slider') && e.target !== document.getElementById('docreader-volume')) {
                if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    e.stopPropagation();
                    window.DocReader.nextSentence();
                    return;
                }
                if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    e.stopPropagation();
                    window.DocReader.prevSentence();
                    return;
                }
                if (e.code === 'Space') {
                    e.preventDefault();
                    e.stopPropagation();
                    window.DocReader.togglePlayPause();
                    return;
                }
                if (e.key === 'PageDown') {
                    e.preventDefault();
                    e.stopPropagation();
                    window.DocReader.nextPage();
                    return;
                }
                if (e.key === 'PageUp') {
                    e.preventDefault();
                    e.stopPropagation();
                    window.DocReader.prevPage();
                    return;
                }
            }
        });

        // Mouse Wheel speed and volume adjustment on controls
        const speedGroup = overlay.querySelector('#docreader-speed-group');
        if (speedGroup) {
            speedGroup.addEventListener('wheel', function(e) {
                e.preventDefault();
                e.stopPropagation();
                const delta = e.deltaY < 0 ? 0.05 : -0.05;
                window.DocReader.changeSpeedDelta(delta, false);
            }, { passive: false });
        }

        const volGroup = overlay.querySelector('#docreader-volume')?.parentElement;
        if (volGroup) {
            volGroup.addEventListener('wheel', function(e) {
                e.preventDefault();
                e.stopPropagation();
                const delta = e.deltaY < 0 ? 0.05 : -0.05;
                const newVol = Math.max(0, Math.min(1, Math.round(((STATE.volume !== undefined ? STATE.volume : 1.0) + delta) * 100) / 100));
                window.DocReader.changeVolume(newVol);
                const slider = document.getElementById('docreader-volume');
                if (slider) slider.value = newVol;
            }, { passive: false });
        }

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
        if (typeof speechSynthesis !== 'undefined' && speechSynthesis.onvoiceschanged !== undefined) {
            speechSynthesis.onvoiceschanged = _populateVoices;
        }

        return overlay;
    }

    // ── Load Hecos Presets, Audio Presets, and Voices from Backend ───────────
    async function _loadHecosPresets() {
        try {
            const res = await fetch('/hecos/api/plugins/document_reader/presets', { cache: 'no-store' });
            if (res.ok) {
                const data = await res.json();
                if (data.ok) {
                    if (Array.isArray(data.presets)) {
                        STATE.availablePresets = data.presets;
                    }
                    STATE.activePresetName = data.active_preset_name || 'Active GP';
                    STATE.systemActiveEngine = data.active_engine || 'kokoro';
                    STATE.audioPresetsMap = data.audio_presets || {};
                    STATE.audioVoicesMap = data.voices || {};

                    _populatePresetSelect();
                    _populateEngineSelect();
                    _populateVoiceAndPresetSelect();
                    return;
                }
            }
        } catch (e) {
            console.warn('[DocReader] Presets API load failed, falling back:', e);
        }

        // Fallback to /api/souls if plugin route was unavailable
        try {
            const soulsRes = await fetch('/api/souls', { cache: 'no-store' });
            if (soulsRes && soulsRes.ok) {
                const soulsData = await soulsRes.json();
                if (soulsData.ok && Array.isArray(soulsData.souls)) {
                    STATE.availablePresets = soulsData.souls.map(s => ({
                        id: s.meta.id,
                        name: s.meta.name,
                        engine: s.voice?.tts_engine ? s.voice.tts_engine.toUpperCase() : 'LOCAL',
                        voice: s.voice?.tts_voice || ''
                    }));
                    _populatePresetSelect();
                    _populateEngineSelect();
                    _populateVoiceAndPresetSelect();
                }
            }
        } catch (err) {
            console.warn('[DocReader] Fallback presets load failed:', err);
        }
    }

    function _populatePresetSelect() {
        const pSelect = document.getElementById('docreader-preset-select');
        if (!pSelect) return;
        pSelect.innerHTML = '';

        const currOpt = document.createElement('option');
        currOpt.value = 'current';
        currOpt.textContent = `✨ Active GP (${STATE.activePresetName || 'Hecos'})`;
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

    function _populateEngineSelect() {
        const eSelect = document.getElementById('docreader-engine-select');
        if (!eSelect) return;
        if (STATE.audioEngine) {
            eSelect.value = STATE.audioEngine;
        }
    }

    function _populateVoiceAndPresetSelect() {
        const vSelect = document.getElementById('docreader-voice-select');
        if (!vSelect) return;
        vSelect.innerHTML = '';

        const engine = STATE.audioEngine || 'auto';

        if (engine === 'browser') {
            const group = document.createElement('optgroup');
            group.label = "Browser Voices (Web Speech)";
            const voices = (typeof speechSynthesis !== 'undefined') ? speechSynthesis.getVoices() : [];
            if (voices && voices.length > 0) {
                const priority = ['it', 'en', 'es', 'fr', 'de', 'pt'];
                const sorted = [...voices].sort((a, b) => {
                    const aLang = a.lang.split('-')[0].toLowerCase();
                    const bLang = b.lang.split('-')[0].toLowerCase();
                    const aIdx = priority.indexOf(aLang);
                    const bIdx = priority.indexOf(bLang);
                    if (aIdx !== -1 && bIdx !== -1) return aIdx - bIdx;
                    if (aIdx !== -1) return -1;
                    if (bIdx !== -1) return 1;
                    return a.name.localeCompare(b.name);
                });
                sorted.forEach(v => {
                    const opt = document.createElement('option');
                    opt.value = 'browser:' + v.name;
                    opt.textContent = `${v.name} (${v.lang})`;
                    group.appendChild(opt);
                });
            } else {
                const opt = document.createElement('option');
                opt.value = 'browser:default';
                opt.textContent = "Browser Default Voice";
                group.appendChild(opt);
            }
            vSelect.appendChild(group);

            if (STATE.selectedVoice) {
                vSelect.value = 'browser:' + STATE.selectedVoice;
            }
            return;
        }

        // For Neural / Local Engines:
        // 1. Default Option
        const defaultOpt = document.createElement('option');
        defaultOpt.value = 'default';
        if (engine === 'auto') {
            defaultOpt.textContent = `✨ Default Voice (Auto: ${STATE.systemActiveEngine || 'Kokoro'})`;
        } else {
            defaultOpt.textContent = `✨ Default Voice (${engine.toUpperCase()})`;
        }
        vSelect.appendChild(defaultOpt);

        // 2. Audio Configuration Presets (for kokoro, xtts2, fish_speech)
        const presets = (STATE.audioPresetsMap && STATE.audioPresetsMap[engine]) || [];
        if (presets.length > 0) {
            const pGroup = document.createElement('optgroup');
            pGroup.label = `${engine.toUpperCase()} Audio Presets`;
            presets.forEach(pName => {
                const opt = document.createElement('option');
                opt.value = 'preset:' + pName;
                opt.textContent = `🎙️ ${pName}`;
                pGroup.appendChild(opt);
            });
            vSelect.appendChild(pGroup);
        }

        // 3. Voices / Cloned Models
        const voicesObj = (STATE.audioVoicesMap && STATE.audioVoicesMap[engine]) || {};
        const voiceKeys = Object.keys(voicesObj);
        if (voiceKeys.length > 0) {
            const vGroup = document.createElement('optgroup');
            vGroup.label = `${engine.toUpperCase()} Voices & Clones`;
            voiceKeys.forEach(vId => {
                const opt = document.createElement('option');
                opt.value = 'voice:' + vId;
                const vLabel = voicesObj[vId] || vId;
                opt.textContent = (vLabel.startsWith('🎭') || vLabel.startsWith('✨')) ? vLabel : `🗣️ ${vLabel}`;
                vGroup.appendChild(opt);
            });
            vSelect.appendChild(vGroup);
        }

        // If engine is 'auto', also show Kokoro presets & Piper voices as quick optgroups
        if (engine === 'auto') {
            const kPresets = (STATE.audioPresetsMap && STATE.audioPresetsMap.kokoro) || [];
            if (kPresets.length > 0) {
                const kpGroup = document.createElement('optgroup');
                kpGroup.label = "Kokoro Audio Presets";
                kPresets.forEach(pName => {
                    const opt = document.createElement('option');
                    opt.value = 'preset:' + pName;
                    opt.textContent = `🎙️ ${pName}`;
                    kpGroup.appendChild(opt);
                });
                vSelect.appendChild(kpGroup);
            }

            const kVoices = (STATE.audioVoicesMap && STATE.audioVoicesMap.kokoro) || {};
            const kKeys = Object.keys(kVoices);
            if (kKeys.length > 0) {
                const kvGroup = document.createElement('optgroup');
                kvGroup.label = "Kokoro Voices";
                kKeys.forEach(vId => {
                    const opt = document.createElement('option');
                    opt.value = 'voice:' + vId;
                    opt.textContent = kVoices[vId] || vId;
                    kvGroup.appendChild(opt);
                });
                vSelect.appendChild(kvGroup);
            }

            const piperVoices = (STATE.audioVoicesMap && STATE.audioVoicesMap.piper) || {};
            const pKeys = Object.keys(piperVoices);
            if (pKeys.length > 0) {
                const ppGroup = document.createElement('optgroup');
                ppGroup.label = "Piper Voices";
                pKeys.forEach(vId => {
                    const opt = document.createElement('option');
                    opt.value = 'voice:' + vId;
                    opt.textContent = piperVoices[vId] || vId;
                    ppGroup.appendChild(opt);
                });
                vSelect.appendChild(ppGroup);
            }
        }

        // Restore selection
        if (STATE.audioPreset) {
            vSelect.value = 'preset:' + STATE.audioPreset;
        } else if (STATE.audioVoice && STATE.audioVoice !== 'default') {
            vSelect.value = 'voice:' + STATE.audioVoice;
        } else {
            vSelect.value = 'default';
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
            if (cfg.audio_engine) STATE.audioEngine = cfg.audio_engine;
            if (cfg.audio_preset) STATE.audioPreset = cfg.audio_preset;
            if (cfg.audio_voice) STATE.audioVoice = cfg.audio_voice;
            if (cfg.default_voice) STATE.selectedVoice = cfg.default_voice;
            if (cfg.default_rate) STATE.rate = parseFloat(cfg.default_rate);
            if (cfg.default_pitch) STATE.pitch = parseFloat(cfg.default_pitch);
            if (cfg.default_volume) STATE.volume = parseFloat(cfg.default_volume);
            if (cfg.highlight_color) {
                document.documentElement.style.setProperty('--docreader-highlight-color', cfg.highlight_color);
            }
            if (typeof cfg.word_highlight === 'boolean') STATE.wordHighlight = cfg.word_highlight;

            // Update UI elements to reflect config
            _updateSpeedUI(STATE.rate);
            const volSlider = document.getElementById('docreader-volume');
            if (volSlider) volSlider.value = STATE.volume;

            _syncVoiceUI();
        } catch (e) {
            console.warn('[DocReader] Failed to load config:', e);
        }
    }

    // ── Save User Config ─────────────────────────────────────────────────────
    async function _saveConfig() {
        try {
            await fetch('/hecos/api/plugins/document_reader/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    voice_source: STATE.voiceSource,
                    hecos_preset: STATE.hecosPresetId,
                    audio_engine: STATE.audioEngine,
                    audio_preset: STATE.audioPreset,
                    audio_voice: STATE.audioVoice,
                    default_voice: STATE.selectedVoice,
                    default_rate: STATE.rate,
                    default_pitch: STATE.pitch,
                    default_volume: STATE.volume
                })
            });
        } catch (e) {
            console.warn('[DocReader] Failed to save config:', e);
        }
    }

    // ── Speed Formatting and UI Helpers ──────────────────────────────────────
    function _formatSpeed(val) {
        const num = parseFloat(val);
        if (isNaN(num)) return '1.00×';
        return num.toFixed(2) + '×';
    }

    function _updateSpeedUI(val) {
        const speedSlider = document.getElementById('docreader-speed-slider');
        if (speedSlider) speedSlider.value = val;
        const speedBadge = document.getElementById('docreader-speed-badge');
        if (speedBadge) speedBadge.textContent = _formatSpeed(val);
        const oldBtn = document.getElementById('docreader-speed-btn');
        if (oldBtn) oldBtn.textContent = _formatSpeed(val);
    }

    // ── Sync UI Selects with State ───────────────────────────────────────────
    function _syncVoiceUI() {
        _populateEngineSelect();
        _populatePresetSelect();
        _populateVoiceAndPresetSelect();
    }

    // ── Populate TTS voices ──────────────────────────────────────────────────
    function _populateVoices() {
        if (STATE.audioEngine === 'browser') {
            _populateVoiceAndPresetSelect();
        }
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
            else if (status === 'synthesizing' || status === 'loading') dot.classList.add('synthesizing');
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

    // ── Cold Load / Preset Switch Progress Tracker ───────────────────────────
    function _getCurrentEngineKey() {
        if (STATE.voiceSource === 'browser') {
            return 'browser:' + (STATE.selectedVoice || 'default');
        }
        const eng = STATE.audioEngine || 'auto';
        const ap = STATE.audioPreset || '';
        const v = STATE.audioVoice || 'default';
        const gp = STATE.hecosPresetId || 'current';
        return `hecos:${eng}:${ap}:${v}:${gp}`;
    }

    function _getActiveEngineName() {
        if (STATE.voiceSource === 'browser') return 'Browser Voice (' + (STATE.selectedVoice || 'Default') + ')';
        if (STATE.audioPreset) return `${(STATE.audioEngine || 'TTS').toUpperCase()} · ${STATE.audioPreset}`;
        if (STATE.audioVoice && STATE.audioVoice !== 'default') return `${(STATE.audioEngine || 'TTS').toUpperCase()} · ${STATE.audioVoice}`;
        if (STATE.audioEngine && STATE.audioEngine !== 'auto') return `${STATE.audioEngine.toUpperCase()} Voice`;
        if (STATE.availablePresets && STATE.hecosPresetId && STATE.hecosPresetId !== 'current') {
            const found = STATE.availablePresets.find(p => p.id === STATE.hecosPresetId);
            if (found && found.name) return found.name;
        }
        return STATE.activePresetName || 'Hecos Neural';
    }

    function _clearColdLoadTracker() {
        if (STATE._synthesisInterval) {
            clearInterval(STATE._synthesisInterval);
            STATE._synthesisInterval = null;
        }
    }

    function _startColdLoadTracker() {
        _clearColdLoadTracker();

        const engineLabel = _getActiveEngineName();
        const bufferEl = document.getElementById('docreader-audio-buffer-fill');
        const barEl = document.getElementById('docreader-progress-bar');
        if (bufferEl) {
            bufferEl.classList.add('loading-engine');
            bufferEl.style.width = '10%';
        }
        if (barEl) barEl.classList.add('synthesizing');

        _updateStatus('loading', `Caricamento ${engineLabel}...`);

        let currentPct = 10;
        let elapsedMs = 0;
        const intervalMs = 120;

        STATE._synthesisInterval = setInterval(() => {
            elapsedMs += intervalMs;
            if (elapsedMs < 600) {
                currentPct = Math.min(30, currentPct + 4);
                _updateStatus('loading', `Caricamento ${engineLabel}... (${Math.round(currentPct)}%)`);
            } else if (elapsedMs < 4000) {
                currentPct = Math.min(75, currentPct + 2.5);
                _updateStatus('loading', `Inizializzazione modello in RAM... (${Math.round(currentPct)}%)`);
            } else {
                currentPct = Math.min(94, currentPct + 0.8);
                _updateStatus('loading', `Elaborazione ${engineLabel}... (${Math.round(currentPct)}%)`);
            }
            if (bufferEl) bufferEl.style.width = currentPct + '%';
        }, intervalMs);
    }

    function _completeColdLoadTracker(onComplete) {
        _clearColdLoadTracker();
        const bufferEl = document.getElementById('docreader-audio-buffer-fill');
        const barEl = document.getElementById('docreader-progress-bar');
        if (bufferEl) {
            bufferEl.style.width = '100%';
        }
        _updateStatus('reading', 'Reading...');

        setTimeout(() => {
            if (bufferEl) {
                bufferEl.classList.remove('loading-engine');
                bufferEl.style.width = '0%';
            }
            if (barEl) barEl.classList.remove('synthesizing');
            if (onComplete) onComplete();
        }, 350);
    }

    function _errorColdLoadTracker() {
        _clearColdLoadTracker();
        const bufferEl = document.getElementById('docreader-audio-buffer-fill');
        const barEl = document.getElementById('docreader-progress-bar');
        if (bufferEl) {
            bufferEl.classList.remove('loading-engine');
            bufferEl.style.width = '0%';
        }
        if (barEl) barEl.classList.remove('synthesizing');
        _updateStatus('error', 'Errore caricamento TTS');
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
        _clearSynthesisTracker();
        _setTTSProgress(1, 'Inizializzazione voce browser...', 25);

        const utterance = new SpeechSynthesisUtterance(sentenceData.text);
        utterance.rate = STATE.rate;
        utterance.pitch = STATE.pitch;
        utterance.volume = STATE.volume;

        if (STATE.selectedVoice) {
            const voices = speechSynthesis.getVoices();
            const v = voices.find(v => v.name === STATE.selectedVoice);
            if (v) utterance.voice = v;
        }

        _setTTSProgress(2, 'Sintesi vocale sistema operativo...', 75);

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

        utterance.onstart = () => {
            _updateStatus('reading', 'Reading (Browser)...');
        };

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
        const gp = STATE.hecosPresetId || 'current';
        const eng = STATE.audioEngine || 'auto';
        const ap = STATE.audioPreset || '';
        const v = STATE.audioVoice || 'default';
        const rate = STATE.rate || 1.0;
        return `${path}:::${gp}:::${eng}:::${ap}:::${v}:::${rate}:::${index}:::${text}`;
    }

    // ── Mode B: Hecos Neural TTS (Local Kokoro / Piper / XTTS2 / Fish Speech) ─
    async function _speakWithHecosLocal(index, sentenceData, onEnd) {
        if (!STATE.isReading) return;

        const cacheKey = _getAudioCacheKey(index, sentenceData);
        let audioUrl = STATE._audioCache.get(cacheKey);
        const engineKey = _getCurrentEngineKey();
        const isCold = !STATE._loadedEngines.has(engineKey) || STATE._pendingEngineSwitch;

        if (!audioUrl) {
            // Only show progress bar when cold loading or switching engine/preset
            if (isCold) {
                _startColdLoadTracker();
            } else {
                _updateStatus('reading', 'Reading (Hecos Local)...');
            }

            try {
                const res = await fetch('/hecos/api/plugins/document_reader/tts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: sentenceData.text,
                        preset_id: STATE.hecosPresetId || 'current',
                        engine: STATE.audioEngine || 'auto',
                        audio_preset: STATE.audioPreset || '',
                        voice: STATE.audioVoice || 'default',
                        rate: STATE.rate || 1.0
                    })
                });
                if (!res.ok) throw new Error('TTS server status ' + res.status);
                const data = await res.json();
                if (!data.ok || !data.audio_url) throw new Error(data.error || 'No audio returned');
                audioUrl = data.audio_url;
                STATE._audioCache.set(cacheKey, audioUrl);

                if (isCold) {
                    STATE._loadedEngines.add(engineKey);
                    STATE._pendingEngineSwitch = false;
                    _completeColdLoadTracker();
                }
            } catch (err) {
                console.warn('[DocReader] Hecos TTS error:', err);
                if (isCold) _errorColdLoadTracker();
                _updateStatus('error', 'Voice synthesis error, continuing...');
                setTimeout(() => {
                    if (STATE.isReading && onEnd) onEnd(false);
                }, 1000);
                return;
            }
        } else {
            STATE._loadedEngines.add(engineKey);
            STATE._pendingEngineSwitch = false;
        }

        if (!STATE.isReading) return;

        const audio = new Audio(audioUrl);
        audio.playbackRate = STATE.rate || 1.0;
        audio.volume = STATE.volume !== undefined ? STATE.volume : 1.0;
        STATE._currentAudio = audio;

        audio.onplay = () => {
            _updateStatus('reading', 'Reading (Hecos Local)...');
            // Pre-fetch next sentence in background without invasive UI
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
                    engine: STATE.audioEngine || 'auto',
                    audio_preset: STATE.audioPreset || '',
                    voice: STATE.audioVoice || 'default',
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
                    engine: STATE.audioEngine || 'auto',
                    audio_preset: STATE.audioPreset || '',
                    voice: STATE.audioVoice || 'default',
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

            // Ensure speed & volume controls reflect current state
            _updateSpeedUI(STATE.rate || 1.0);

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
            _clearColdLoadTracker();
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
            _clearColdLoadTracker();
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

            const bufferEl = document.getElementById('docreader-audio-buffer-fill');
            if (bufferEl) {
                bufferEl.classList.remove('loading-engine');
                bufferEl.style.width = '0%';
            }
            const barEl = document.getElementById('docreader-progress-bar');
            if (barEl) barEl.classList.remove('synthesizing');
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
                const engineKey = _getCurrentEngineKey();
                const isCold = !STATE._loadedEngines.has(engineKey) || STATE._pendingEngineSwitch;
                if (isCold) {
                    _startColdLoadTracker();
                } else {
                    _updateStatus('reading', 'Reading selection (Hecos Local)...');
                }

                fetch('/hecos/api/plugins/document_reader/tts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: text,
                        preset_id: STATE.hecosPresetId || 'current',
                        engine: STATE.audioEngine || 'auto',
                        audio_preset: STATE.audioPreset || '',
                        voice: STATE.audioVoice || 'default',
                        rate: STATE.rate || 1.0
                    })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.ok && data.audio_url) {
                        if (isCold) {
                            STATE._loadedEngines.add(engineKey);
                            STATE._pendingEngineSwitch = false;
                            _completeColdLoadTracker();
                        }
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
                        if (isCold) _errorColdLoadTracker();
                        _updateStatus('error', 'Synthesis failed');
                    }
                })
                .catch(err => {
                    STATE.isReading = false;
                    if (isCold) _errorColdLoadTracker();
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

        // Granular Speed Control (0.50× to 3.00× with 0.05 step)
        changeSpeed: function(val, showToastFeedback = false) {
            let rate = parseFloat(val);
            if (isNaN(rate)) rate = 1.0;
            rate = Math.max(0.5, Math.min(3.0, Math.round(rate * 100) / 100));
            STATE.rate = rate;
            
            _updateSpeedUI(rate);

            // Apply in real-time to active audio
            if (STATE.voiceSource === 'hecos' && STATE._currentAudio) {
                STATE._currentAudio.playbackRate = STATE.rate;
            } else if (STATE.voiceSource === 'browser' && STATE.isReading && !STATE.isPaused) {
                clearTimeout(this._speedRestartTimer);
                this._speedRestartTimer = setTimeout(() => {
                    if (STATE.isReading && !STATE.isPaused) {
                        const idx = STATE.currentIndex;
                        this.stop();
                        this.readFromIndex(idx);
                    }
                }, 250);
            }

            if (showToastFeedback && window.showToast) {
                window.showToast(`⚡ Speed: ${_formatSpeed(rate)}`, 'info');
            }
        },

        changeSpeedDelta: function(delta, showToastFeedback = true) {
            const cur = STATE.rate || 1.0;
            const next = Math.max(0.5, Math.min(3.0, Math.round((cur + delta) * 100) / 100));
            this.changeSpeed(next, showToastFeedback);
        },

        resetSpeed: function() {
            this.changeSpeed(1.0, true);
        },

        cycleSpeed: function() {
            this.changeSpeedDelta(0.1, true);
        },

        nextPage: function() {
            const curPage = (STATE.sentences[STATE.currentIndex] && STATE.sentences[STATE.currentIndex].pageIdx) || 0;
            const maxPage = (STATE.pages && STATE.pages.length) ? STATE.pages.length - 1 : 0;
            if (curPage < maxPage) _scrollToPage(curPage + 1);
        },

        prevPage: function() {
            const curPage = (STATE.sentences[STATE.currentIndex] && STATE.sentences[STATE.currentIndex].pageIdx) || 0;
            if (curPage > 0) _scrollToPage(curPage - 1);
        },

        // Change Audio Engine (Auto, Kokoro, Piper, XTTS, Fish Speech, Browser)
        changeAudioEngine: function(engine) {
            STATE.audioEngine = engine;
            if (engine === 'browser') {
                STATE.voiceSource = 'browser';
                if (!STATE.selectedVoice) {
                    const voices = (typeof speechSynthesis !== 'undefined') ? speechSynthesis.getVoices() : [];
                    if (voices && voices.length > 0) STATE.selectedVoice = voices[0].name;
                }
            } else {
                STATE.voiceSource = 'hecos';
            }
            STATE.audioPreset = '';
            STATE.audioVoice = 'default';

            _populateVoiceAndPresetSelect();
            _saveConfig();

            STATE._pendingEngineSwitch = true;
            STATE._audioCache.clear();
            STATE._prefetchSet.clear();

            if (STATE.isReading && !STATE.isPaused) {
                const idx = STATE.currentIndex;
                this.stop();
                this.readFromIndex(idx);
            }
        },

        // Change Voice or Audio Engine Configuration Preset
        changeVoice: function(val) {
            if (!val) return;
            if (val.startsWith('browser:')) {
                STATE.voiceSource = 'browser';
                STATE.audioEngine = 'browser';
                STATE.selectedVoice = val.replace('browser:', '');
                STATE.audioPreset = '';
                STATE.audioVoice = 'default';
                const eSelect = document.getElementById('docreader-engine-select');
                if (eSelect) eSelect.value = 'browser';
            } else if (val.startsWith('preset:')) {
                STATE.voiceSource = 'hecos';
                STATE.audioPreset = val.replace('preset:', '');
                STATE.audioVoice = 'default';
            } else if (val.startsWith('voice:')) {
                STATE.voiceSource = 'hecos';
                STATE.audioVoice = val.replace('voice:', '');
                STATE.audioPreset = '';
            } else { // 'default'
                STATE.audioPreset = '';
                STATE.audioVoice = 'default';
            }

            STATE._pendingEngineSwitch = true;
            STATE._audioCache.clear();
            STATE._prefetchSet.clear();
            _saveConfig();

            if (STATE.isReading && !STATE.isPaused) {
                const idx = STATE.currentIndex;
                this.stop();
                this.readFromIndex(idx);
            }
        },

        // Global Preset (GP / AI Soul Persona) change
        changeHecosPreset: function(presetId) {
            STATE.hecosPresetId = presetId;
            STATE._pendingEngineSwitch = true;
            STATE._audioCache.clear();
            STATE._prefetchSet.clear();
            _saveConfig();

            if (STATE.isReading && !STATE.isPaused) {
                const idx = STATE.currentIndex;
                this.stop();
                this.readFromIndex(idx);
            }
        },

        // Backward compatibility
        changeVoiceSource: function(val) {
            this.changeVoice(val);
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
