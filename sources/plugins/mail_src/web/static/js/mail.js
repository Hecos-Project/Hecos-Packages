/**
 * HECOS Mail Module — Frontend Logic
 * Served at: /ext/mail/static/js/mail.js
 */

// ── State ─────────────────────────────────────────────────────────────────────

window.MailApp = {
    currentFolder: 'INBOX',
    currentFilter: 'all',
    searchQuery: '',
    messages: [],
    selectedId: null,
    isComposeOpen: false,
    focusMode: 0,  // 0=normal, 1=compact, 2=fullscreen
    headers: {}    // injected per-request (e.g. X-Mail-Account)
};

// ── API Helpers ───────────────────────────────────────────────────────────────

function mailGetHeaders() {
    return Object.assign({'Content-Type': 'application/json'}, MailApp.headers || {});
}
function mailApiGet(endpoint) {
    return fetch('/api/mail' + endpoint, { headers: mailGetHeaders() }).then(r => r.json());
}
function mailApiPost(endpoint, data = {}) {
    return fetch('/api/mail' + endpoint, {
        method: 'POST', body: JSON.stringify(data), headers: mailGetHeaders()
    }).then(r => r.json());
}
function mailApiPut(endpoint, data = {}) {
    return fetch('/api/mail' + endpoint, {
        method: 'PUT', body: JSON.stringify(data), headers: mailGetHeaders()
    }).then(r => r.json());
}
function mailApiDelete(endpoint) {
    return fetch('/api/mail' + endpoint, {
        method: 'DELETE', headers: mailGetHeaders()
    }).then(r => r.json());
}

// ── Utility ───────────────────────────────────────────────────────────────────

function hecosEscapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// ── Modals ────────────────────────────────────────────────────────────────────

function mailShowToast(msg, type = 'info') {
    let overlay = document.getElementById('mail-hecos-toast-modal');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'mail-hecos-toast-modal';
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);z-index:99999;display:flex;align-items:center;justify-content:center;opacity:0;transition:opacity 0.2s;';
        overlay.innerHTML = `
            <div style="background:var(--bg2,#1e1e1e);border:1px solid var(--border-color,#333);border-radius:12px;padding:24px;max-width:400px;text-align:center;box-shadow:0 10px 30px rgba(0,0,0,0.5);transform:translateY(20px);transition:transform 0.3s cubic-bezier(0.175,0.885,0.32,1.275);">
                <h2 style="margin-top:0;font-size:1.4em;color:var(--text);"><i id="mail-toast-icon" class="fas fa-info-circle" style="margin-right:8px;"></i><span id="mail-toast-title-text">Notice</span></h2>
                <p id="mail-toast-msg" style="margin:20px 0;color:var(--text);font-size:1.05em;"></p>
                <div style="display:flex;justify-content:center;margin-top:24px;">
                    <button type="button" class="btn btn-secondary" onclick="this.closest('div[id]').style.opacity='0';setTimeout(()=>this.closest('div[id]').style.display='none',200)">OK</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
    }
    document.getElementById('mail-toast-msg').innerHTML = msg;
    const title = document.getElementById('mail-toast-title-text');
    const icon  = document.getElementById('mail-toast-icon');
    if (type === 'error')   { title.textContent = 'Error';   icon.className = 'fas fa-exclamation-triangle'; icon.style.color = '#ff4a4a'; }
    else if (type === 'success') { title.textContent = 'Success'; icon.className = 'fas fa-check-circle'; icon.style.color = '#10b981'; }
    else                    { title.textContent = 'Notice';  icon.className = 'fas fa-info-circle'; icon.style.color = 'var(--accent,#3b82f6)'; }
    overlay.style.display = 'flex';
    setTimeout(() => { overlay.style.opacity = '1'; overlay.querySelector('div').style.transform = 'translateY(0)'; }, 10);
}

function mailShowConfirm(msg, btnText, onConfirm) {
    let overlay = document.getElementById('mail-hecos-confirm-modal');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'mail-hecos-confirm-modal';
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);z-index:99999;display:flex;align-items:center;justify-content:center;opacity:0;transition:opacity 0.2s;';
        overlay.innerHTML = `
            <div style="background:var(--bg2,#1e1e1e);border:1px solid var(--border-color,#333);border-radius:12px;padding:24px;max-width:400px;text-align:center;box-shadow:0 10px 30px rgba(0,0,0,0.5);transform:translateY(20px);transition:transform 0.3s;">
                <h2 style="margin-top:0;font-size:1.4em;color:var(--text);"><i class="fas fa-exclamation-triangle" style="color:#ff4a4a;margin-right:8px;"></i>Confirm</h2>
                <p id="mail-confirm-msg" style="margin:20px 0;color:var(--text);font-size:1.05em;"></p>
                <div style="display:flex;justify-content:center;gap:15px;margin-top:24px;">
                    <button type="button" class="btn btn-secondary" onclick="this.closest('div[id]').style.opacity='0';setTimeout(()=>this.closest('div[id]').style.display='none',200)">Cancel</button>
                    <button type="button" class="btn btn-danger" style="background:#ff4a4a;color:white;border:none;" id="mail-confirm-btn">Confirm</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
    }
    document.getElementById('mail-confirm-msg').innerHTML = msg;
    const obtn = document.getElementById('mail-confirm-btn');
    obtn.textContent = btnText || 'Confirm';
    obtn.onclick = () => {
        if (onConfirm) onConfirm();
        overlay.style.opacity = '0';
        setTimeout(() => overlay.style.display = 'none', 200);
    };
    overlay.style.display = 'flex';
    setTimeout(() => { overlay.style.opacity = '1'; overlay.querySelector('div').style.transform = 'translateY(0)'; }, 10);
}

