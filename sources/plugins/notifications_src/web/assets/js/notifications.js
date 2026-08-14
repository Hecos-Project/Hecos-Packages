(function() {
    'use strict';

    // ── State ──────────────────────────────────────────────────────────────────
    let nConfig = { enabled: false, destinations: {}, rules: {} };
    let availablePlugins = [];

    const EVENT_DEFS = [
        { id: "system_boot",        label: "System Boot",      desc: "Triggered when Hecos core finishes booting." },
        { id: "system_shutdown",    label: "System Shutdown",  desc: "Triggered when Hecos is safely shutting down." },
        { id: "system_error",       label: "System Error",     desc: "Triggered on critical system crash or exception." },
        { id: "flow_started",       label: "Flow Started",     desc: "Triggered when a Flow execution begins." },
        { id: "flow_completed",     label: "Flow Completed",   desc: "Triggered when a Flow finishes successfully." },
        { id: "flow_failed",        label: "Flow Failed",      desc: "Triggered when a Flow execution fails." },
        { id: "package_installed",  label: "Package Installed",desc: "Triggered when a new HPM plugin is installed." },
        { id: "security_login_failed", label: "Failed Login",  desc: "Triggered on invalid WebUI login attempt." },
        { id: "custom",             label: "Test",             desc: "Custom event / manual test." },
    ];

    // ── Inline modal (no external dependency) ────────────────────────────────
    window._ntfModalResolve = null;
    function ntfConfirm(msg, confirmLabel) {
        return new Promise(resolve => {
            document.getElementById('ntf-confirm-text').textContent = msg;
            if (confirmLabel) document.getElementById('ntf-confirm-ok').textContent = confirmLabel;
            const modal = document.getElementById('ntf-confirm-modal');
            modal.style.display = 'flex';
            window._ntfModalResolve = (result) => {
                modal.style.display = 'none';
                resolve(result);
            };
        });
    }

    function ntfToast(msg, isError) {
        if (window.showToast) {
            window.showToast(msg, isError ? 'error' : 'success');
        } else {
            console.log('[NTF]', msg);
        }
    }

    function setSaveStatus(msg, isOk) {
        const el = document.getElementById('ntf-save-status');
        if (el) {
            el.textContent = msg;
            el.style.color = isOk ? 'var(--accent)' : '#ff6b6b';
        }
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    window.initNotificationsPanel = async function() {
        try {
            // Load config and available plugins in parallel
            const [cfgRes, plugRes] = await Promise.all([
                fetch('/hecos/api/plugins/notifications/config'),
                fetch('/hecos/api/plugins/notifications/available_plugins')
            ]);

            const cfgData = await cfgRes.json();
            const plugData = await plugRes.json();

            if (cfgData.status === 'success') {
                nConfig = cfgData.config;
            }
            if (plugData.status === 'success') {
                availablePlugins = plugData.plugins || [];
            }

            // Show warning if no plugins
            const warn = document.getElementById('ntf-no-plugins-warn');
            if (warn) warn.style.display = availablePlugins.length === 0 ? 'block' : 'none';

            renderPanel();
        } catch (e) {
            console.error('[NOTIFICATIONS] Init error:', e);
            setSaveStatus('Network error while loading.', false);
        }
    };

    // ── Render ────────────────────────────────────────────────────────────────
    function renderPanel() {
        // Master switch
        const sw = document.getElementById('notifications-master-switch');
        if (sw) sw.checked = nConfig.enabled;

        // Add buttons
        renderAddButtons();

        // Destinations
        renderDestinations();

        // Rules
        renderRules();
    }

    function renderAddButtons() {
        const container = document.getElementById('ntf-add-buttons');
        if (!container) return;
        container.innerHTML = '';

        if (availablePlugins.length === 0) {
            container.innerHTML = '<span style="font-size:12px; color:var(--muted);">No plugins available</span>';
            return;
        }

        availablePlugins.forEach(plug => {
            const btn = document.createElement('button');
            btn.className = 'btn btn-secondary';
            btn.style.cssText = 'padding:4px 10px; font-size:12px;';
            btn.innerHTML = `<i class="${plug.icon}"></i> + ${plug.label}`;
            btn.onclick = () => ntfAddDestination(plug);
            container.appendChild(btn);
        });
    }

    function renderDestinations() {
        const container = document.getElementById('ntf-destinations-list');
        if (!container) return;

        const keys = Object.keys(nConfig.destinations);
        if (keys.length === 0) {
            container.innerHTML = '<div style="font-size:12px; color:var(--muted); font-style:italic; padding:8px 0;">No destinations configured. Add a contact using the buttons above.</div>';
            return;
        }

        container.innerHTML = '';
        keys.forEach(key => {
            const uri = nConfig.destinations[key];
            const plug = guessPluginFromUri(uri);
            const row = document.createElement('div');
            row.style.cssText = 'display:flex; gap:10px; align-items:center; padding:10px; background:var(--glass); border:1px solid var(--border); border-radius:8px;';

            const iconHtml = plug ? `<i class="${plug.icon}" style="color:var(--accent); width:18px; text-align:center;"></i>` : '<i class="fas fa-bell" style="width:18px;"></i>';
            const hintHtml = plug ? `<span style="font-size:10px; color:var(--muted);">${plug.hint}</span>` : '';

            row.innerHTML = `
                ${iconHtml}
                <div style="flex:0 0 130px;">
                    <input type="text" value="${key}" placeholder="Contact ID"
                        class="config-input" style="width:100%; font-size:12px;"
                        onblur="window.ntfRenameKey('${key}', this.value)">
                </div>
                <div style="flex:1;">
                    <input type="text" value="${uri}" placeholder="${plug ? plug.hint : 'MAIL:email@example.com'}"
                        class="config-input" style="width:100%; font-size:12px;"
                        data-dest-key="${key}"
                        onblur="window.ntfUpdateUri('${key}', this.value)">
                    ${hintHtml}
                </div>
                <button class="btn btn-secondary" title="Remove" style="padding:4px 8px; flex-shrink:0;"
                    onclick="window.ntfRemoveDest('${key}')"><i class="fas fa-trash"></i></button>
            `;
            container.appendChild(row);
        });
    }

    function guessPluginFromUri(uri) {
        if (!uri) return null;
        const upper = uri.toUpperCase();
        return availablePlugins.find(p => upper.startsWith(p.tag + ':')) || null;
    }

    function renderRules() {
        const table = document.getElementById('ntf-rules-table');
        if (!table) return;
        table.innerHTML = '';

        const destKeys = Object.keys(nConfig.destinations);

        EVENT_DEFS.forEach(evt => {
            const tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid rgba(255,255,255,0.04)';

            const selectedKeys = nConfig.rules[evt.id] || [];
            let selectCell;

            if (destKeys.length === 0) {
                selectCell = `<span style="font-size:11px; color:var(--muted);">Add a destination first</span>`;
            } else {
                let opts = destKeys.map(k => {
                    const sel = selectedKeys.includes(k) ? 'selected' : '';
                    const plug = guessPluginFromUri(nConfig.destinations[k]);
                    const icon = plug ? plug.tag : '?';
                    return `<option value="${k}" ${sel}>[${icon}] ${k}</option>`;
                }).join('');
                selectCell = `<select multiple class="select-sm" style="width:100%; min-height:52px;"
                    onchange="window.ntfUpdateRule('${evt.id}', this)">${opts}</select>`;
            }

            tr.innerHTML = `
                <td style="padding:10px 8px; font-weight:600;">${evt.label}</td>
                <td style="padding:10px 8px; color:var(--muted); font-size:12px;">${evt.desc}</td>
                <td style="padding:10px 8px;">${selectCell}</td>
            `;
            table.appendChild(tr);
        });
    }

    // ── Actions ───────────────────────────────────────────────────────────────
    window.ntfAddDestination = function(plug) {
        const key = (plug.tag.toLowerCase()) + '_' + Date.now().toString().slice(-4);
        const prefix = plug.platform
            ? `${plug.tag}:${plug.platform}:`
            : `${plug.tag}:`;
        nConfig.destinations[key] = prefix;
        renderDestinations();
        renderRules();
        ntfSaveQuiet();
    };

    window.ntfRenameKey = function(oldKey, newKey) {
        newKey = newKey.trim();
        if (!newKey || oldKey === newKey) return;
        if (nConfig.destinations[newKey] !== undefined) {
            ntfToast('Contact ID already exists!', true);
            renderDestinations();
            return;
        }
        nConfig.destinations[newKey] = nConfig.destinations[oldKey];
        delete nConfig.destinations[oldKey];
        // Update rules
        for (const evtId in nConfig.rules) {
            nConfig.rules[evtId] = (nConfig.rules[evtId] || []).map(k => k === oldKey ? newKey : k);
        }
        renderDestinations();
        renderRules();
        ntfSaveQuiet();
    };

    window.ntfUpdateUri = function(key, newUri) {
        nConfig.destinations[key] = newUri;
        renderDestinations();
        renderRules();
        ntfSaveQuiet();
    };

    window.ntfRemoveDest = async function(key) {
        const ok = await ntfConfirm(`Remove destination "${key}"?`, 'Remove');
        if (!ok) return;
        delete nConfig.destinations[key];
        for (const evtId in nConfig.rules) {
            nConfig.rules[evtId] = (nConfig.rules[evtId] || []).filter(k => k !== key);
        }
        renderDestinations();
        renderRules();
        ntfSaveQuiet();
    };

    window.ntfUpdateRule = function(evtId, selectElem) {
        nConfig.rules[evtId] = Array.from(selectElem.selectedOptions).map(o => o.value);
        ntfSaveQuiet();
    };

    // ── Save ──────────────────────────────────────────────────────────────────
    window.ntfSave = async function(showToast) {
        nConfig.enabled = document.getElementById('notifications-master-switch').checked;
        try {
            const res = await fetch('/hecos/api/plugins/notifications/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(nConfig)
            });
            const data = await res.json();
            if (data.status === 'success') {
                setSaveStatus('Saved ✓', true);
                if (showToast) ntfToast('Notifications configuration saved.');
            } else {
                setSaveStatus('Save error: ' + data.message, false);
            }
        } catch(e) {
            console.error('[NTF] Save error:', e);
            setSaveStatus('Network error while saving.', false);
        }
    };

    function ntfSaveQuiet() { window.ntfSave(false); }

    // ── Test ──────────────────────────────────────────────────────────────────
    window.ntfTest = async function() {
        const ok = await ntfConfirm('Send a test notification to all configured destinations now?', 'Send');
        if (!ok) return;
        try {
            const res = await fetch('/hecos/api/plugins/notifications/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: '{}'
            });
            const data = await res.json();
            if (data.status === 'success') ntfToast('Test notification dispatched!');
            else ntfToast('Error: ' + data.message, true);
        } catch(e) {
            ntfToast('Network error during test.', true);
        }
    };

    // ── Auto-init ─────────────────────────────────────────────────────────────
    // -- Auto-init with MutationObserver ---------------------------------------
    let _ntfInitDone = false;
    function _waitForNtfPanel(callback) {
        if (document.getElementById('notifications-master-switch')) {
            callback();
            return;
        }
        const observer = new MutationObserver((mutations, obs) => {
            if (document.getElementById('notifications-master-switch')) {
                obs.disconnect();
                callback();
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }

    _waitForNtfPanel(() => {
        if (_ntfInitDone) return;
        _ntfInitDone = true;
        console.log('[NOTIFICATIONS] Panel DOM ready - initializing...');
        window.initNotificationsPanel();
    });
})();
