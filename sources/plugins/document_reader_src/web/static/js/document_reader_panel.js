/**
 * document_reader_panel.js
 * Controller script for Document Reader configuration panel in Hecos Central Hub.
 */

let _docreaderSaveTimer = null;
let _docreaderVoices = [];
let _docreaderPresets = [];
let _docreaderActiveSoulName = 'Urania 9800 GP';
let _docreaderActiveSoulId = 'urania_9800_gp';
let _docreaderTestAudio = null;

function docreaderInit() {
    docreaderLoadPresets();
    docreaderPopulateVoices();
    docreaderLoadConfig();

    if ('speechSynthesis' in window) {
        window.speechSynthesis.onvoiceschanged = () => {
            docreaderPopulateVoices();
        };
    }
}

// ── Update Dynamic Label on Voice Engine Mode ──────────────────────────────
function docreaderUpdateVoiceSourceLabel() {
    const hecosLabel = document.getElementById('docreader-opt-voice-hecos-label');
    const presetSelect = document.getElementById('docreader-opt-hecos-preset');
    if (!hecosLabel || !presetSelect) return;

    const selectedVal = presetSelect.value;
    let labelText = _docreaderActiveSoulName || 'Current Active Voice';

    if (selectedVal === 'current') {
        labelText = _docreaderActiveSoulName ? `${_docreaderActiveSoulName}` : 'Current Active Voice';
    } else {
        const selectedOpt = presetSelect.options[presetSelect.selectedIndex];
        if (selectedOpt) {
            // Strip engine info to get clean preset name
            labelText = selectedOpt.textContent.split('(')[0].trim();
        }
    }

    hecosLabel.textContent = `✨ Hecos Local Neural TTS (${labelText})`;
}

function docreaderOnPresetChange() {
    docreaderUpdateVoiceSourceLabel();
    docreaderSaveConfig();
}

// ── Load Presets from Core API & Plugin ─────────────────────────────────────
async function docreaderLoadPresets() {
    const select = document.getElementById('docreader-opt-hecos-preset');
    if (!select) return;

    try {
        // Fetch active soul and all souls in parallel from core endpoints
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

        if (cfgRes && cfgRes.ok) {
            const cfgData = await cfgRes.json();
            if (cfgData.ai && cfgData.ai.active_global_preset) {
                _docreaderActiveSoulId = cfgData.ai.active_global_preset;
            }
        }

        // Also try plugin route if available
        if (souls.length === 0) {
            try {
                const pRes = await fetch('/hecos/api/plugins/document_reader/presets');
                if (pRes.ok) {
                    const pData = await pRes.json();
                    if (pData.ok && Array.isArray(pData.presets)) {
                        _docreaderActiveSoulId = pData.active_preset_id || _docreaderActiveSoulId;
                        _docreaderActiveSoulName = pData.active_preset_name || _docreaderActiveSoulName;
                        pData.presets.forEach(p => {
                            souls.push({
                                meta: { id: p.id, name: p.name },
                                voice: { tts_engine: p.engine, tts_voice: p.voice }
                            });
                        });
                    }
                }
            } catch(e) {}
        }

        // Find active soul name
        if (souls.length > 0) {
            const matchedActive = souls.find(s => s.meta && s.meta.id === _docreaderActiveSoulId);
            if (matchedActive && matchedActive.meta && matchedActive.meta.name) {
                _docreaderActiveSoulName = matchedActive.meta.name;
            }

            // Save currently selected value before rebuilding
            const currentSelected = select.value;

            // Rebuild options with fresh data
            select.innerHTML = '';
            
            const currOpt = document.createElement('option');
            currOpt.value = 'current';
            currOpt.textContent = `✨ Use Current Hecos Voice (Local) [${_docreaderActiveSoulName}]`;
            select.appendChild(currOpt);

            // Sort presets alphabetically
            souls.sort((a, b) => (a.meta?.name || '').localeCompare(b.meta?.name || ''));

            souls.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.meta.id;
                const eng = s.voice?.tts_engine ? s.voice.tts_engine.toUpperCase() : 'LOCAL';
                const v = s.voice?.tts_voice ? ` · ${s.voice.tts_voice}` : '';
                opt.textContent = `${s.meta.name} (${eng}${v})`;
                select.appendChild(opt);
            });

            if (currentSelected) {
                select.value = currentSelected;
            }
        } else {
            // If network failed, update the first option with current known soul name
            const firstOpt = select.querySelector('option[value="current"]');
            if (firstOpt) {
                firstOpt.textContent = `✨ Use Current Hecos Voice (Local) [${_docreaderActiveSoulName}]`;
            }
        }

        docreaderUpdateVoiceSourceLabel();

    } catch (e) {
        console.warn('[DocReader] Failed to load presets:', e);
        docreaderUpdateVoiceSourceLabel();
    }
}