// ── Focus Mode ────────────────────────────────────────────────────────────────

function mailCycleFocusMode() {
    MailApp.focusMode = (MailApp.focusMode + 1) % 3;
    mailApplyFocusMode();
}

function mailApplyFocusMode() {
    const shell = document.querySelector('.mail-shell');
    const btn   = document.getElementById('mail-focus-btn');
    const icon  = document.getElementById('mail-focus-icon');
    const label = document.getElementById('mail-focus-label');
    if (!shell || !btn) return;
    shell.classList.remove('focus-compact');
    document.getElementById('mail-fullscreen-overlay')?.classList.remove('active');
    btn.classList.remove('compact', 'fullscreen');
    if (MailApp.focusMode === 0) {
        icon.className = 'fas fa-compress-alt'; label.textContent = 'Focus'; btn.title = 'Switch to Compact mode';
    } else if (MailApp.focusMode === 1) {
        shell.classList.add('focus-compact'); btn.classList.add('compact');
        icon.className = 'fas fa-columns'; label.textContent = 'Compact'; btn.title = 'Switch to Fullscreen mode';
    } else {
        document.getElementById('mail-fs-subject').innerHTML = document.getElementById('mail-preview-subject')?.innerHTML || '';
        document.getElementById('mail-fs-meta').innerHTML    = document.getElementById('mail-preview-meta')?.innerHTML || '';
        document.getElementById('mail-fs-body').innerHTML    = document.getElementById('mail-preview-body')?.innerHTML || '';
        const srcActions = document.querySelector('#mail-preview-header .mail-preview-actions');
        const dstActions = document.getElementById('mail-fs-actions');
        if (srcActions && dstActions) dstActions.innerHTML = srcActions.innerHTML;
        document.getElementById('mail-fullscreen-overlay').classList.add('active');
        btn.classList.add('fullscreen'); icon.className = 'fas fa-expand'; label.textContent = 'Fullscreen'; btn.title = 'Back to Normal mode';
    }
}

function mailExitFullscreen() { MailApp.focusMode = 0; mailApplyFocusMode(); }

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && MailApp.focusMode === 2) mailExitFullscreen();
});

// ── Initialization ────────────────────────────────────────────────────────────

function initMailPanel() {
    console.log('[MailApp] Initializing panel...');
    mailLoadAccounts().then(() => {
        mailLoadFolder('INBOX');
        const syncOnOpen = document.getElementById('plugins.MAIL.sync_on_open');
        if (syncOnOpen && syncOnOpen.checked) setTimeout(mailSyncCurrent, 500);
        mailSetupConfigSync();
    });
}

// ── Config Auto-Sync ──────────────────────────────────────────────────────────

async function mailSetupConfigSync() {
    try {
        const res = await mailApiGet('/config');
        if (res.ok && res.config) {
            const cfg = res.config;
            ['sync_on_open', 'auto_detect_provider', 'max_messages'].forEach(key => {
                const el = document.getElementById('plugins.MAIL.' + key);
                if (!el || cfg[key] === undefined) return;
                if (el.type === 'checkbox') el.checked = Boolean(cfg[key]);
                else el.value = cfg[key];
            });
        }
    } catch(e) { console.warn('[MailApp] Could not load mail config:', e); }
}

