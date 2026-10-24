/**
 * Hecos Document Reader — Chat Integration
 * Dynamically injects the "Read Document" button next to the "Download" button
 * in .chat-file-card elements when the plugin is active.
 * Never touches the preview bar.
 */

(function() {
    'use strict';

    const SUPPORTED_EXTS = ['.pdf', '.txt', '.md', '.html', '.htm'];

    function _extractCleanPath(raw) {
        if (!raw || typeof raw !== 'string') return '';
        let p = raw.trim();
        while (p.includes('?path=')) {
            try {
                const u = new URL(p, window.location.origin);
                const val = u.searchParams.get('path');
                if (val) p = decodeURIComponent(val);
                else break;
            } catch(e) {
                const m = p.match(/[?&]path=([^&]+)/);
                if (m) p = decodeURIComponent(m[1]);
                else break;
            }
        }
        if (p.startsWith('file:///')) {
            p = decodeURIComponent(p.substring(8));
        } else if (p.startsWith('file://')) {
            p = decodeURIComponent(p.substring(7));
        }
        return p.replace(/\\/g, '/');
    }

    // ── Scan for document cards and inject "Read Document" next to "Download" ─
    function _scanAndInject() {
        // Find all file cards in the chat
        document.querySelectorAll('.chat-file-card').forEach(card => {
            if (card.querySelector('.docreader-chat-btn')) return;

            const nameEl = card.querySelector('.chat-file-name');
            if (!nameEl) return;

            const title = nameEl.getAttribute('title') || '';
            const name = (nameEl.textContent || '').trim();
            const candidateStr = (name || title).toLowerCase();

            if (!SUPPORTED_EXTS.some(ext => candidateStr.endsWith(ext))) return;

            const actionDiv = card.querySelector('.chat-file-action');
            if (!actionDiv) return;

            // Extract document path
            let rawPath = title;
            if (!rawPath) {
                const dlLink = actionDiv.querySelector('a[href]');
                if (dlLink) {
                    const href = dlLink.getAttribute('href') || '';
                    if (href.includes('?path=')) {
                        rawPath = href;
                    }
                }
            }
            if (!rawPath) rawPath = name;

            const docPath = _extractCleanPath(rawPath);
            if (!docPath) return;

            // Create "Read Document" button
            const btn = document.createElement('button');
            btn.className = 'docreader-chat-btn';
            btn.innerHTML = '<i class="fas fa-book-reader"></i> Read Document';
            btn.title = 'Read document aloud with TTS';
            btn.style.cssText = `
                background: rgba(139, 92, 246, 0.15);
                border: 1px solid rgba(139, 92, 246, 0.35);
                color: #c4b5fd;
                padding: 4px 10px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 0.8em;
                font-family: inherit;
                font-weight: 500;
                transition: all 0.2s ease;
                display: inline-flex;
                align-items: center;
                gap: 5px;
            `;

            btn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                let curRaw = '';
                const curDl = actionDiv.querySelector('a[href]');
                if (curDl && (curDl.getAttribute('href') || '').includes('?path=')) {
                    curRaw = curDl.getAttribute('href');
                } else if (nameEl.getAttribute('title')) {
                    curRaw = nameEl.getAttribute('title');
                } else {
                    curRaw = (nameEl.textContent || '').trim();
                }
                const targetPath = _extractCleanPath(curRaw) || docPath;
                if (window.DocReader && typeof window.DocReader.open === 'function') {
                    window.DocReader.open(targetPath);
                } else if (typeof window.openDocReader === 'function') {
                    window.openDocReader(targetPath);
                } else {
                    console.error('[DocReader] Document reader not loaded');
                }
            };

            // Place immediately after the Download link, or append
            const dlBtn = actionDiv.querySelector('a[download]');
            if (dlBtn && dlBtn.nextSibling) {
                actionDiv.insertBefore(btn, dlBtn.nextSibling);
            } else {
                actionDiv.appendChild(btn);
            }
        });

        // Detect <docreader-open path="..."> tags from LLM tool responses
        document.querySelectorAll('docreader-open').forEach(el => {
            const path = el.getAttribute('path');
            if (path) {
                _ensureDocReaderLoaded().then(() => {
                    if (window.DocReader && typeof window.DocReader.open === 'function') {
                        window.DocReader.open(_extractCleanPath(path));
                    }
                });
            }
            el.remove();
        });

        // Detect <docreader-stop> tags
        document.querySelectorAll('docreader-stop').forEach(el => {
            if (window.DocReader && typeof window.DocReader.stop === 'function') {
                window.DocReader.stop();
            }
            el.remove();
        });

        // Detect <docreader-picker> tags
        document.querySelectorAll('docreader-picker').forEach(el => {
            if (typeof window.docReaderOpenFilePicker === 'function') {
                window.docReaderOpenFilePicker();
            }
            el.remove();
        });

        // Detect text tag [DOCREADER:open:PATH] in chat messages (if HTML tags were sanitized)
        document.querySelectorAll('.chat-bubble, .message-content, .chat-message').forEach(bubble => {
            if (bubble._docReaderHandled) return;
            const text = bubble.innerHTML || '';
            const m = text.match(/\[DOCREADER:open:([^\]]+)\]/);
            if (m) {
                bubble._docReaderHandled = true;
                bubble.innerHTML = text.replace(/\[DOCREADER:open:[^\]]+\]/g, '');
                const cleanP = _extractCleanPath(m[1].trim());
                if (cleanP) {
                    _ensureDocReaderLoaded().then(() => {
                        if (window.DocReader && typeof window.DocReader.open === 'function') {
                            window.DocReader.open(cleanP);
                        }
                    });
                }
            } else if (text.includes('[DOCREADER:stop]')) {
                bubble._docReaderHandled = true;
                bubble.innerHTML = text.replace(/\[DOCREADER:stop\]/g, '');
                if (window.DocReader && typeof window.DocReader.stop === 'function') {
                    window.DocReader.stop();
                }
            }
        });
    }

    // ── MutationObserver to detect new cards dynamically ─────────────────────
    function _startObserver() {
        const targetContainer = document.getElementById('chat-area') || 
                                document.getElementById('chat') || 
                                document.getElementById('main') || 
                                document.body;

        const observer = new MutationObserver((mutations) => {
            let shouldScan = false;
            for (const m of mutations) {
                if (m.addedNodes.length > 0) {
                    shouldScan = true;
                    break;
                }
            }
            if (shouldScan) {
                clearTimeout(window._docReaderScanTimer);
                window._docReaderScanTimer = setTimeout(_scanAndInject, 150);
            }
        });

        observer.observe(targetContainer, {
            childList: true,
            subtree: true
        });

        // Initial scan and periodic safety scans
        _scanAndInject();
        setTimeout(_scanAndInject, 500);
        setTimeout(_scanAndInject, 1500);
    }

    // ── Init ─────────────────────────────────────────────────────────────────
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _startObserver);
    } else {
        _startObserver();
    }

    // Also expose scan trigger globally for external UI updates
    window.docReaderScanCards = _scanAndInject;

    // ── Ensure DocReader and dependencies are loaded ──────────────────────────
    async function _ensureDocReaderLoaded() {
        if (window.DocReader && typeof window.DocReader.open === 'function') {
            return true;
        }
        if (!document.querySelector('link[href*="document_reader.css"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = '/hpm_plugin/document_reader/web/static/css/document_reader.css?t=' + Date.now();
            document.head.appendChild(link);
        }
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

    // Direct Reader Picker
    window.docReaderOpenFilePicker = function() {
        if (typeof HecosFilePicker !== 'undefined') {
            HecosFilePicker.open({
                title: "Select Document to Read",
                mode: 'file',
                initialPath: 'C:\\Hecos\\hecos\\modules\\media\\documents',
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

})();