// ── Populate Browser Voices ────────────────────────────────────────────────
function docreaderPopulateVoices() {
    if (!('speechSynthesis' in window)) return;
    _docreaderVoices = window.speechSynthesis.getVoices() || [];
    
    const select = document.getElementById('docreader-opt-voice');
    if (!select) return;

    const currentVal = select.value;
    select.innerHTML = '<option value="">-- Default System Voice --</option>';

    const sorted = [..._docreaderVoices].sort((a, b) => {
        const aIsIt = a.lang.toLowerCase().startsWith('it');
        const bIsIt = b.lang.toLowerCase().startsWith('it');
        if (aIsIt && !bIsIt) return -1;
        if (!aIsIt && bIsIt) return 1;
        return a.name.localeCompare(b.name);
    });

    sorted.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.name;
        opt.textContent = `${v.name} (${v.lang})${v.default ? ' [Default]' : ''}`;
        select.appendChild(opt);
    });

    if (currentVal) {
        select.value = currentVal;
    }
}

// ── Toggle Engine Mode Visibility ──────────────────────────────────────────
function docreaderOnVoiceSourceChange() {
    const srcEl = document.getElementById('docreader-opt-voice-source');
    const hecosField = document.getElementById('docreader-hecos-preset-field');
    const browserField = document.getElementById('docreader-browser-voice-field');

    const source = srcEl ? srcEl.value : 'hecos';
    if (source === 'hecos') {
        if (hecosField) hecosField.style.display = 'block';
        if (browserField) browserField.style.display = 'none';
    } else {
        if (hecosField) hecosField.style.display = 'none';
        if (browserField) browserField.style.display = 'block';
    }

    docreaderUpdateVoiceSourceLabel();
    docreaderSaveConfig();
}

// ── Load User Config ───────────────────────────────────────────────────────
async function docreaderLoadConfig() {
    try {
        const res = await fetch('/hecos/api/plugins/document_reader/config');
        if (!res.ok) return;
        const cfg = await res.json();

        const srcEl = document.getElementById('docreader-opt-voice-source');
        if (srcEl && cfg.voice_source) {
            srcEl.value = cfg.voice_source;
        }

        const presetEl = document.getElementById('docreader-opt-hecos-preset');
        if (presetEl && cfg.hecos_preset) {
            presetEl.value = cfg.hecos_preset;
        }

        const voiceEl = document.getElementById('docreader-opt-voice');
        if (voiceEl && cfg.default_voice) {
            voiceEl.value = cfg.default_voice;
        }

        const rateEl = document.getElementById('docreader-opt-rate');
        const rateValEl = document.getElementById('docreader-val-rate');
        if (rateEl) {
            rateEl.value = cfg.default_rate || 1.0;
            if (rateValEl) rateValEl.textContent = parseFloat(rateEl.value).toFixed(1) + '×';
        }

        const pitchEl = document.getElementById('docreader-opt-pitch');
        const pitchValEl = document.getElementById('docreader-val-pitch');
        if (pitchEl) {
            pitchEl.value = cfg.default_pitch || 1.0;
            if (pitchValEl) pitchValEl.textContent = parseFloat(pitchEl.value).toFixed(2);
        }

        const volEl = document.getElementById('docreader-opt-volume');
        const volValEl = document.getElementById('docreader-val-volume');
        if (volEl) {
            volEl.value = cfg.default_volume || 1.0;
            if (volValEl) volValEl.textContent = Math.round(parseFloat(volEl.value) * 100) + '%';
        }

        const colEl = document.getElementById('docreader-opt-color');
        const colHexEl = document.getElementById('docreader-opt-color-hex');
        if (colEl && cfg.highlight_color) {
            colEl.value = cfg.highlight_color;
            if (colHexEl) colHexEl.value = cfg.highlight_color;
        }

        const wordEl = document.getElementById('docreader-opt-word-highlight');
        if (wordEl) {
            wordEl.checked = cfg.word_highlight !== false;
        }

        docreaderOnVoiceSourceChange();
        docreaderUpdateVoiceSourceLabel();

    } catch (e) {
        console.warn('[DocReader] Failed to load config:', e);
    }
}

