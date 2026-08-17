(function() {
    'use strict';

    // ── History ───────────────────────────────────────────────────────────────
        window.ntfLoadHistory = async function() {
            const tbody = document.getElementById('ntf-history-list');
            if (!tbody) return;
        
            try {
                const res = await fetch('/hecos/api/plugins/notifications/history');
                const data = await res.json();
            
                if (!Array.isArray(data) || data.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="4" style="padding:12px; text-align:center; color:var(--muted); font-style:italic;">No notifications sent yet.</td></tr>`;
                    return;
                }
            
                tbody.innerHTML = data.map(log => {
                    const dateObj = new Date(log.timestamp);
                    const timeStr = dateObj.toLocaleDateString() + ' ' + dateObj.toLocaleTimeString();
                    const statusBadge = log.status === 'SUCCESS' 
                        ? `<span style="background:rgba(var(--green-rgb),0.15); color:var(--green); padding:2px 6px; border-radius:4px; font-size:10px; font-weight:bold;">SENT</span>`
                        : `<span style="background:rgba(var(--red-rgb),0.15); color:var(--red); padding:2px 6px; border-radius:4px; font-size:10px; font-weight:bold;" title="${log.error_msg || ''}">ERROR</span>`;
                
                    return `
                        <tr style="border-bottom:1px solid var(--border);">
                            <td style="padding:8px; white-space:nowrap; color:var(--muted); font-size:11px;">${timeStr}</td>
                            <td style="padding:8px; font-weight:500;">${log.event_type}</td>
                            <td style="padding:8px;">${log.destination}</td>
                            <td style="padding:8px;">${statusBadge}</td>
                        </tr>
                    `;
                }).join('');
            } catch(e) {
                console.error('[NTF] Error loading history:', e);
                tbody.innerHTML = `<tr><td colspan="4" style="padding:12px; text-align:center; color:var(--error);">Error loading history.</td></tr>`;
            }
        };

        window.ntfClearHistory = async function() {
            const ok = await window.ntfConfirm('Are you sure you want to clear the notification history?', 'Clear History');
            if (!ok) return;
        
            try {
                await fetch('/hecos/api/plugins/notifications/history/clear', { method: 'POST' });
                window.ntfToast('History cleared.');
                window.ntfLoadHistory();
            } catch(e) {
                console.error('[NTF] Error clearing history:', e);
                window.ntfToast('Error clearing history', true);
            }
        };

        // ── Live Log Box ─────────────────────────────────────────────────────────────
        const NTF_LOG_KEYWORDS = ['NOTIFICATIONS', 'MAIL', 'MESSENGER', 'LAZY LOAD', 'NtfTestThread'];
        let _ntfLogEvtSource = null;
        let _ntfLogInitialized = false;

        window._ntfLogColor = function(level) {
            if (!level) return '#b0b0b0';
            const l = level.toUpperCase();
            if (l === 'ERROR')   return '#ff6b6b';
            if (l === 'WARNING') return '#ffaa44';
            if (l === 'INFO')    return '#7ecfff';
            if (l === 'DEBUG')   return '#888';
            return '#b0b0b0';
        }

        window._ntfLogAppend = function(line, level) {
            const box = document.getElementById('ntf-log-box');
            if (!box) return;
            // Remove placeholder
            const ph = box.querySelector('div[style*="italic"]');
            if (ph) ph.remove();

            const entry = document.createElement('div');
            entry.style.color = window._ntfLogColor(level);
            entry.style.borderBottom = '1px solid rgba(255,255,255,0.04)';
            entry.style.paddingBottom = '2px';
            entry.style.marginBottom = '2px';
            entry.textContent = line;
            box.appendChild(entry);

            // Auto-scroll to bottom
            box.scrollTop = box.scrollHeight;

            // Keep max 200 entries
            while (box.children.length > 200) box.removeChild(box.firstChild);
        }

        window._ntfStartLogStream = function() {
            if (_ntfLogInitialized) return;
            _ntfLogInitialized = true;

            const statusEl = document.getElementById('ntf-log-status');
            try {
                _ntfLogEvtSource = new EventSource('/api/logs/stream');

                _ntfLogEvtSource.onopen = () => {
                    if (statusEl) { statusEl.textContent = '● Live'; statusEl.style.color = 'var(--accent)'; }
                };

                _ntfLogEvtSource.onerror = () => {
                    if (statusEl) { statusEl.textContent = '⚠ Reconnecting...'; statusEl.style.color = '#ffaa44'; }
                };

                _ntfLogEvtSource.onmessage = (e) => {
                    try {
                        const data = JSON.parse(e.data);
                        // LogHub format: {time, level, module, text}
                        const text = data.text || data.message || data.msg || JSON.stringify(data);
                        const level = data.level || '';
                        const module = data.module || data.name || '';
                        const fullText = (module + ' ' + text).toUpperCase();
                    
                        // Only show relevant keywords
                        const relevant = NTF_LOG_KEYWORDS.some(kw => fullText.includes(kw.toUpperCase()));
                        if (relevant) {
                            const displayMsg = `[${data.time || ''}] [${module}] ${text}`;
                            window._ntfLogAppend(displayMsg, level);
                        }
                    } catch (_) {}
                };
            } catch(e) {
                if (statusEl) { statusEl.textContent = 'Unavailable'; statusEl.style.color = '#ff6b6b'; }
                console.warn('[NTF] Log stream not available:', e);
            }
        }

        window.ntfClearLog = function() {
            const box = document.getElementById('ntf-log-box');
            if (box) box.innerHTML = '<div style="color:var(--muted); font-style:italic;">Log cleared.</div>';
        };

    
})();