async function mailSaveGlobalConfig() {
    try {
        const payload = {
            sync_on_open:         document.getElementById('plugins.MAIL.sync_on_open')?.checked,
            auto_detect_provider: document.getElementById('plugins.MAIL.auto_detect_provider')?.checked,
            max_messages:         parseInt(document.getElementById('plugins.MAIL.max_messages')?.value) || 100
        };
        const res = await mailApiPut('/config', payload);
        if (res.ok) window.dispatchEvent(new CustomEvent('hecos.tooltip', {detail: 'Global settings saved!'}));
        else mailShowToast('Error: ' + res.error, 'error');
    } catch(e) { mailShowToast('Error: ' + e, 'error'); }
}

// ── Multi-Account ─────────────────────────────────────────────────────────────

let mailAccountsCache = [];
let mailActiveEditId  = null;

async function mailLoadAccounts() {
    try {
        const res = await mailApiGet('/config');
        if (!res.ok || !res.config) return;
        mailAccountsCache = res.config.accounts || [];
        const activeId = res.config.active_account_id;

        // Toolbar switcher
        const switcher = document.getElementById('mail-account-switcher');
        if (switcher) {
            switcher.innerHTML = '';
            mailAccountsCache.forEach(acc => {
                const opt = document.createElement('option');
                opt.value = acc.id;
                opt.textContent = acc.name || acc.mail_address || 'Unnamed Account';
                if (acc.id === activeId) opt.selected = true;
                switcher.appendChild(opt);
            });
        }

        // Set active header
        if (activeId) MailApp.headers = { 'X-Mail-Account': activeId };

        // Config panel list
        const list = document.getElementById('mail-accounts-list');
        if (list) {
            mailRenderAccountsList();
            if (mailAccountsCache.length > 0) mailEditAccount(activeId || mailAccountsCache[0].id);
            else { const ed = document.getElementById('mail-account-editor'); if (ed) ed.style.display = 'none'; }
        }
    } catch(e) { console.warn('[MailApp] Could not load config:', e); }
}

function mailRenderAccountsList() {
    const list = document.getElementById('mail-accounts-list');
    if (!list) return;
    list.innerHTML = '';
    mailAccountsCache.forEach(acc => {
        const div = document.createElement('div');
        div.style.cssText = 'padding:10px 14px;border-radius:8px;background:var(--bg3);border:1px solid var(--border);cursor:pointer;transition:background 0.2s;display:flex;flex-direction:column;margin-bottom:4px;';
        if (acc.id === mailActiveEditId) div.style.borderColor = 'var(--accent)';
        div.onclick = () => mailEditAccount(acc.id);
        div.innerHTML = `<div style="font-weight:600;color:var(--text);font-size:13px;">${hecosEscapeHtml(acc.name || 'Unnamed')}</div>
                         <div style="font-size:11px;color:var(--muted);margin-top:4px;">${hecosEscapeHtml(acc.mail_address || 'No email set')}</div>`;
        list.appendChild(div);
    });
}

function mailAddNewAccount() {
    const newAcc = {
        id: (crypto.randomUUID ? crypto.randomUUID() : 'acc_' + Date.now()),
        name: 'New Account', mail_address: '', mail_app_password: '',
        smtp_host: '', smtp_port: 587, smtp_security: 'STARTTLS',
        imap_host: '', imap_port: 993, imap_security: 'SSL'
    };
    mailAccountsCache.push(newAcc);
    mailRenderAccountsList();
    mailEditAccount(newAcc.id);
}

function mailEditAccount(id) {
    const acc = mailAccountsCache.find(a => a.id === id);
    if (!acc) return;
    mailActiveEditId = id;
    const ed = document.getElementById('mail-account-editor');
    if (!ed) return;
    ed.style.display = 'block';
    document.getElementById('mail_edit_header').innerText = `Edit: ${acc.name || 'Account'}`;
    document.getElementById('mail_edit_account_id').value     = acc.id || '';
    document.getElementById('mail_edit_name').value           = acc.name || '';
    document.getElementById('mail_edit_email').value          = acc.mail_address || '';
    document.getElementById('mail_edit_password').value       = acc.mail_app_password || '';
    document.getElementById('mail_edit_smtp_host').value      = acc.smtp_host || '';
    document.getElementById('mail_edit_smtp_port').value      = acc.smtp_port || 587;
    document.getElementById('mail_edit_smtp_security').value  = acc.smtp_security || 'STARTTLS';
    document.getElementById('mail_edit_imap_host').value      = acc.imap_host || '';
    document.getElementById('mail_edit_imap_port').value      = acc.imap_port || 993;
    document.getElementById('mail_edit_imap_security').value  = acc.imap_security || 'SSL';
    mailRenderAccountsList();
    // Auto-sync cache from form on any input change
    const fields = ['mail_edit_name','mail_edit_email','mail_edit_password',
                    'mail_edit_smtp_host','mail_edit_smtp_port','mail_edit_smtp_security',
                    'mail_edit_imap_host','mail_edit_imap_port','mail_edit_imap_security'];
    fields.forEach(fid => {
        const el = document.getElementById(fid);
        if (el) el.oninput = mailSyncAccountFromForm;
    });
}