function docreaderDebounceSave() {
    clearTimeout(_docreaderSaveTimer);
    _docreaderSaveTimer = setTimeout(docreaderSaveConfig, 400);
}

// ── Save User Config ───────────────────────────────────────────────────────
async function docreaderSaveConfig() {
    const srcEl = document.getElementById('docreader-opt-voice-source');
    const presetEl = document.getElementById('docreader-opt-hecos-preset');
    const voiceEl = document.getElementById('docreader-opt-voice');
    const rateEl = document.getElementById('docreader-opt-rate');
    const pitchEl = document.getElementById('docreader-opt-pitch');
    const volEl = document.getElementById('docreader-opt-volume');
    const colEl = document.getElementById('docreader-opt-color');
    const wordEl = document.getElementById('docreader-opt-word-highlight');

    const payload = {
        enabled: true,
        voice_source: srcEl ? srcEl.value : 'hecos',
        hecos_preset: presetEl ? presetEl.value : 'current',
        default_voice: voiceEl ? voiceEl.value : '',
        default_rate: rateEl ? parseFloat(rateEl.value) : 1.0,
        default_pitch: pitchEl ? parseFloat(pitchEl.value) : 1.0,
        default_volume: volEl ? parseFloat(volEl.value) : 1.0,
        highlight_color: colEl ? colEl.value : '#a78bfa',
        word_highlight: wordEl ? wordEl.checked : true
    };

    try {
        const res = await fetch('/hecos/api/plugins/document_reader/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            const statusEl = document.getElementById('docreader-save-status');
            if (statusEl) {
                statusEl.style.display = 'inline-flex';
                clearTimeout(statusEl._hideTimer);
                statusEl._hideTimer = setTimeout(() => {
                    statusEl.style.display = 'none';
                }, 2500);
            }
        }
    } catch (e) {
        console.error('[DocReader] Save error:', e);
    }
}

// ── Test Voice Playback ────────────────────────────────────────────────────
async function docreaderTestVoice() {
    const srcEl = document.getElementById('docreader-opt-voice-source');
    const presetEl = document.getElementById('docreader-opt-hecos-preset');
    const voiceEl = document.getElementById('docreader-opt-voice');
    const rateEl = document.getElementById('docreader-opt-rate');
    const pitchEl = document.getElementById('docreader-opt-pitch');
    const volEl = document.getElementById('docreader-opt-volume');
    const btn = document.getElementById('docreader-test-btn');

    const source = srcEl ? srcEl.value : 'hecos';
    const rate = rateEl ? parseFloat(rateEl.value) : 1.0;
    const pitch = pitchEl ? parseFloat(pitchEl.value) : 1.0;
    const volume = volEl ? parseFloat(volEl.value) : 1.0;
    const sampleText = "This is a voice reading test with Hecos Document Reader. The system is operating properly.";

    if (_docreaderTestAudio) {
        try {
            _docreaderTestAudio.pause();
            _docreaderTestAudio.currentTime = 0;
        } catch(e) {}
        _docreaderTestAudio = null;
    }
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
    }

    if (source === 'hecos') {
        const presetId = presetEl ? presetEl.value : 'current';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
        }

        try {
            const res = await fetch('/hecos/api/plugins/document_reader/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: sampleText,
                    preset_id: presetId,
                    rate: rate
                })
            });

            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            if (!data.ok || !data.audio_url) throw new Error(data.error || 'Empty audio');

            const audio = new Audio(data.audio_url);
            audio.playbackRate = rate;
            audio.volume = volume;
            _docreaderTestAudio = audio;

            if (btn) {
                btn.innerHTML = '<i class="fas fa-volume-up"></i> Playing...';
            }

            audio.onended = () => {
                _docreaderTestAudio = null;
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-play"></i> Test Voice';
                }
            };

            audio.onerror = () => {
                _docreaderTestAudio = null;
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-play"></i> Test Voice';
                }
            };

            await audio.play();

        } catch (err) {
            console.error('[DocReader] Test voice error:', err);
            alert('Voice test failed: ' + err.message);
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-play"></i> Test Voice';
            }
        }

    } else {
        if (!('speechSynthesis' in window)) {
            alert('Your browser does not support the Web Speech API speech synthesis.');
            return;
        }

        const voiceName = voiceEl ? voiceEl.value : '';
        const u = new SpeechSynthesisUtterance(sampleText);
        u.rate = rate;
        u.pitch = pitch;
        u.volume = volume;

        if (voiceName) {
            const matched = _docreaderVoices.find(v => v.name === voiceName);
            if (matched) u.voice = matched;
        }

        window.speechSynthesis.speak(u);
    }
}

