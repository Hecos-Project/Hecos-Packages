/**
 * Global Backup Panel — panel.js
 * Hecos HPM Module: global_backup
 *
 * Functions used by web_ui/templates/panel.html
 * API base: /hecos/api/backup/
 */

// ── Log Box (inline, HPM-style) ───────────────────────────────────────────────

function backupLog(msg, type = 'info') {
    const icons = { info: 'fas fa-circle-info', success: 'fas fa-check', error: 'fas fa-times', warn: 'fas fa-exclamation-triangle' };
    const colors = { info: 'var(--accent)', success: '#10b981', error: '#ef4444', warn: '#f59e0b' };
    let box = document.getElementById('backup-log-box');
    if (!box) {
        // Create the log box inside the status card body if it doesn't exist yet
        const statusBody = document.querySelector('#tab-backup_panel .backup-card-body');
        if (!statusBody) return;
        box = document.createElement('div');
        box.id = 'backup-log-box';
        box.style.cssText = [
            'margin-top:12px', 'font-size:0.8rem', 'font-family:monospace',
            'background:rgba(0,0,0,0.25)', 'border-radius:8px', 'padding:10px 12px',
            'border-left:3px solid var(--accent)', 'max-height:160px',
            'overflow-y:auto', 'display:flex', 'flex-direction:column', 'gap:4px'
        ].join(';');
        statusBody.appendChild(box);
    }
    const now = new Date().toLocaleTimeString();
    const line = document.createElement('div');
    line.style.cssText = `display:flex; align-items:baseline; gap:8px; color:${colors[type] || colors.info};`;
    line.innerHTML = `<i class="${icons[type] || icons.info}" style="flex-shrink:0; font-size:0.75rem;"></i>
        <span style="color:var(--muted); flex-shrink:0;">${now}</span>
        <span style="color:var(--text); word-break:break-all;">${msg}</span>`;
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;
}

function backupClearLog() {
    const box = document.getElementById('backup-log-box');
    if (box) box.innerHTML = '';
}


function backupFmt(bytes) {
    if (!bytes) return '—';
    const k = 1024;
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let v = bytes;
    while (v >= k && i < units.length - 1) { v /= k; i++; }
    return v.toFixed(1) + ' ' + units[i];
}

function backupFmtDate(iso) {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

// ── Load Config ───────────────────────────────────────────────────────────────

async function backupLoadConfig() {
    try {
        const res = await fetch('/hecos/api/backup/config');
        
        // Handle case where route isn't loaded yet (e.g. before server restart)
        const contentType = res.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            backupShowToast('API not found. Restart Hecos to activate new routes.', 'error');
            return;
        }
        
        const data = await res.json();
        if (!data.ok) { backupLog('Error loading config: ' + data.error, 'error'); return; }

        const cfg = data.config || {};
        const meta = data.modules_meta || {};
        const presets = cfg.presets || {};

        const enEl = document.getElementById('backup-enabled');
        if (enEl) enEl.checked = !!cfg.enabled;

        const destEl = document.getElementById('backup-destination');
        if (destEl) destEl.value = cfg.destination || '';

        const keepEl = document.getElementById('backup-keep-last');
        if (keepEl) keepEl.value = cfg.keep_last ?? 7;

        // Restore schedule builder from saved cron
        schedFromCron(cfg.schedule_cron || '0 */6 * * *');
        schedOnFreqChange();
        schedUpdateSummary();

        const grid = document.getElementById('backup-modules-grid');
        if (grid) {
            grid.innerHTML = '';
            const enabled = Array.isArray(cfg.modules) ? cfg.modules : [];
            Object.keys(meta).forEach(mod => {
                const m = meta[mod];
                const label = document.createElement('label');
                label.className = 'backup-mod-check';
                label.innerHTML = `<input type="checkbox" name="backup-mod" value="${mod}" ${enabled.includes(mod) ? 'checked' : ''} onchange="backupUpdateStats()">
                    <i class="${m.icon || 'fas fa-box'}" style="color:var(--accent)"></i>
                    <span>${m.label || mod}</span>`;
                grid.appendChild(label);
            });
            backupUpdateStats();
        }

        const nextEl = document.getElementById('backup-next-run');
        const lastEl = document.getElementById('backup-last-run');
        const resultEl = document.getElementById('backup-last-result');
        if (nextEl) nextEl.textContent = cfg.next_run ? backupFmtDate(cfg.next_run) : '—';
        if (lastEl) lastEl.textContent = cfg.last_backup ? backupFmtDate(cfg.last_backup) : '—';
        if (resultEl) resultEl.textContent = cfg.last_result || '—';

        await backupLoadHistory();
    } catch (e) {
        backupShowToast('Network error: ' + e.message, 'error');
    }
}

