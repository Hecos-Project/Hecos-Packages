/**
 * Hecos Document Reader — Main Controller & Public API Facade
 * Fullscreen document reader with Web Speech API TTS, Hecos Local Neural TTS, and PDF.js extraction.
 */

(function() {
    'use strict';

    function _getBaseScriptPath() {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const s = scripts[i];
            if (s.src && s.src.includes('document_reader.js')) {
                return s.src.substring(0, s.src.lastIndexOf('/') + 1);
            }
        }
        return '/static/js/';
    }

    const _basePath = _getBaseScriptPath();

    async function _loadScript(fileName) {
        return new Promise((resolve) => {
            const script = document.createElement('script');
            script.src = _basePath + fileName + '?t=' + Date.now();
            script.onload = () => resolve(true);
            script.onerror = () => resolve(false);
            document.head.appendChild(script);
        });
    }

    async function _ensureModulesLoaded() {
        if (!window.DocReaderState) await _loadScript('docreader_state.js');
        if (!window.DocReaderLoader) await _loadScript('docreader_loader.js');
        if (!window.DocReaderAudio) await _loadScript('docreader_audio.js');
        if (!window.DocReaderUI) await _loadScript('docreader_ui.js');
    }

    // Immediately trigger module load in the background
    _ensureModulesLoaded();

    function _getState() {
        return (window.DocReaderState && window.DocReaderState.state) ? window.DocReaderState.state : {};
    }

    // ── Public API ───────────────────────────────────────────────────────────
    window.DocReader = {
        // Open the reader with a document path
        open: async function(filePath) {
            await _ensureModulesLoaded();
            const STATE = _getState();

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

            // Immediately stop current playback and clear all caches
            this.stop();
            STATE._audioCache.clear();
            STATE._prefetchSet.clear();
            STATE.sentences = [];
            STATE.pages = [];
            if (STATE.pdfDoc && typeof STATE.pdfDoc.destroy === 'function') {
                try { STATE.pdfDoc.destroy(); } catch(e) {}
                STATE.pdfDoc = null;
            }

            // Establish fresh document session ID to discard any in-flight async tasks
            const sessionId = Date.now();
            STATE._sessionId = sessionId;
            STATE.currentPath = filePath;
            STATE.isOpen = true;
            STATE.currentIndex = 0;

            const overlay = window.DocReaderUI ? window.DocReaderUI.createOverlay() : document.getElementById('docreader-overlay');
            if (overlay) overlay.classList.add('active');

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

            if (window.DocReaderUI) {
                window.DocReaderUI.updateSpeedUI(STATE.rate || 1.0);
            }

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
                    docData = await window.DocReaderLoader.loadPDFDocument(apiUrl, sessionId);
                } else {
                    docData = await window.DocReaderLoader.loadTextDocument(apiUrl, ext, filePath);
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
                if (window.DocReaderUI) {
                    window.DocReaderUI.renderContent(docData, sessionId);
                    window.DocReaderUI.updateStatus('ready', 'Ready');
                }

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
            const STATE = _getState();
            this.stop();
            if (window.DocReaderState) window.DocReaderState.clearColdLoadTracker();
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

        togglePlayPause: function() {
            const STATE = _getState();
            if (STATE.isReading && !STATE.isPaused) {
                if (STATE.voiceSource === 'browser') {
                    if (typeof speechSynthesis !== 'undefined') speechSynthesis.pause();
                } else if (STATE._currentAudio) {
                    STATE._currentAudio.pause();
                }
                STATE.isPaused = true;
                if (window.DocReaderUI) {
                    window.DocReaderUI.updatePlayBtn();
                    window.DocReaderUI.updateStatus('paused', 'Paused');
                }
            } else if (STATE.isPaused) {
                if (STATE.voiceSource === 'browser') {
                    if (typeof speechSynthesis !== 'undefined') speechSynthesis.resume();
                } else if (STATE._currentAudio) {
                    STATE._currentAudio.play().catch(e => console.warn(e));
                }
                STATE.isPaused = false;
                if (window.DocReaderUI) {
                    window.DocReaderUI.updatePlayBtn();
                    window.DocReaderUI.updateStatus('reading', 'Reading...');
                }
            } else {
                this.readFromIndex(STATE.currentIndex);
            }
        },

        stop: function() {
            const STATE = _getState();
            if (window.DocReaderState) window.DocReaderState.clearColdLoadTracker();
            if (window.DocReaderAudio) window.DocReaderAudio.stopAudio();
            STATE.isReading = false;
            STATE.isPaused = false;
            STATE.utterance = null;
            if (window.DocReaderUI) {
                window.DocReaderUI.highlightSentence(-1, true);
                window.DocReaderUI.updatePlayBtn();
                window.DocReaderUI.updateStatus('ready', 'Ready');
            }
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

        readFromIndex: function(index) {
            const STATE = _getState();
            this.stop();
            STATE.isReading = true;
            STATE.currentIndex = index;
            if (window.DocReaderUI) {
                window.DocReaderUI.updatePlayBtn();
                window.DocReaderUI.updateStatus('reading', 'Reading...');
            }

            const readNext = (idx) => {
                if (!STATE.isReading || idx >= STATE.sentences.length) {
                    this.stop();
                    return;
                }
                STATE.currentIndex = idx;
                if (window.DocReaderAudio) {
                    window.DocReaderAudio.speakSentence(idx, (done) => {
                        if (!done && STATE.isReading) {
                            readNext(idx + 1);
                        } else if (done) {
                            this.stop();
                        }
                    });
                }
            };

            readNext(index);
        },

        prevSentence: function() {
            const STATE = _getState();
            const wasReading = STATE.isReading;
            this.stop();
            STATE.currentIndex = Math.max(0, STATE.currentIndex - 1);
            if (window.DocReaderUI) {
                window.DocReaderUI.highlightSentence(STATE.currentIndex);
                window.DocReaderUI.updateProgress();
            }
            if (wasReading) {
                this.readFromIndex(STATE.currentIndex);
            }
        },

        nextSentence: function() {
            const STATE = _getState();
            const wasReading = STATE.isReading;
            this.stop();
            STATE.currentIndex = Math.min(STATE.sentences.length - 1, STATE.currentIndex + 1);
            if (window.DocReaderUI) {
                window.DocReaderUI.highlightSentence(STATE.currentIndex);
                window.DocReaderUI.updateProgress();
            }
            if (wasReading) {
                this.readFromIndex(STATE.currentIndex);
            }
        },

        readSelection: function() {
            if (window.DocReaderAudio) {
                window.DocReaderAudio.readSelection();
            }
        },

        readFromHere: function() {
            const sel = window.getSelection();
            if (!sel || !sel.rangeCount) return;

            const range = sel.getRangeAt(0);
            const startNode = range.startContainer;

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

        seekProgress: function(e) {
            const STATE = _getState();
            const bar = document.getElementById('docreader-progress-bar');
            if (!bar || STATE.sentences.length === 0) return;
            
            const rect = bar.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            const idx = Math.floor(pct * STATE.sentences.length);
            
            const wasReading = STATE.isReading;
            this.stop();
            STATE.currentIndex = Math.max(0, Math.min(STATE.sentences.length - 1, idx));
            if (window.DocReaderUI) {
                window.DocReaderUI.highlightSentence(STATE.currentIndex);
                window.DocReaderUI.updateProgress();
            }
            
            if (wasReading) {
                this.readFromIndex(STATE.currentIndex);
            }
        },

        changeSpeed: function(val, showToastFeedback = false) {
            const STATE = _getState();
            let rate = parseFloat(val);
            if (isNaN(rate)) rate = 1.0;
            rate = Math.max(0.5, Math.min(3.0, Math.round(rate * 100) / 100));
            STATE.rate = rate;
            
            if (window.DocReaderUI) {
                window.DocReaderUI.updateSpeedUI(rate);
            }

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
                const formatted = window.DocReaderState ? window.DocReaderState.formatSpeed(rate) : (rate + '×');
                window.showToast(`⚡ Speed: ${formatted}`, 'info');
            }
        },

        changeSpeedDelta: function(delta, showToastFeedback = true) {
            const STATE = _getState();
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
            const STATE = _getState();
            const curPage = (STATE.sentences[STATE.currentIndex] && STATE.sentences[STATE.currentIndex].pageIdx) || 0;
            const maxPage = (STATE.pages && STATE.pages.length) ? STATE.pages.length - 1 : 0;
            if (curPage < maxPage && window.DocReaderUI) window.DocReaderUI.scrollToPage(curPage + 1);
        },

        prevPage: function() {
            const STATE = _getState();
            const curPage = (STATE.sentences[STATE.currentIndex] && STATE.sentences[STATE.currentIndex].pageIdx) || 0;
            if (curPage > 0 && window.DocReaderUI) window.DocReaderUI.scrollToPage(curPage - 1);
        },

        changeAudioEngine: function(engine) {
            const STATE = _getState();
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

            if (window.DocReaderUI) {
                window.DocReaderUI.populateVoiceAndPresetSelect();
                window.DocReaderUI.saveConfig();
            }

            STATE._pendingEngineSwitch = true;
            STATE._audioCache.clear();
            STATE._prefetchSet.clear();

            if (STATE.isReading && !STATE.isPaused) {
                const idx = STATE.currentIndex;
                this.stop();
                this.readFromIndex(idx);
            }
        },

        changeVoice: function(val) {
            if (!val) return;
            const STATE = _getState();
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
            } else {
                STATE.audioPreset = '';
                STATE.audioVoice = 'default';
            }

            STATE._pendingEngineSwitch = true;
            STATE._audioCache.clear();
            STATE._prefetchSet.clear();
            if (window.DocReaderUI) window.DocReaderUI.saveConfig();

            if (STATE.isReading && !STATE.isPaused) {
                const idx = STATE.currentIndex;
                this.stop();
                this.readFromIndex(idx);
            }
        },

        changeHecosPreset: function(presetId) {
            const STATE = _getState();
            STATE.hecosPresetId = presetId;
            STATE._pendingEngineSwitch = true;
            STATE._audioCache.clear();
            STATE._prefetchSet.clear();
            if (window.DocReaderUI) window.DocReaderUI.saveConfig();

            if (STATE.isReading && !STATE.isPaused) {
                const idx = STATE.currentIndex;
                this.stop();
                this.readFromIndex(idx);
            }
        },

        changeVoiceSource: function(val) {
            this.changeVoice(val);
        },

        changeVolume: function(val) {
            const STATE = _getState();
            STATE.volume = parseFloat(val);
            if (STATE._currentAudio) {
                STATE._currentAudio.volume = STATE.volume;
            }
        },

        changeFontSize: function(delta) {
            const STATE = _getState();
            STATE.fontSize = Math.max(0.7, Math.min(2.5, STATE.fontSize + delta));
            STATE.visualZoom = Math.max(0.5, Math.min(2.5, (STATE.visualZoom || 1.0) + delta));
            const content = document.getElementById('docreader-content');
            if (content) content.style.fontSize = STATE.fontSize + 'em';

            document.querySelectorAll('.docreader-pdf-canvas').forEach(canvas => {
                const baseW = parseFloat(canvas.dataset.baseWidth);
                const baseH = parseFloat(canvas.dataset.baseHeight);
                if (baseW && baseH) {
                    canvas.style.width = Math.floor(baseW * STATE.visualZoom) + 'px';
                    canvas.style.height = Math.floor(baseH * STATE.visualZoom) + 'px';
                }
            });
        },

        setViewMode: function(mode) {
            if (!['visual', 'split', 'text'].includes(mode)) return;
            const STATE = _getState();
            STATE.viewMode = mode;
            const container = document.getElementById('docreader-pages-container');
            if (container) {
                container.className = `docreader-pages-container docreader-view-${mode}`;
            }
            document.querySelectorAll('.docreader-view-btn').forEach(btn => {
                btn.classList.toggle('active', btn.id === `docreader-mode-${mode}`);
            });
            if (STATE.sentences[STATE.currentIndex] && window.DocReaderUI) {
                window.DocReaderUI.highlightSentence(STATE.currentIndex);
            }
        },

        toggleSidebar: function() {
            const STATE = _getState();
            STATE.sidebarOpen = !STATE.sidebarOpen;
            const sidebar = document.getElementById('docreader-sidebar');
            if (sidebar) sidebar.classList.toggle('open', STATE.sidebarOpen);
        },

        isReading: function() {
            const STATE = _getState();
            return !!(STATE.isReading && !STATE.isPaused);
        },

        isOpen: function() {
            const STATE = _getState();
            return !!STATE.isOpen;
        }
    };

    // ── Listen for SSE events from the backend ───────────────────────────────
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