// ── Tab Navigation Listeners ───────────────────────────────────────────────
document.addEventListener('click', (e) => {
    const tabBtn = e.target.closest('[onclick*="document_reader"]');
    if (tabBtn) {
        setTimeout(docreaderInit, 120);
    }
});

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', docreaderInit);
} else {
    docreaderInit();
}

// ── Ensure DocReader and dependencies are loaded ──────────────────────────
async function _ensureDocReaderLoaded() {
    if (window.DocReader && typeof window.DocReader.open === 'function') {
        return true;
    }
    // 1. Ensure CSS
    if (!document.querySelector('link[href*="document_reader.css"]')) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = '/hpm_plugin/document_reader/web/static/css/document_reader.css?t=' + Date.now();
        document.head.appendChild(link);
    }
    // 2. Ensure PDF.js
    if (typeof window.pdfjsLib === 'undefined') {
        await new Promise((resolve) => {
            const s = document.createElement('script');
            s.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
            s.onload = () => {
                if (window.pdfjsLib) {
                    window.pdfjsLib.GlobalWorkerOptions.workerSrc = 
                        'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
                }
                resolve();
            };
            s.onerror = resolve;
            document.head.appendChild(s);
        });
    }
    // 3. Ensure document_reader.js
    if (!window.DocReader) {
        await new Promise((resolve) => {
            const s = document.createElement('script');
            s.src = '/hpm_plugin/document_reader/web/static/js/document_reader.js?t=' + Date.now();
            s.onload = resolve;
            s.onerror = () => {
                const s2 = document.createElement('script');
                s2.src = '/static/js/document_reader.js?t=' + Date.now();
                s2.onload = resolve;
                s2.onerror = resolve;
                document.head.appendChild(s2);
            };
            document.head.appendChild(s);
        });
    }
    return !!(window.DocReader && typeof window.DocReader.open === 'function');
}

// ── Direct Document Reader Launcher Helpers ────────────────────────────────
window.docReaderOpenFilePicker = function() {
    if (typeof HecosFilePicker !== 'undefined') {
        HecosFilePicker.open({
            title: "Select Document to Read",
            mode: 'file',
            initialPath: 'C:\\Hecos\\hecos\\media\\documents',
            onSelect: async function(path) {
                if (!path) return;
                const ext = path.split('.').pop().toLowerCase();
                const supported = ['pdf', 'txt', 'md', 'html', 'htm', 'docx'];
                if (!supported.includes(ext)) {
                    if (window.showToast) window.showToast('Format not supported by reader: .' + ext);
                    return;
                }
                const ready = await _ensureDocReaderLoaded();
                if (ready && window.DocReader && typeof window.DocReader.open === 'function') {
                    window.DocReader.open(path);
                } else if (typeof window.openDocReader === 'function') {
                    window.openDocReader(path);
                } else {
                    if (window.showToast) window.showToast('Could not launch Document Reader');
                }
            }
        });
    } else {
        let fi = document.getElementById('docreader-direct-file-input');
        if (!fi) {
            fi = document.createElement('input');
            fi.id = 'docreader-direct-file-input';
            fi.type = 'file';
            fi.accept = '.pdf,.txt,.md,.html,.htm,.docx';
            fi.style.display = 'none';
            document.body.appendChild(fi);
            fi.addEventListener('change', async (e) => {
                const file = e.target.files[0];
                if (!file) return;
                const fd = new FormData();
                fd.append('files', file);
                try {
                    const r = await fetch('/api/upload', { method: 'POST', body: fd });
                    const d = await r.json();
                    if (d.ok && d.saved_files && d.saved_files.length > 0) {
                        const savedPath = d.saved_files[0].path;
                        const ready = await _ensureDocReaderLoaded();
                        if (ready && window.DocReader && typeof window.DocReader.open === 'function') {
                            window.DocReader.open(savedPath);
                        } else if (typeof window.openDocReader === 'function') {
                            window.openDocReader(savedPath);
                        }
                    }
                } catch(err) {
                    if (window.showToast) window.showToast('Error opening file: ' + err.message);
                }
                fi.value = '';
            });
        }
        fi.click();
    }
};


