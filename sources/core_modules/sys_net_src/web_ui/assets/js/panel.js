window.SysNetPanel = {
    updateProxyUrl: function() {
        const proto = document.getElementById('sysnet-proto').value;
        const host  = document.getElementById('sysnet-host').value.trim();
        const port  = document.getElementById('sysnet-port').value.trim();
        const user  = document.getElementById('sysnet-user').value.trim();
        const pass  = document.getElementById('sysnet-pass').value.trim();
        const urlEl = document.getElementById('sys-proxy-url');
        if (!proto || !host) { urlEl.value = ''; return; }
        let auth = '';
        if (user) auth = pass ? `${encodeURIComponent(user)}:${encodeURIComponent(pass)}@` : `${encodeURIComponent(user)}@`;
        urlEl.value = `${proto}://${auth}${host}${port ? ':'+port : ''}`;
    },

    parseProxyUrl: function() {
        const url = document.getElementById('sys-proxy-url').value.trim();
        if (!url) { this.clearProxyFields(); return; }
        try {
            const m = url.match(/^(\w+):\/\/(?:([^:@]+)?(?::([^@]+))?@)?([^:/]+)(?::(\d+))?/);
            if (m) {
                const protoEl = document.getElementById('sysnet-proto');
                if ([...protoEl.options].some(o => o.value === m[1])) protoEl.value = m[1];
                document.getElementById('sysnet-user').value = m[2] ? decodeURIComponent(m[2]) : '';
                document.getElementById('sysnet-pass').value = m[3] ? decodeURIComponent(m[3]) : '';
                document.getElementById('sysnet-host').value = m[4] || '';
                document.getElementById('sysnet-port').value = m[5] || '';
            }
        } catch(e) {}
    },

    applyProxyPreset: function(proto, host, port) {
        document.getElementById('sysnet-proto').value = proto;
        document.getElementById('sysnet-host').value  = host;
        document.getElementById('sysnet-port').value  = port;
        document.getElementById('sysnet-user').value  = '';
        document.getElementById('sysnet-pass').value  = '';
        this.updateProxyUrl();
    },

    clearProxy: function() {
        this.clearProxyFields();
        document.getElementById('sys-proxy-url').value = '';
    },

    clearProxyFields: function() {
        document.getElementById('sysnet-proto').value = '';
        document.getElementById('sysnet-host').value  = '';
        document.getElementById('sysnet-port').value  = '';
        document.getElementById('sysnet-user').value  = '';
        document.getElementById('sysnet-pass').value  = '';
    },

    _proxyTestEvt: null,

    runProxyTest: function() {
        const proxyUrl = document.getElementById('sys-proxy-url').value.trim();
        const logPanel = document.getElementById('sysnet-log-panel');
        const logOut   = document.getElementById('sysnet-log-output');
        const spinner  = document.getElementById('sysnet-test-spinner');
        const btn      = document.getElementById('sysnet-test-btn');

        const dot = document.getElementById('sysnet-status-dot');
        const txt = document.getElementById('sysnet-status-text');
        const loc = document.getElementById('sysnet-status-loc');

        // Reset UI
        logPanel.style.display = 'block';
        logOut.innerHTML = '';
        spinner.style.display = 'inline';
        btn.disabled = true;
        
        dot.style.background = 'var(--yellow)';
        dot.style.boxShadow = '0 0 5px var(--yellow)';
        txt.style.color = 'var(--yellow)';
        txt.textContent = 'Verifica in corso...';
        loc.innerHTML = '';
        let proxySuccess = false;

        if (this._proxyTestEvt) { this._proxyTestEvt.close(); this._proxyTestEvt = null; }

        const encoded = encodeURIComponent(proxyUrl);
        this._proxyTestEvt = new EventSource(`/api/sysnet/test-proxy?url=${encoded}`);

        const colors = { OK: 'var(--green)', ERR: 'var(--red)', WARN: 'var(--yellow)', DONE: 'var(--muted)', INFO: 'var(--text)' };

        this._proxyTestEvt.onmessage = (e) => {
            const data = JSON.parse(e.data);
            
            if (data.level === 'PAYLOAD') {
                try {
                    const payload = JSON.parse(data.msg);
                    if (payload.status === 'active') {
                        proxySuccess = true;
                        dot.style.background = 'var(--green)';
                        dot.style.boxShadow = '0 0 5px var(--green)';
                        txt.style.color = 'var(--green)';
                        txt.textContent = 'Attivo';
                        loc.innerHTML = `🌍 IP: <b>${payload.ip}</b> — Regione: <b>${payload.loc}</b>`;
                    }
                } catch(err) {}
                return;
            }

            const color = colors[data.level] || colors.INFO;
            const line = document.createElement('div');
            // Safe escape function inside
            const escapeHtml = (unsafe) => {
                return (unsafe||'').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
            };
            line.innerHTML = `<span style="color:var(--muted);user-select:none;">[${data.ts}]</span> <span style="color:${color}">${escapeHtml(data.msg)}</span>`;
            logOut.appendChild(line);
            logOut.scrollTop = logOut.scrollHeight;

            if (data.level === 'DONE') {
                this._proxyTestEvt.close();
                this._proxyTestEvt = null;
                spinner.style.display = 'none';
                btn.disabled = false;
                
                if (!proxySuccess) {
                    dot.style.background = 'var(--red)';
                    dot.style.boxShadow = '0 0 5px var(--red)';
                    txt.style.color = 'var(--red)';
                    txt.textContent = 'Inattivo / Fallito';
                }
            }
        };

        this._proxyTestEvt.onerror = () => {
            const line = document.createElement('div');
            line.innerHTML = `<span style="color:var(--red)"><i class="fas fa-exclamation-circle"></i> Connessione SSE interrotta.</span>`;
            logOut.appendChild(line);
            spinner.style.display = 'none';
            btn.disabled = false;
            dot.style.background = 'var(--red)';
            dot.style.boxShadow = '0 0 5px var(--red)';
            txt.style.color = 'var(--red)';
            txt.textContent = 'Errore Connessione';
            if (this._proxyTestEvt) { this._proxyTestEvt.close(); this._proxyTestEvt = null; }
        };
    },
    
    // Register the custom load/save handlers for the HPM dynamically loaded panel
    init: function() {
        console.log("SysNetPanel initialized.");
    }
};

// If HPM provides a way to register config mappers for dynamic panels, we hook into it here
// We can use the global events
document.addEventListener("hpm_panel_load_sys_net", function(e) {
    const data = e.detail || {};
    const enabled = data.proxy_enabled || false;
    const url = data.proxy_url || "";
    
    document.getElementById('sys-proxy-enabled').checked = enabled;
    const urlEl = document.getElementById('sys-proxy-url');
    if (urlEl) {
        urlEl.value = url;
        if (url) SysNetPanel.parseProxyUrl();
    }
});

document.addEventListener("hpm_panel_save_sys_net", function(e) {
    // Modify the detail object in place to return data to the caller
    e.detail.proxy_enabled = document.getElementById('sys-proxy-enabled').checked;
    e.detail.proxy_url = document.getElementById('sys-proxy-url').value.trim();
});

SysNetPanel.init();