// ── UI Helpers ────────────────────────────────────────────────────────────────

function backupUpdateStats() {
    const checkboxes = document.querySelectorAll('input[name="backup-mod"]');
    if (!checkboxes.length) return;
    const total = checkboxes.length;
    const selected = Array.from(checkboxes).filter(cb => cb.checked).length;
    const unselected = total - selected;
    const statsEl = document.getElementById('backup-modules-stats');
    if (statsEl) {
        const cTotal = `<span style="color:var(--accent); font-weight:bold;">${total}</span>`;
        const cSel = `<span style="color:var(--accent); font-weight:bold;">${selected}</span>`;
        const cUnsel = `<span style="color:var(--accent); font-weight:bold;">${unselected}</span>`;
        statsEl.innerHTML = `(Attached: ${cTotal} | Selected: ${cSel} | Not selected: ${cUnsel})`;
    }
}

function backupToggleSelectAll() {
    const checkboxes = document.querySelectorAll('input[name="backup-mod"]');
    if (!checkboxes.length) return;
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    checkboxes.forEach(cb => cb.checked = !allChecked);
    backupUpdateStats();
    backupSaveConfig();
}

// ── Save Config ───────────────────────────────────────────────────────────────

async function backupSaveConfig() {
    const mods = [...document.querySelectorAll('input[name="backup-mod"]:checked')].map(el => el.value);
    const cronExpr = schedToCron();
    const payload = {
        enabled:         document.getElementById('backup-enabled')?.checked ?? false,
        destination:     document.getElementById('backup-destination')?.value.trim() || '',
        keep_last:       parseInt(document.getElementById('backup-keep-last')?.value || '7'),
        schedule_preset: 'custom',
        schedule_cron:   cronExpr,
        modules:         mods,
    };
    try {
        const res = await fetch('/hecos/api/backup/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!data.ok) backupLog('Save error: ' + data.error, 'error');
    } catch (e) {
        backupLog('Network error: ' + e.message, 'error');
    }
}

// ── Run Backup ────────────────────────────────────────────────────────────────

async function backupRunNow() {
    const btn = document.getElementById('backup-run-btn');
    const banner = document.getElementById('backup-in-progress');
    if (btn) btn.disabled = true;
    if (banner) banner.style.display = 'flex';
    backupClearLog();
    backupLog('Starting backup...', 'info');

    // Capture current last_backup timestamp so we can detect when it changes
    let prevLastBackup = null;
    try {
        const pr = await fetch('/hecos/api/backup/config');
        const pd = await pr.json();
        prevLastBackup = pd.config?.last_backup || null;
    } catch { /* ignore */ }

    try {
        const res = await fetch('/hecos/api/backup/run', { method: 'POST' });
        const data = await res.json();
        if (data.ok) {
            backupLog(data.message || 'Backup running in background...', 'info');
            let attempts = 0;
            let done = false;
            let isPolling = false;
            const poll = setInterval(async () => {
                if (done || isPolling) return;
                isPolling = true;
                attempts++;
                try {
                    const sr = await fetch('/hecos/api/backup/config');
                    const sd = await sr.json();
                    const cfg = sd.config || {};
                    const newTs = cfg.last_backup;
                    // Fire only when the timestamp actually changed (new backup finished)
                    if (newTs && newTs !== prevLastBackup) {
                        done = true;
                        clearInterval(poll);
                        if (cfg.last_result === 'ok') {
                            backupLog('Backup completed successfully.', 'success');
                        } else {
                            backupLog('Backup finished with errors.', 'error');
                        }

                        // Detailed modules reporting
                        if (cfg.last_details && cfg.last_details.modules) {
                            let successCount = 0;
                            let failCount = 0;
                            for (const [mod, res] of Object.entries(cfg.last_details.modules)) {
                                if (res.skipped) continue;
                                if (res.ok) {
                                    let fName = mod === 'system_config' ? '(multiple files)' : `${mod}.json`;
                                    backupLog(`Module '${mod}' backed up correctly. --> ${fName}`, 'success');
                                    successCount++;
                                } else {
                                    backupLog(`Module '${mod}' failed: ${res.error || 'Unknown error'}`, 'error');
                                    failCount++;
                                }
                            }
                            backupLog(`--- Summary: ${successCount} modules backed up successfully. ---`, 'info');
                            if (failCount > 0) {
                                backupLog(`--- Summary: ${failCount} modules failed. ---`, 'warn');
                            }
                        }
                        
                        // User instruction for more details
                        backupLog('For further details, please consult the system logs.', 'info');
                        const lastEl = document.getElementById('backup-last-run');
                        const resultEl = document.getElementById('backup-last-result');
                        if (lastEl) lastEl.textContent = backupFmtDate(newTs);
                        if (resultEl) resultEl.textContent = cfg.last_result || '—';
                        await backupLoadHistory();
                    }
                } catch { clearInterval(poll); }
                finally { isPolling = false; }
                if (attempts >= 60) { clearInterval(poll); backupLog('Timeout waiting for backup result.', 'warn'); }
            }, 1000);
        } else {
            backupLog('Backup failed: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (e) {
        backupLog('Network error: ' + e.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
        if (banner) banner.style.display = 'none';
    }
}


// ── Load History ──────────────────────────────────────────────────────────────

async function backupLoadHistory() {
    const container = document.getElementById('backup-history-list');
    if (!container) return;
    container.innerHTML = '<div class="backup-empty-note">Loading...</div>';
    try {
        const res = await fetch('/hecos/api/backup/history');
        const data = await res.json();
        if (!data.ok || !data.history || data.history.length === 0) {
            container.innerHTML = '<div class="backup-empty-note">No backups available.</div>';
            return;
        }
        container.innerHTML = '';
        data.history.forEach(entry => {
            const row = document.createElement('div');
            row.className = 'backup-history-row';
            row.innerHTML = `
                <div class="backup-history-info">
                    <span class="backup-history-name">${entry.filename || '—'}</span>
                    <span class="backup-history-meta">${backupFmtDate(entry.created_at)} · ${backupFmt(entry.size)}</span>
                </div>
                <div class="backup-history-actions">
                    <button class="btn btn-secondary btn-sm" onclick="backupDownload('${entry.filename}')" title="Scarica"><i class="fas fa-download"></i></button>
                    <button class="btn btn-secondary btn-sm" onclick="backupOpenRestoreModal('${entry.filename}')" title="Ripristina"><i class="fas fa-undo"></i></button>
                    <button class="btn btn-danger btn-sm" onclick="backupDelete('${entry.filename}')" title="Elimina"><i class="fas fa-trash"></i></button>
                </div>`;
            container.appendChild(row);
        });
    } catch (e) {
        container.innerHTML = '<div class="backup-empty-note">Error loading history.</div>';
    }
}

// ── Download / Delete ─────────────────────────────────────────────────────────

function backupDownload(filename) {
    window.location.href = `/hecos/api/backup/download/${encodeURIComponent(filename)}`;
}

async function backupDelete(filename) {
    if (!confirm(`Delete backup "${filename}"?`)) return;
    try {
        const res = await fetch(`/hecos/api/backup/delete/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.ok) { backupLog('Backup deleted: ' + filename, 'info'); await backupLoadHistory(); }
        else backupLog('Error: ' + data.error, 'error');
    } catch (e) { backupLog('Network error: ' + e.message, 'error'); }
}

// ── Restore Modal ─────────────────────────────────────────────────────────────

async function backupOpenRestoreModal(filename) {
    const overlay = document.getElementById('backup-restore-modal');
    if (!overlay) return;
    let modOptions = '';
    try {
        const res = await fetch('/hecos/api/backup/config');
        const data = await res.json();
        const meta = data.modules_meta || {};
        modOptions = Object.keys(meta).map(mod =>
            `<label class="backup-mod-check">
                <input type="checkbox" name="restore-mod" value="${mod}" checked>
                <span>${meta[mod]?.label || mod}</span>
            </label>`
        ).join('');
    } catch { modOptions = '<p>Impossibile caricare i moduli.</p>'; }

    overlay.innerHTML = `
        <div class="backup-modal-box">
            <div class="backup-modal-header"><i class="fas fa-undo"></i> Restore Backup</div>
            <div class="backup-modal-body">
                <p style="font-size:0.85rem;color:var(--muted);margin-bottom:16px;">
                    Select modules to restore from <strong>${filename}</strong>.
                </p>
                <div class="backup-modules-grid">${modOptions}</div>
                <label class="backup-select-all-row">
                    <input type="checkbox" onchange="backupSelectAll(this)"> Select all
                </label>
            </div>
            <div class="backup-modal-footer">
                <button class="btn btn-secondary" onclick="backupCloseModal()">Cancel</button>
                <button class="btn btn-primary" onclick="backupConfirmRestore('${filename}')">
                    <i class="fas fa-undo"></i> Restore
                </button>
            </div>
        </div>`;
    overlay.style.display = 'flex';
}

function backupCloseModal() {
    const overlay = document.getElementById('backup-restore-modal');
    if (overlay) overlay.style.display = 'none';
}

function backupSelectAll(cb) {
    document.querySelectorAll('input[name="restore-mod"]').forEach(el => el.checked = cb.checked);
}

async function backupConfirmRestore(filename) {
    const mods = [...document.querySelectorAll('input[name="restore-mod"]:checked')].map(el => el.value);
    if (mods.length === 0) { backupShowToast('Select at least one module.', 'error'); return; }
    backupCloseModal();
    
    backupClearLog();
    backupLog('Starting restore from ' + filename + '...', 'info');
    document.getElementById('backup-log-box')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    
    try {
        const res = await fetch('/hecos/api/backup/restore', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename, modules: mods }),
        });
        const data = await res.json();
        
        if (data.ok) {
            backupLog('Restore process finished with success flag.', 'success');
        } else {
            backupLog('Restore finished with errors or failures.', 'error');
            if (data.error) backupLog('Error details: ' + data.error, 'error');
        }
        
        if (data.results) {
            let successCount = 0;
            let failCount = 0;
            for (const [mod, r] of Object.entries(data.results)) {
                if (r.skipped) continue;
                if (r.ok) {
                    let fName = mod === 'system_config' ? '(multiple files)' : `${mod}.json`;
                    backupLog(`Module '${mod}' restored correctly. <-- ${fName}`, 'success');
                    successCount++;
                } else {
                    backupLog(`Module '${mod}' failed to restore: ${r.error || 'Unknown error'}`, 'error');
                    failCount++;
                }
            }
            backupLog(`--- Summary: ${successCount} modules restored successfully. ---`, 'info');
            if (failCount > 0) backupLog(`--- Summary: ${failCount} modules failed. ---`, 'warn');
        }
        
        backupLog('For further details, please consult the system logs.', 'info');
    } catch (e) { 
        backupLog('Network error: ' + e.message, 'error'); 
    }
}

// ── Upload Restore ────────────────────────────────────────────────────────────

async function backupHandleRestoreUpload(input) {
    if (!input.files.length) return;
    const formData = new FormData();
    formData.append('file', input.files[0]);
    
    backupClearLog();
    backupLog('Starting restore from uploaded ZIP...', 'info');
    document.getElementById('backup-log-box')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    
    try {
        const res = await fetch('/hecos/api/backup/restore', { method: 'POST', body: formData });
        const data = await res.json();
        
        if (data.ok) {
            backupLog('Uploaded restore process finished with success flag.', 'success');
            await backupLoadHistory();
        } else {
            backupLog('Uploaded restore finished with errors.', 'error');
            if (data.error) backupLog('Error details: ' + data.error, 'error');
        }
        
        if (data.results) {
            let successCount = 0;
            let failCount = 0;
            for (const [mod, r] of Object.entries(data.results)) {
                if (r.skipped) continue;
                if (r.ok) {
                    let fName = mod === 'system_config' ? '(multiple files)' : `${mod}.json`;
                    backupLog(`Module '${mod}' restored correctly. <-- ${fName}`, 'success');
                    successCount++;
                } else {
                    backupLog(`Module '${mod}' failed to restore: ${r.error || 'Unknown error'}`, 'error');
                    failCount++;
                }
            }
            backupLog(`--- Summary: ${successCount} modules restored successfully. ---`, 'info');
            if (failCount > 0) backupLog(`--- Summary: ${failCount} modules failed. ---`, 'warn');
        }
        
        backupLog('For further details, please consult the system logs.', 'info');
    } catch (e) { 
        backupLog('Network error: ' + e.message, 'error'); 
    }
    input.value = '';
}

// ── Schedule Builder Helpers ──────────────────────────────────────────

function schedOnFreqChange() {
    const freq = document.getElementById('sched-freq')?.value || 'interval';
    document.getElementById('sched-row-interval').style.display = (freq === 'interval') ? 'flex' : 'none';
    document.getElementById('sched-row-time').style.display    = (freq !== 'interval') ? 'flex' : 'none';
    document.getElementById('sched-row-days').style.display    = (freq === 'weekly')   ? 'flex' : 'none';
    document.getElementById('sched-row-dom').style.display     = (freq === 'monthly')  ? 'flex' : 'none';
    schedUpdateSummary();
}

function schedGetActiveDays() {
    return [...document.querySelectorAll('.sched-day-btn.active')].map(el => parseInt(el.dataset.day));
}

function schedToggleDay(el) {
    el.classList.toggle('active');
    schedUpdateSummary();
    backupSaveConfig();
}

function schedUpdateSummary() {
    const freq = document.getElementById('sched-freq')?.value || 'interval';
    const summEl = document.getElementById('sched-summary');
    if (!summEl) return;
    const DAY_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    let txt = '';
    const icon = '<i class="fas fa-clock" style="color:var(--accent); margin-right:6px; font-size:0.85rem;"></i>';
    if (freq === 'interval') {
        const h = parseInt(document.getElementById('sched-interval-h')?.value || 6);
        txt = `${icon} Every ${h} hour${h !== 1 ? 's' : ''}`;
    } else if (freq === 'daily') {
        const t = document.getElementById('sched-time')?.value || '02:00';
        txt = `${icon} Every day at ${t}`;
    } else if (freq === 'weekly') {
        const days = schedGetActiveDays().sort((a,b) => a-b).map(d => DAY_NAMES[d]).join(', ');
        const t = document.getElementById('sched-time')?.value || '02:00';
        txt = days.length ? `${icon} Every ${days} at ${t}` : '<i class="fas fa-exclamation-triangle" style="color:var(--warn); margin-right:6px;"></i> Select at least one day';
    } else if (freq === 'monthly') {
        const dom = document.getElementById('sched-dom')?.value || '1';
        const t = document.getElementById('sched-time')?.value || '02:00';
        const suffix = dom == 1 ? 'st' : dom == 2 ? 'nd' : dom == 3 ? 'rd' : 'th';
        txt = `${icon} Every month on the ${dom}${suffix} at ${t}`;
    }
    summEl.innerHTML = txt;
}

function schedToCron() {
    const freq = document.getElementById('sched-freq')?.value || 'interval';
    const t = (document.getElementById('sched-time')?.value || '02:00').split(':');
    // t[0] = hours (HH), t[1] = minutes (MM)  e.g. '02:30' -> ['02','30']
    const schedHour = t[0] || '2';
    const schedMin  = t[1] || '0';
    if (freq === 'interval') {
        const h = parseInt(document.getElementById('sched-interval-h')?.value || 6);
        return `0 */${h} * * *`;
    } else if (freq === 'daily') {
        return `${schedMin} ${schedHour} * * *`;
    } else if (freq === 'weekly') {
        const days = schedGetActiveDays().sort((a,b) => a-b).join(',') || '1';
        return `${schedMin} ${schedHour} * * ${days}`;
    } else if (freq === 'monthly') {
        const dom = parseInt(document.getElementById('sched-dom')?.value || 1);
        return `${schedMin} ${schedHour} ${dom} * *`;
    }
    return '0 2 * * *';
}

function schedFromCron(cron) {
    // Parse a stored cron expression back into the builder UI
    if (!cron) return;
    const parts = cron.trim().split(/\s+/);
    if (parts.length !== 5) return;
    const [cronMin, cronHour, cronDom, , cronDow] = parts;
    const freqEl = document.getElementById('sched-freq');
    const timeEl = document.getElementById('sched-time');
    const intervalEl = document.getElementById('sched-interval-h');
    const domEl = document.getElementById('sched-dom');
    if (!freqEl) return;

    // Detect frequency from pattern
    if (cronHour && cronHour.startsWith('*/')) {
        // interval
        freqEl.value = 'interval';
        if (intervalEl) intervalEl.value = cronHour.replace('*/', '');
    } else if (cronDow !== '*') {
        // weekly
        freqEl.value = 'weekly';
        const activeDays = cronDow.split(',').map(Number);
        document.querySelectorAll('.sched-day-btn').forEach(btn => {
            btn.classList.toggle('active', activeDays.includes(parseInt(btn.dataset.day)));
        });
        if (timeEl) timeEl.value = cronHour.padStart(2,'0') + ':' + cronMin.padStart(2,'0');
    } else if (cronDom !== '*') {
        // monthly
        freqEl.value = 'monthly';
        if (domEl) domEl.value = cronDom;
        if (timeEl) timeEl.value = cronHour.padStart(2,'0') + ':' + cronMin.padStart(2,'0');
    } else {
        // daily
        freqEl.value = 'daily';
        if (timeEl) timeEl.value = cronHour.padStart(2,'0') + ':' + cronMin.padStart(2,'0');
    }
}

// Wire up day pill clicks (called once after page load)
document.querySelectorAll('.sched-day-btn').forEach(btn => {
    btn.addEventListener('click', () => schedToggleDay(btn));
});

async function backupBrowseFolder() {
    try {
        const res = await fetch('/api/system/explorer/pick-native', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pick_dir: true,
                title: 'Select Backup Destination Folder'
            })
        });
        const data = await res.json();
        if (data.ok && data.path) {
            const dest = document.getElementById('backup-destination');
            if (dest) {
                dest.value = data.path;
                // Trigger input event to auto-save config
                dest.dispatchEvent(new Event('input', { bubbles: true }));
            }
        } else if (!data.ok && data.error) {
            console.warn('[GlobalBackup] Folder pick canceled or failed: ', data.error);
        }
    } catch (e) {
        backupShowToast('Network error: ' + e.message, 'error');
    }
}

// ── Bootstrap ──────────────────────────────────────────────────────────────────
// The HPM Asset Loader injects our JS *before* the panel HTML is merged into the
// hub. So we must wait for a key element (like backup-enabled) to appear in the DOM.

let _backupInitDone = false;

function _waitForBackupPanel(callback) {
    if (document.getElementById('backup-enabled')) {
        callback();
        return;
    }
    const observer = new MutationObserver((mutations, obs) => {
        if (document.getElementById('backup-enabled')) {
            obs.disconnect();
            callback();
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
}

const initBackupPanel = () => {
    if (_backupInitDone) return;
    _backupInitDone = true;
    console.log('[GlobalBackup] Panel DOM ready — initializing...');
    backupLoadConfig();
    backupLoadHistory();
    
    // Auto-save on change
    const panel = document.getElementById('tab-backup_panel');
    if (panel) {
        panel.addEventListener('change', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') {
                if (e.target.type !== 'file' && !e.target.name?.startsWith('restore-')) {
                    backupSaveConfig();
                }
            }
        });
        
        // Debounce for text/number inputs
        let timeout;
        panel.addEventListener('input', (e) => {
            if (e.target.type === 'text' || e.target.type === 'number') {
                clearTimeout(timeout);
                timeout = setTimeout(backupSaveConfig, 500);
            }
        });
    }
};

_waitForBackupPanel(initBackupPanel);