// Updates in-memory cache from form fields (no API call)
function mailSyncAccountFromForm() {
    const id  = document.getElementById('mail_edit_account_id')?.value;
    if (!id) return;
    const acc = mailAccountsCache.find(a => a.id === id);
    if (!acc) return;
    acc.name              = document.getElementById('mail_edit_name')?.value || '';
    acc.mail_address      = document.getElementById('mail_edit_email')?.value || '';
    acc.mail_app_password = document.getElementById('mail_edit_password')?.value || '';
    acc.smtp_host         = document.getElementById('mail_edit_smtp_host')?.value || '';
    acc.smtp_port         = parseInt(document.getElementById('mail_edit_smtp_port')?.value) || 587;
    acc.smtp_security     = document.getElementById('mail_edit_smtp_security')?.value || 'STARTTLS';
    acc.imap_host         = document.getElementById('mail_edit_imap_host')?.value || '';
    acc.imap_port         = parseInt(document.getElementById('mail_edit_imap_port')?.value) || 993;
    acc.imap_security     = document.getElementById('mail_edit_imap_security')?.value || 'SSL';
    // Also refresh the list label in real-time
    mailRenderAccountsList();
    document.getElementById('mail_edit_header').innerText = `Edit: ${acc.name || 'Account'}`;
}

// Persists all accounts + global settings to backend
async function mailSaveAccount(silent = false) {
    mailSyncAccountFromForm();
    try {
        const globalPayload = {
            accounts:             mailAccountsCache,
            sync_on_open:         document.getElementById('plugins.MAIL.sync_on_open')?.checked,
            auto_detect_provider: document.getElementById('plugins.MAIL.auto_detect_provider')?.checked,
            max_messages:         parseInt(document.getElementById('plugins.MAIL.max_messages')?.value) || 100
        };
        const res = await mailApiPut('/config', globalPayload);
        if (res.ok) {
            if (!silent) {
                const ind = document.getElementById('mail-account-save-indicator');
                if (ind) { ind.style.display = 'inline'; setTimeout(() => ind.style.display = 'none', 2000); }
            }
        } else if (!silent) {
            mailShowToast('Error saving: ' + res.error, 'error');
        }
    } catch(e) { if (!silent) mailShowToast('Network error: ' + e, 'error'); }
}

async function mailDeleteCurrentAccount() {
    if (!mailActiveEditId) return;
    mailShowConfirm('Delete this account? Local email cache will be orphaned.', 'Delete', async () => {
        mailAccountsCache = mailAccountsCache.filter(a => a.id !== mailActiveEditId);
        try {
            const res = await mailApiPut('/config', { accounts: mailAccountsCache });
            if (res.ok) { window.dispatchEvent(new CustomEvent('hecos.tooltip', {detail: 'Account deleted.'})); await mailLoadAccounts(); }
        } catch(e) { mailShowToast('Error: ' + e, 'error'); }
    });
}

async function mailTestAccount() {
    await mailSaveAccount();
    const saved = MailApp.headers;
    MailApp.headers = { ...saved, 'X-Mail-Account': mailActiveEditId };
    const btn = document.querySelector('#mail-account-editor button[onclick="mailTestAccount()"]');
    if (!btn) return;
    const old = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
    btn.disabled = true;
    try {
        const res = await mailApiPost('/test-account');
        if (res.ok) mailShowToast('Test passed! Server connection successful.', 'success');
        else {
            let info = res.error || '';
            if (res.smtp && !res.smtp.ok) info += '\nSMTP: ' + res.smtp.message;
            if (res.imap && !res.imap.ok) info += '\nIMAP: ' + res.imap.message;
            mailShowToast('Test failed: ' + info, 'error');
        }
    } catch(e) { mailShowToast('Fatal error: ' + e.message, 'error'); }
    finally { btn.innerHTML = old; btn.disabled = false; MailApp.headers = saved; }
}

async function mailSwitchAccount(accountId) {
    if (!accountId) return;
    try {
        const res = await mailApiPut('/config', { active_account_id: accountId });
        if (res.ok) {
            MailApp.headers = { 'X-Mail-Account': accountId };
            document.getElementById('mail-list').innerHTML = '<div class="mail-spinner active" style="margin:20px auto"></div>';
            mailLoadFolder('INBOX');
        }
    } catch(e) { console.warn('Failed to switch account:', e); }
}

