(function() {
    'use strict';

    // ── State ──────────────────────────────────────────────────────────────────
        window.ntfConfig = { destinations: {}, rules: {}, event_templates: {} };
        window.ntfAvailableTemplates = [];
        window.ntfAvailablePlugins = [];

        window.ntfEventDefs = [
            { id: "system_boot",        label: "System Boot",      desc: "Triggered when Hecos core finishes booting." },
            { id: "system_shutdown",    label: "System Shutdown",  desc: "Triggered when Hecos is safely shutting down." },
            { id: "system_error",       label: "System Error",     desc: "Triggered on critical system crash or exception." },
            { id: "flow_started",       label: "Flow Started",     desc: "Triggered when a Flow execution begins." },
            { id: "flow_completed",     label: "Flow Completed",   desc: "Triggered when a Flow finishes successfully." },
            { id: "flow_failed",        label: "Flow Failed",      desc: "Triggered when a Flow execution fails." },
            { id: "package_installed",  label: "Package Installed",desc: "Triggered when a new HPM plugin is installed." },
            { id: "security_login_failed", label: "Failed Login",  desc: "Triggered on invalid WebUI login attempt." },
            { id: "backup_started",     label: "Backup Started",   desc: "Triggered when a Global Backup starts." },
            { id: "backup_completed",   label: "Backup Completed", desc: "Triggered when a Global Backup finishes." },
            { id: "backup_failed",      label: "Backup Failed",    desc: "Triggered when a Global Backup fails." },
            { id: "custom",             label: "Test",             desc: "Custom event / manual test." },
        ];

    // ── Save ──────────────────────────────────────────────────────────────────
        window.ntfSave = async function(showToast) {
            try {
                const res = await fetch('/hecos/api/plugins/notifications/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(window.ntfConfig)
                });
                const data = await res.json();
                if (data.status === 'success') {
                    window.setSaveStatus('Saved ✓', true);
                    if (showToast) window.ntfToast('Notifications configuration saved.');
                } else {
                    window.setSaveStatus('Save error: ' + data.message, false);
                }
            } catch(e) {
                console.error('[NTF] Save error:', e);
                window.setSaveStatus('Network error while saving.', false);
            }
        };

        window.ntfSaveQuiet = function() { window.ntfSave(false); }

    // ── Init ──────────────────────────────────────────────────────────────────
        window.initNotificationsPanel = async function() {
            try {
                // Load config and available plugins in parallel
                const [cfgRes, plugRes, tplRes, mailAccRes] = await Promise.all([
                    fetch('/hecos/api/plugins/notifications/config'),
                    fetch('/hecos/api/plugins/notifications/available_plugins'),
                    fetch('/api/templates/'),
                    fetch('/hecos/api/plugins/notifications/mail_accounts')
                ]);

                const cfgData = await cfgRes.json();
                const plugData = await plugRes.json();
                const tplData = await tplRes.json();

                if (cfgData.status === 'success') {
                    window.ntfConfig = cfgData.config || {};
                    if (!window.ntfConfig.destinations) window.ntfConfig.destinations = {};
                    if (!window.ntfConfig.rules) window.ntfConfig.rules = {};
                    if (!window.ntfConfig.event_templates) window.ntfConfig.event_templates = {};
                }
                if (plugData.status === 'success') {
                    window.ntfAvailablePlugins = plugData.plugins || [];
                }
                if (tplData.ok) {
                    window.ntfAvailableTemplates = tplData.templates || [];
                }
                
                try {
                    window.ntfMailAccounts = await mailAccRes.json();
                } catch(e) {
                    window.ntfMailAccounts = [];
                }

                // Show warning if no plugins
                const warn = document.getElementById('ntf-no-plugins-warn');
                if (warn) warn.style.display = window.ntfAvailablePlugins.length === 0 ? 'block' : 'none';

                window.renderPanel();
            } catch (e) {
                console.error('[NOTIFICATIONS] Init error:', e);
                window.setSaveStatus('Network error while loading.', false);
            }
        };

    // ── Auto-init ─────────────────────────────────────────────────────────────
        let _ntfInitDone = false;
        window._waitForNtfPanel = function(callback) {
            if (document.getElementById('ntf-destinations-list')) {
                callback();
                return;
            }
            const observer = new MutationObserver((mutations, obs) => {
                if (document.getElementById('ntf-destinations-list')) {
                    obs.disconnect();
                    callback();
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        };

        window._ntfLoadDependencies = async function() {
            const deps = [
                '/hpm_plugin/notifications/web/assets/js/ntf_modals.js',
                '/hpm_plugin/notifications/web/assets/js/ntf_history.js',
                '/hpm_plugin/notifications/web/assets/js/ntf_ui.js'
            ];
            const v = window.VERSION || Date.now();
            
            for (const src of deps) {
                if (document.querySelector(`script[src^="${src}"]`)) continue;
                await new Promise((resolve, reject) => {
                    const script = document.createElement('script');
                    script.src = `${src}?v=${v}`;
                    script.onload = resolve;
                    script.onerror = reject;
                    document.head.appendChild(script);
                });
            }
        };

        window._waitForNtfPanel(async () => {
            if (_ntfInitDone) return;
            _ntfInitDone = true;
            console.log('[NOTIFICATIONS] Panel DOM ready - loading dependencies...');
            try {
                await window._ntfLoadDependencies();
                console.log('[NOTIFICATIONS] Dependencies loaded - initializing...');
                window.initNotificationsPanel();
            } catch(e) {
                console.error('[NOTIFICATIONS] Failed to load dependencies:', e);
            }
        });
})();