function mailTogglePasswordVisibility() {
    const pwdEl = document.getElementById('mail_edit_password');
    const icon  = document.getElementById('mail-pwd-eye-icon');
    if (!pwdEl) return;
    pwdEl.type = (pwdEl.type === 'password') ? 'text' : 'password';
    icon.className = (pwdEl.type === 'text') ? 'fas fa-eye-slash' : 'fas fa-eye';
}

// ── Config Toggle ─────────────────────────────────────────────────────────────

async function mailToggleConfig() {
    const shell  = document.querySelector('.mail-shell');
    const config = document.getElementById('mail-config-panel');
    if (shell.style.display === 'none') {
        shell.style.display  = '';
        config.style.display = 'none';
        mailLoadFolder(MailApp.currentFolder);
    } else {
        shell.style.display  = 'none';
        config.style.display = 'block';
        await mailLoadAccounts();
        await mailSetupConfigSync();
    }
}

// ── Folder / List ─────────────────────────────────────────────────────────────

function mailSelectFolder(folder) {
    MailApp.currentFolder = folder;
    document.querySelectorAll('.mail-folder-item').forEach(el => el.classList.remove('active'));
    document.getElementById('mail-folder-' + folder)?.classList.add('active');
    mailSetFilter('all', false);
    mailLoadFolder(folder);
}

function mailSetFilter(filterType, reload = true) {
    MailApp.currentFilter = filterType;
    document.querySelectorAll('.mail-filter-btn').forEach(el => el.classList.remove('active'));
    document.getElementById('mail-filter-' + filterType)?.classList.add('active');
    if (reload) mailLoadFolder(MailApp.currentFolder);
}

function mailSearchDebounce(val) {
    clearTimeout(window.mailSearchTimer);
    window.mailSearchTimer = setTimeout(() => {
        MailApp.searchQuery = val.trim();
        mailLoadFolder(MailApp.currentFolder);
    }, 400);
}

async function mailLoadFolder(folder) {
    const listEl  = document.getElementById('mail-list');
    const titleEl = document.getElementById('mail-folder-title');
    const titles  = { INBOX: 'Inbox', SENT: 'Sent', DRAFTS: 'Drafts', TRASH: 'Trash', SPAM: 'Spam' };
    if (titleEl) titleEl.innerText = titles[folder] || folder;
    try {
        let ep = `/messages?folder=${folder}&limit=100`;
        if (MailApp.currentFilter === 'unread')  ep += '&unread=true';
        if (MailApp.currentFilter === 'starred') ep += '&starred=true';
        if (MailApp.searchQuery) ep += `&q=${encodeURIComponent(MailApp.searchQuery)}`;
        const res = await mailApiGet(ep);
        if (!res.ok) throw new Error(res.error);
        MailApp.messages = res.messages || [];
        mailRenderList(MailApp.messages);
        const stats = await mailApiGet('/stats');
        if (stats.ok) {
            const s = stats.stats;
            const badge = (id, val) => { const el = document.getElementById(id); if (el) el.innerText = val || ''; };
            badge('mail-badge-inbox', s.inbox_unread);
            badge('mail-badge-drafts', s.drafts);
            badge('mail-badge-starred', s.starred);
        }
    } catch(err) {
        if (listEl) listEl.innerHTML = `<div class="mail-empty text-danger"><i class="fas fa-exclamation-triangle"></i><div>Load error: ${err.message}</div></div>`;
    }
}

function mailRenderList(msgs) {
    const listEl = document.getElementById('mail-list');
    const countEl = document.getElementById('mail-count-label');
    if (countEl) countEl.innerText = `(${msgs.length})`;
    if (!msgs || msgs.length === 0) {
        let msg = 'No emails found';
        if (MailApp.currentFilter === 'unread') msg = 'No unread messages';
        if (MailApp.searchQuery) msg = 'No results for: ' + MailApp.searchQuery;
        listEl.innerHTML = `<div class="mail-empty"><i class="fas fa-envelope-open"></i><div class="mail-empty-title">${msg}</div></div>`;
        return;
    }
    const colors = ['#6c63ff','#f59e0b','#10b981','#3b82f6','#ec4899'];
    let html = '';
    msgs.forEach(m => {
        const color  = colors[m.from_addr.length % colors.length];
        const letter = (m.from_addr || '?')[0].toUpperCase();
        const d  = new Date(m.date);
        const df = (Date.now() - d.getTime() < 86400000)
            ? d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})
            : d.toLocaleDateString([], {day:'2-digit', month:'short'});
        html += `
        <div class="mail-msg-row ${m.read ? '' : 'unread'}" id="mail-row-${m.id}" onclick="mailOpenMessage('${m.id}')">
            <div class="mail-msg-avatar" style="background:${color}">${letter}</div>
            <div class="mail-msg-body">
                <div class="d-flex justify-content-between align-items-center">
                    <div class="mail-msg-from">${hecosEscapeHtml(m.from_addr)}</div>
                </div>
                <div class="mail-msg-subject">${hecosEscapeHtml(m.subject || '(No subject)')} ${m.has_attachments ? '<i class="fas fa-paperclip text-muted ms-1"></i>' : ''}</div>
                <div class="mail-msg-preview">${hecosEscapeHtml(m.preview)}</div>
            </div>
            <div class="mail-msg-meta">
                <div class="mail-msg-date">${df}</div>
                <div class="mail-msg-actions" onclick="event.stopPropagation()">
                    <button class="mail-msg-action-btn mail-star-btn ${m.starred ? 'starred' : ''}" onclick="mailToggleStar('${m.id}')">
                        <i class="${m.starred ? 'fas' : 'far'} fa-star"></i>
                    </button>
                    ${MailApp.currentFolder !== 'TRASH' ? `<button class="mail-msg-action-btn" onclick="mailDeleteMessage('${m.id}')"><i class="fas fa-trash"></i></button>` : ''}
                </div>
            </div>
        </div>`;
    });
    listEl.innerHTML = html;
}

// ── Preview ───────────────────────────────────────────────────────────────────

async function mailOpenMessage(id) {
    MailApp.selectedId = id;
    document.querySelectorAll('.mail-msg-row').forEach(el => el.classList.remove('active'));
    const row = document.getElementById('mail-row-' + id);
    if (row) { row.classList.add('active'); row.classList.remove('unread'); }
    document.getElementById('mail-content').classList.add('with-preview');
    const previewEl = document.getElementById('mail-preview');
    previewEl.style.display = 'flex';
    document.getElementById('mail-preview-body').innerHTML = '<div class="mail-preview-empty"><div class="mail-spinner active" style="width:24px;height:24px"></div></div>';
    try {
        const res = await mailApiGet(`/messages/${id}`);
        if (!res.ok) throw new Error(res.error);
        const m = res.message;
        document.getElementById('mail-preview-subject').innerText = m.subject || '(No subject)';
        const df = new Date(m.date).toLocaleString([], {day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit'});
        document.getElementById('mail-preview-meta').innerHTML = `
            <div><strong>From:</strong> ${hecosEscapeHtml(m.from_addr)}</div>
            <div><strong>To:</strong> ${hecosEscapeHtml(m.to_addrs)}</div>
            ${m.cc ? `<div><strong>Cc:</strong> ${hecosEscapeHtml(m.cc)}</div>` : ''}
            <div><strong>Date:</strong> ${df}</div>`;
        let bodyHtml = '';
        if (m.body_html) {
            const styleInject = '<style>body{margin:0;font-family:sans-serif;background:#fff;}img{max-width:100%;height:auto;}</style>';
            const safeHtml = hecosEscapeHtml(styleInject + m.body_html).replace(/"/g, '&quot;');
            bodyHtml = `<iframe srcdoc="${safeHtml}" sandbox="allow-same-origin allow-popups" style="width:100%;height:65vh;border:none;background:#fff;border-radius:8px;"></iframe>`;
        } else {
            bodyHtml = `<div class="mail-preview-body-text">${hecosEscapeHtml(m.body_text)}</div>`;
        }
        if (m.attachments && m.attachments.length > 0) {
            bodyHtml += `<div class="mt-4 pt-3 border-top border-secondary"><h6 class="text-muted"><i class="fas fa-paperclip"></i> Attachments (${m.attachments.length})</h6><div class="d-flex flex-wrap gap-2">`;
            m.attachments.forEach(att => {
                bodyHtml += `<div class="badge bg-dark border border-secondary p-2"><i class="far fa-file"></i> ${hecosEscapeHtml(att.filename)} (${Math.round(att.size/1024)} KB)</div>`;
            });
            bodyHtml += '</div></div>';
        }
        document.getElementById('mail-preview-body').innerHTML = bodyHtml;
        if (!m.read) {
            const s = await mailApiGet('/stats');
            if (s.ok) { const el = document.getElementById('mail-badge-inbox'); if (el) el.innerText = s.stats.inbox_unread || ''; }
        }
    } catch(err) {
        document.getElementById('mail-preview-body').innerHTML = `<div class="mail-preview-empty text-danger"><i class="fas fa-exclamation-triangle"></i><div>Cannot load message: ${err.message}</div></div>`;
    }
}

function mailClosePreview() {
    document.getElementById('mail-content').classList.remove('with-preview');
    document.getElementById('mail-preview').style.display = 'none';
    MailApp.selectedId = null;
    document.querySelectorAll('.mail-msg-row').forEach(el => el.classList.remove('active'));
}

// ── Message Actions ───────────────────────────────────────────────────────────

async function mailToggleStar(id) {
    const m = MailApp.messages.find(x => x.id === id);
    const current = m ? m.starred : false;
    const row = document.getElementById('mail-row-' + id);
    if (row) {
        const btn  = row.querySelector('.mail-star-btn');
        const icon = btn?.querySelector('i');
        if (current) { btn?.classList.remove('starred'); if(icon) icon.className = 'far fa-star'; }
        else         { btn?.classList.add('starred');    if(icon) icon.className = 'fas fa-star'; }
    }
    if (m) m.starred = !current;
    await mailApiPut(`/messages/${id}`, { starred: !current });
}

async function mailDeleteMessage(id) {
    const doDelete = async (permanent) => {
        await mailApiDelete(`/messages/${id}` + (permanent ? '?permanent=true' : ''));
        document.getElementById('mail-row-' + id)?.remove();
        MailApp.messages = MailApp.messages.filter(x => x.id !== id);
        if (MailApp.selectedId === id) mailClosePreview();
    };
    if (MailApp.currentFolder === 'TRASH') {
        mailShowConfirm('Delete message permanently?', 'Delete', () => doDelete(true));
    } else {
        doDelete(false);
    }
}

function mailDeleteActive() { if (MailApp.selectedId) mailDeleteMessage(MailApp.selectedId); }

// ── Sync ──────────────────────────────────────────────────────────────────────

async function mailSyncCurrent() {
    const spinner = document.getElementById('mail-sync-spinner');
    const btn     = document.getElementById('mail-sync-btn');
    if (spinner?.classList.contains('active')) return;
    spinner?.classList.add('active');
    if (btn) btn.disabled = true;
    window.dispatchEvent(new CustomEvent('hecos.tooltip', {detail: 'Syncing...'}));
    try {
        const res = await mailApiPost('/sync-all', {});
        if (res.ok) {
            const details = Object.entries(res.per_folder || {}).filter(([,v]) => v > 0).map(([k,v]) => `${k}: +${v}`).join(', ');
            const msg = res.synced > 0
                ? `Sync complete: ${res.synced} new messages${details ? ' (' + details + ')' : ''}.`
                : 'Sync complete. No new messages.';
            window.dispatchEvent(new CustomEvent('hecos.tooltip', {detail: msg}));
            if (res.stats) {
                const b = (id, v) => { const el = document.getElementById(id); if (el) el.innerText = v || ''; };
                b('mail-badge-inbox', res.stats.inbox_unread);
                b('mail-badge-drafts', res.stats.drafts);
            }
            mailLoadFolder(MailApp.currentFolder);
        } else { throw new Error(res.error); }
    } catch(err) { mailShowToast('Sync error: ' + err.message, 'error'); }
    finally { spinner?.classList.remove('active'); if (btn) btn.disabled = false; }
}

// ── Compose / Reply / Forward ─────────────────────────────────────────────────

function mailCompose() {
    document.getElementById('mail-compose-title').innerText = 'New Message';
    ['mail-compose-to','mail-compose-cc','mail-compose-subject','mail-compose-body','mail-compose-in-reply-to']
        .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    document.getElementById('mail-compose-modal').classList.add('active');
    setTimeout(() => document.getElementById('mail-compose-to')?.focus(), 100);
}

function mailCloseComposeModal() {
    document.getElementById('mail-compose-modal').classList.remove('active');
}

async function mailReplyActive() {
    if (!MailApp.selectedId) return;
    try { const res = await mailApiGet(`/messages/${MailApp.selectedId}`); if (res.ok) _openReplyModal(res.message, false); } catch(e) {}
}

async function mailReplyAllActive() {
    if (!MailApp.selectedId) return;
    try { const res = await mailApiGet(`/messages/${MailApp.selectedId}`); if (res.ok) _openReplyModal(res.message, true); } catch(e) {}
}

function _openReplyModal(m, replyAll) {
    document.getElementById('mail-compose-title').innerText = replyAll ? 'Reply All' : 'Reply';
    document.getElementById('mail-compose-to').value = m.from_addr;
    document.getElementById('mail-compose-cc').value = replyAll ? m.to_addrs : '';
    document.getElementById('mail-compose-in-reply-to').value = m.id;
    let subj = m.subject || '';
    if (!subj.toLowerCase().startsWith('re:')) subj = 'Re: ' + subj;
    document.getElementById('mail-compose-subject').value = subj;
    const quote = `\n\n\n--- On ${new Date(m.date).toLocaleString()}, ${m.from_addr} wrote ---\n> ${(m.body_text || '').replace(/\n/g, '\n> ')}`;
    document.getElementById('mail-compose-body').value = quote;
    document.getElementById('mail-compose-modal').classList.add('active');
    setTimeout(() => document.getElementById('mail-compose-body')?.focus(), 100);
}

async function mailForwardActive() {
    if (!MailApp.selectedId) return;
    try {
        const res = await mailApiGet(`/messages/${MailApp.selectedId}`);
        if (!res.ok) return;
        const m = res.message;
        document.getElementById('mail-compose-title').innerText = 'Forward';
        document.getElementById('mail-compose-to').value = '';
        document.getElementById('mail-compose-cc').value = '';
        document.getElementById('mail-compose-in-reply-to').value = m.id;
        let subj = m.subject || '';
        if (!subj.toLowerCase().startsWith('fwd:')) subj = 'Fwd: ' + subj;
        document.getElementById('mail-compose-subject').value = subj;
        document.getElementById('mail-compose-body').value = `\n\n\n--- Forwarded Message ---\nFrom: ${m.from_addr}\nDate: ${m.date}\nSubject: ${m.subject}\n\n${m.body_text || ''}`;
        document.getElementById('mail-compose-modal').classList.add('active');
        setTimeout(() => document.getElementById('mail-compose-to')?.focus(), 100);
    } catch(e) {}
}

async function mailSend() {
    const to      = document.getElementById('mail-compose-to').value.trim();
    const cc      = document.getElementById('mail-compose-cc').value.trim();
    const subj    = document.getElementById('mail-compose-subject').value.trim();
    const body    = document.getElementById('mail-compose-body').value.trim();
    const replyId = document.getElementById('mail-compose-in-reply-to').value;
    const title   = document.getElementById('mail-compose-title').innerText;
    if (!to) { mailShowToast('Please insert a recipient (To:)', 'warning'); return; }
    const btn = document.getElementById('mail-send-btn');
    const old = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
    btn.disabled = true;
    try {
        let res;
        if (replyId && title.includes('Reply'))   res = await mailApiPost(`/reply/${replyId}`, {body, reply_all: !!cc});
        else if (replyId && title.includes('Fwd') || title.includes('Forward')) res = await mailApiPost(`/forward/${replyId}`, {to, body: body.split('--- Forwarded')[0]});
        else res = await mailApiPost('/send', {to, cc, subject: subj, body, is_html: false});
        if (res.ok) {
            window.dispatchEvent(new CustomEvent('hecos.tooltip', {detail: 'Message sent!'}));
            mailCloseComposeModal();
            if (MailApp.currentFolder === 'SENT') mailLoadFolder('SENT');
        } else { throw new Error(res.error); }
    } catch(e) { mailShowToast('Error sending email: ' + e.message, 'error'); }
    finally { btn.innerHTML = old; btn.disabled = false; }
}

async function mailSaveDraft() {
    const data = {
        to:      document.getElementById('mail-compose-to').value,
        cc:      document.getElementById('mail-compose-cc').value,
        subject: document.getElementById('mail-compose-subject').value,
        body:    document.getElementById('mail-compose-body').value
    };
    try {
        const res = await mailApiPost('/drafts', data);
        if (res.ok) {
            window.dispatchEvent(new CustomEvent('hecos.tooltip', {detail: 'Draft saved.'}));
            mailCloseComposeModal();
            if (MailApp.currentFolder === 'DRAFTS') mailLoadFolder('DRAFTS');
        }
    } catch(e) { console.error('Draft error', e); }
}

// ── Auto-init ─────────────────────────────────────────────────────────────────
document.addEventListener('panelActivated', function(e) {
    if (e.detail && e.detail.panelId === 'mail') {
        initMailPanel();
    }
});
const mailPanel = document.getElementById('tab-mail');
if (mailPanel && mailPanel.classList.contains('active')) {
    initMailPanel();
}

// ── Hook into Hecos global Save button ───────────────────────────────────────
// When saveConfig() runs, we piggyback mail config persistence on top
(function() {
    const _origSaveConfig = window.saveConfig;
    window.saveConfig = async function(silent) {
        // Save mail accounts + global settings silently in background
        try { await mailSaveAccount(true); } catch(e) { console.warn('[MailApp] auto-save failed:', e); }
        if (typeof _origSaveConfig === 'function') return _origSaveConfig.call(this, silent);
    };
})();

