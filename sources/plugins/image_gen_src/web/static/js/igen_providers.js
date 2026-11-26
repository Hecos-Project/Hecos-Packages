/**
 * igen_providers.js - Image Gen Panel: Provider & Model Logic
 * Handles provider dropdown (Local Backends first, then Cloud),
 * model fetching with retry, key status check, tab visibility,
 * SwarmUI test & auto-start, cloud enable toggle, and aspect ratio.
 */

// ── Tab switching ────────────────────────────────────────────────────────────

window.switchIgenTab = function(targetId, btn) {
    document.querySelectorAll('.igen-tab-pane').forEach(function(p) {
        p.style.display = 'none';
        p.classList.remove('igen-tab-pane-active');
    });
    document.querySelectorAll('.igen-tab-btn').forEach(function(b) {
        b.classList.remove('igen-tab-active');
    });
    var pane = document.getElementById(targetId);
    if (pane) { pane.style.display = 'block'; pane.classList.add('igen-tab-pane-active'); }
    if (btn) btn.classList.add('igen-tab-active');
};

// ── Provider Changed ─────────────────────────────────────────────────────────

window.onProviderChanged = async function(userTriggered, _attempt) {
    if (userTriggered === undefined) userTriggered = false;
    if (_attempt === undefined) _attempt = 0;

    var provSel  = document.getElementById('igen-provider');
    var modelSel = document.getElementById('igen-model');
    if (!provSel || !modelSel) return;

    // ── Populate provider list (Local Backends first) ────────────────────────
    var localProviders = [
        { id: 'swarmui',        name: '\uD83D\uDDA5\uFE0F SwarmUI (Local Backend)' },
    ];
    var cloudProviders = [
        { id: 'pollinations',   name: 'Pollinations (Free, Fast)' },
        { id: 'gemini',         name: 'Google Gemini' },
        { id: 'gemini_native',  name: 'Google Gemini Native (Flash)' },
        { id: 'openai',         name: 'OpenAI DALL-E' },
        { id: 'stability',      name: 'Stability AI' },
        { id: 'airforce',       name: 'Airforce (Free)' },
        { id: 'huggingface',    name: 'Hugging Face Inference API' },
        { id: 'horde',          name: '\uD83C\uDF10 AI Horde (Free / No Censorship)' },
    ];

    if (provSel.options.length === 0) {
        var localGroup = document.createElement('optgroup');
        localGroup.label = '\uD83D\uDCBB Local Backends';
        var cloudGroup = document.createElement('optgroup');
        cloudGroup.label = '\u2601\uFE0F Cloud Providers';

        localProviders.forEach(function(p) {
            var opt = document.createElement('option');
            opt.value = p.id; opt.textContent = p.name;
            localGroup.appendChild(opt);
        });
        cloudProviders.forEach(function(p) {
            var opt = document.createElement('option');
            opt.value = p.id; opt.textContent = p.name;
            cloudGroup.appendChild(opt);
        });
        provSel.appendChild(localGroup);
        provSel.appendChild(cloudGroup);

        var initialProv = provSel.getAttribute('data-initial-val') || 'swarmui';
        provSel.value = initialProv;
    }

    var isLocal  = (provSel.value === 'swarmui');
    var isHF     = (provSel.value === 'huggingface');
    var isHorde  = (provSel.value === 'horde');

    // ── Show/hide local backend panel ────────────────────────────────────────
    var localWrapper = document.getElementById('igen-local-backend-wrapper');
    if (localWrapper) localWrapper.style.display = isLocal ? 'block' : 'none';
    var fluxParamsRow = document.getElementById('igen-flux-params-row');
    if (fluxParamsRow) fluxParamsRow.style.display = isLocal ? '' : 'none';
    if (isLocal && _attempt === 0 && typeof window.checkSwarmUIBadgeSilent === 'function') {
        window.checkSwarmUIBadgeSilent();
    }

    // ── Show/hide VAE + LoRA tabs ────────────────────────────────────────────
    var vaeTabBtn   = document.getElementById('igen-tab-btn-vae');
    var lorasTabBtn = document.getElementById('igen-tab-btn-loras');
    // We intentionally do NOT hide these tabs anymore as per user request
    if (vaeTabBtn)   vaeTabBtn.style.display   = 'inline-flex';
    if (lorasTabBtn) lorasTabBtn.style.display = 'inline-flex';

    // If switching away from local while VAE/LoRA tab is active, reset to Model
    if (!isLocal) {
        var activePane = document.querySelector('.igen-tab-pane.igen-tab-pane-active');
        if (activePane && (activePane.id === 'igen-tab-vae' || activePane.id === 'igen-tab-loras')) {
            var modelBtn = document.querySelector('[data-target="igen-tab-model"]');
            window.switchIgenTab('igen-tab-model', modelBtn);
        }
    }

    // ── Show/hide HuggingFace sub-provider ───────────────────────────────────
    var hfProviderWrap = document.getElementById('igen-hf-provider-wrapper');
    if (hfProviderWrap) hfProviderWrap.style.display = isHF ? 'block' : 'none';

    var hfWrap = document.getElementById('igen-hf-explorer-wrapper');
    if (hfWrap) hfWrap.style.display = isHF ? 'block' : 'none';

    // ── Show/hide Horde panel ────────────────────────────────────────────────
    var hordeWrap = document.getElementById('igen-horde-wrapper');
    if (hordeWrap) hordeWrap.style.display = isHorde ? 'block' : 'none';
    if (isHorde && userTriggered) {
        setTimeout(function() { window.checkHordeAccount(); }, 500);
    }

    // ── Show/hide cloud panel & API key ─────────────────────────────────────
    var cloudWrapper   = document.getElementById('igen-cloud-wrapper');
    var apiKeyWrapper  = document.getElementById('igen-api-key-wrapper');
    var cloudProbeWrap = document.getElementById('igen-cloud-probe-wrapper');
    var nologoWrap     = document.getElementById('igen-nologo-wrapper');
    if (cloudWrapper) cloudWrapper.style.display = isLocal ? 'none' : 'block';
    if (cloudProbeWrap) cloudProbeWrap.style.display = isLocal ? 'none' : 'block';
    if (nologoWrap) nologoWrap.style.display = isLocal ? 'none' : 'flex';
    // For Horde: API key section is inside the horde block, so hide generic one
    if (apiKeyWrapper) apiKeyWrapper.style.display = isHorde ? 'none' : 'block';

    // ── Fetch models ─────────────────────────────────────────────────────────
    var statusEl = document.getElementById('igen-model-status');
    if (statusEl && _attempt === 0) statusEl.textContent = '\u23F3 loading...';

    try {
        var res = await fetch('/hecos/api/plugins/image_gen/models?provider=' + encodeURIComponent(provSel.value));
        if (!res.ok) throw new Error('HTTP ' + res.status);

        var data = await res.json();
        if (!data.ok) throw new Error(data.error || 'API returned ok=false');

        var currentSelection = userTriggered ? '' : (modelSel.getAttribute('data-initial-val') || modelSel.value);
        if (!userTriggered && modelSel.hasAttribute('data-initial-val')) {
            modelSel.removeAttribute('data-initial-val'); // Use only once
        }
        modelSel.innerHTML = '';
        if (data.models && data.models.length) {
            data.models.forEach(function(m) {
                var opt = document.createElement('option');
                opt.value = opt.textContent = m;
                modelSel.appendChild(opt);
            });
            if (currentSelection) {
                if (data.models.includes(currentSelection)) {
                    modelSel.value = currentSelection;
                } else {
                    var matched = data.models.find(function(m) { return m.includes(currentSelection); });
                    if (matched) {
                        modelSel.value = matched;
                    } else {
                        // Preserve saved model even if not currently in provider list
                        var savedOpt = document.createElement('option');
                        savedOpt.value = currentSelection;
                        savedOpt.textContent = currentSelection + ' (saved)';
                        modelSel.insertBefore(savedOpt, modelSel.firstChild);
                        modelSel.value = currentSelection;
                    }
                }
            }
        } else if (currentSelection) {
            // Backend offline / returned 0 models — NEVER wipe configured model to ""!
            var offlineOpt = document.createElement('option');
            offlineOpt.value = currentSelection;
            offlineOpt.textContent = currentSelection + (isLocal ? ' (SwarmUI offline — saved)' : ' (saved)');
            modelSel.appendChild(offlineOpt);
            modelSel.value = currentSelection;
        }

        // ── Fetch VAEs and LoRAs for SwarmUI ─────────────────────────────────
        if (_attempt === 0) {
            try {
                var vSel = document.getElementById('igen-vae');
                var lSel = document.getElementById('igen-loras');
                var vPending = (!userTriggered && vSel && vSel.hasAttribute('data-initial-val'))
                    ? vSel.getAttribute('data-initial-val') : null;
                if (vSel && vSel.hasAttribute('data-initial-val')) {
                    vSel.removeAttribute('data-initial-val');
                }
                var vCur = userTriggered ? '' : (vPending !== null ? vPending : (vSel ? vSel.value : ''));

                var lCur = userTriggered
                    ? []
                    : (Array.isArray(window._igenPendingLoras)
                        ? window._igenPendingLoras.slice()
                        : (window._selectedLoras instanceof Set && window._selectedLoras.size > 0
                            ? Array.from(window._selectedLoras)
                            : Array.from((lSel || {}).selectedOptions || []).map(function(o) { return o.value; })));
                window._igenPendingLoras = null;

                var vRes = await fetch('/hecos/api/plugins/image_gen/vaes');
                var vData = await vRes.json();

                var lRes = await fetch('/hecos/api/plugins/image_gen/local_compat_info');
                var lData = await lRes.json();

                window._swarmui_compat = lData;

                if (vSel) {
                    vSel.innerHTML = '<option value="">Default (Automatic)</option>';
                    if (vData.ok && vData.models && vData.models.length) {
                        vData.models.forEach(function(m) {
                            var o = document.createElement('option'); o.value = o.textContent = m;
                            vSel.appendChild(o);
                        });
                    }
                    if (vCur) {
                        var hasV = Array.from(vSel.options).some(function(o) { return o.value === vCur; });
                        if (!hasV) {
                            var vo = document.createElement('option');
                            vo.value = vCur; vo.textContent = vCur + ' (saved)';
                            vSel.appendChild(vo);
                        }
                        vSel.value = vCur;
                    }
                }

                if (lSel) {
                    lSel.innerHTML = '';
                    var seenLoras = new Set();
                    if (lData.ok && lData.loras && lData.loras.length) {
                        window._swarmui_loras_data = lData.loras;
                        lData.loras.forEach(function(m) {
                            var o = document.createElement('option');
                            o.value = m.name; o.textContent = m.name;
                            if (lCur.includes(m.name)) o.selected = true;
                            lSel.appendChild(o);
                            seenLoras.add(m.name);
                        });
                    }
                    // Preserve any saved LoRAs when SwarmUI is offline
                    lCur.forEach(function(name) {
                        if (name && !seenLoras.has(name)) {
                            var o = document.createElement('option');
                            o.value = name; o.textContent = name; o.selected = true;
                            lSel.appendChild(o);
                        }
                    });
                }

                window._selectedLoras = new Set(lCur);
                if (typeof window.renderLoRAList === 'function') window.renderLoRAList();
                if (typeof window.updateLoRACompatibility === 'function') window.updateLoRACompatibility();

            } catch(ex) { console.warn('[ImageGen] Failed fetching VAEs/LoRAs:', ex); }
        }

        if (statusEl) statusEl.textContent = '';
        if (userTriggered) _igenDebounceSave();
        window._igenUpdateKeyStatus(provSel.value);

    } catch (e) {
        var MAX_RETRIES = 5, RETRY_DELAY_MS = 800;
        if (_attempt < MAX_RETRIES) {
            if (statusEl) statusEl.textContent = '\u23F3 Retrying (' + (_attempt+1) + '/' + MAX_RETRIES + ')...';
            console.warn('[ImageGen] Models fetch failed (attempt ' + (_attempt+1) + '): ' + e.message + '. Retrying...');
            setTimeout(function() { window.onProviderChanged(userTriggered, _attempt + 1); }, RETRY_DELAY_MS);
            return;
        }
        if (statusEl) statusEl.textContent = '\u26A0\uFE0F Could not load - click Refresh';
        console.error('[ImageGen] Fetch models error after all retries:', e);
        if (userTriggered) _igenDebounceSave();
        window._igenUpdateKeyStatus(provSel.value);
    }
};

// ── Key Status ───────────────────────────────────────────────────────────────

window._igenUpdateKeyStatus = async function(provider) {
    var stEl = document.getElementById('igen-key-source-text');
    if (!stEl) return;

    if (provider === 'pollinations' || provider === 'airforce' || provider === 'swarmui') {
        stEl.textContent = provider === 'swarmui' ? 'Local backend (no key needed)' : 'Free provider (no key needed)';
        stEl.parentElement.style.color = 'var(--ok, #2ecc71)';
        return;
    }
    if (provider === 'horde') {
        var hasKey = (document.getElementById('horde-api-key') && document.getElementById('horde-api-key').value.trim().length > 0);
        stEl.textContent = hasKey ? 'Horde key configured' : 'Anonymous (no key)';
        stEl.parentElement.style.color = hasKey ? 'var(--ok, #2ecc71)' : 'var(--muted)';
        return;
    }

    stEl.textContent = 'Checking...';
    stEl.parentElement.style.color = 'var(--muted)';
    try {
        var r = await fetch('/hecos/api/plugins/image_gen/key_status?provider=' + encodeURIComponent(provider));
        var d = await r.json();
        if (d.ok) {
            stEl.textContent = d.source;
            stEl.parentElement.style.color = (d.source.includes('invalid') || d.source.includes('Not found'))
                ? 'var(--error, #e74c3c)' : 'var(--ok, #2ecc71)';
        } else {
            stEl.textContent = 'Unknown';
        }
    } catch(e) {
        stEl.textContent = 'Unknown';
    }
};


// ── Update SwarmUI Badge Helper ──────────────────────────────────────────────

function _updateSwarmUIBadge(data) {
    var badge    = document.getElementById('igen-local-status-badge');
    var badgeTxt = document.getElementById('igen-local-status-text');
    var startBtn = document.getElementById('igen-local-start-btn');
    if (!badge || !badgeTxt) return;

    var ok        = data && data.ok === true;
    var installed = data && data.installed === true;

    if (ok) {
        badge.style.background  = 'rgba(16,185,129,0.12)';
        badge.style.borderColor = 'rgba(16,185,129,0.35)';
        badge.style.color       = '#34d399';
        if (badge.querySelector('i')) badge.querySelector('i').style.color = '#34d399';
        badgeTxt.textContent    = 'Online';
        if (startBtn) startBtn.style.display = 'none';
    } else if (installed) {
        badge.style.background  = 'rgba(245,158,11,0.12)';
        badge.style.borderColor = 'rgba(245,158,11,0.35)';
        badge.style.color       = '#fbbf24';
        if (badge.querySelector('i')) badge.querySelector('i').style.color = '#fbbf24';
        badgeTxt.textContent    = data.auto_start ? 'Standby (Auto-Start)' : 'Offline (Installed)';
        if (startBtn) startBtn.style.display = 'inline-flex';
    } else {
        badge.style.background  = 'rgba(231,76,60,0.12)';
        badge.style.borderColor = 'rgba(231,76,60,0.35)';
        badge.style.color       = '#e74c3c';
        if (badge.querySelector('i')) badge.querySelector('i').style.color = '#e74c3c';
        badgeTxt.textContent    = 'Not Installed';
        if (startBtn) startBtn.style.display = 'inline-flex';
    }
}

window.checkSwarmUIBadgeSilent = async function() {
    try {
        var res  = await fetch('/hecos/api/plugins/image_gen/local_status');
        var data = await res.json();
        _updateSwarmUIBadge(data);
    } catch (e) {
        console.debug('[ImageGen] Silent SwarmUI check failed:', e);
    }
};


// ── Test SwarmUI backend ─────────────────────────────────────────────────────

window.testSwarmUIBackend = async function() {
    var btn      = document.getElementById('igen-local-test-btn');
    var box      = document.getElementById('igen-local-test-results');
    var badge    = document.getElementById('igen-local-status-badge');
    var badgeTxt = document.getElementById('igen-local-status-text');
    if (!btn || !box) return;

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
    box.style.display = 'block';
    box.innerHTML = '<div style="color:var(--muted); text-align:center; padding:8px;">\u23f3 Checking SwarmUI installation and server status...</div>';

    if (badge) {
        badge.style.background   = 'rgba(255,200,0,0.1)';
        badge.style.borderColor  = 'rgba(255,200,0,0.3)';
        badge.style.color        = '#fbbf24';
        if (badge.querySelector('i')) badge.querySelector('i').style.color = '#fbbf24';
    }
    if (badgeTxt) badgeTxt.textContent = 'Testing...';

    try {
        var res = await fetch('/hecos/api/plugins/image_gen/local_status');
        var data = await res.json();

        var ok        = data.ok === true;
        var installed = data.installed === true;
        var icon      = ok ? '\u2705' : (installed ? '\u26A0\uFE0F' : '\u274c');
        var color     = ok ? '#2ecc71' : (installed ? '#f59e0b' : '#e74c3c');

        var statusLine = data.status_text || (ok ? 'SwarmUI reachable' : 'SwarmUI unreachable');
        var html  = '<div style="color:' + color + '; font-weight:700; margin-bottom:6px;">' + icon + ' ' + statusLine + '</div>';

        if (installed) {
            html += '<div style="color:var(--muted);">\uD83D\uDCC2 Install path: <code>' + (data.install_path || 'Detected') + '</code></div>';
        } else {
            html += '<div style="color:#e74c3c;">\uD83D\uDCC2 Installation: <b>Not found</b> (install SwarmUI or set custom path above)</div>';
        }
        html += '<div style="color:var(--muted);">\u26A1 Auto-Start: <b>' + (data.auto_start ? 'Enabled (launches automatically on image request)' : 'Disabled') + '</b></div>';
        if (data.version)  html += '<div style="color:var(--muted);">\uD83D\uDD16 Version: ' + data.version + '</div>';
        if (data.url)      html += '<div style="color:var(--muted);">\uD83D\uDD17 URL: <code>' + data.url + '</code></div>';
        if (ok && data.models_count !== undefined) html += '<div style="color:var(--muted);">\uD83E\uDDE0 Models loaded: ' + data.models_count + '</div>';
        if (data.error && !ok) html += '<div style="color:' + (installed ? '#f59e0b' : '#e74c3c') + '; margin-top:6px; font-size:11px;">' + data.error + '</div>';
        if (data.message && !data.error) html += '<div style="color:var(--muted); margin-top:6px; font-size:11px;">' + data.message + '</div>';

        box.innerHTML = html;
        _updateSwarmUIBadge(data);

    } catch (e) {
        box.innerHTML = '<div style="color:#e74c3c;">\u274c Network error: ' + e.message + '</div>';
        if (badge) {
            badge.style.background  = 'rgba(231,76,60,0.1)';
            badge.style.borderColor = 'rgba(231,76,60,0.3)';
            badge.style.color       = '#e74c3c';
        }
        if (badgeTxt) badgeTxt.textContent = 'Error';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-stethoscope"></i> Test SwarmUI Connection';
    }
};


// ── Start SwarmUI backend on demand ──────────────────────────────────────────

window.startSwarmUIBackend = async function() {
    var startBtn = document.getElementById('igen-local-start-btn');
    var testBtn  = document.getElementById('igen-local-test-btn');
    var box      = document.getElementById('igen-local-test-results');
    var badge    = document.getElementById('igen-local-status-badge');
    var badgeTxt = document.getElementById('igen-local-status-text');
    var pathEl   = document.getElementById('igen-local-install-path');
    if (!startBtn || !box) return;

    startBtn.disabled = true;
    if (testBtn) testBtn.disabled = true;
    startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting SwarmUI...';
    box.style.display = 'block';
    box.innerHTML = '<div style="color:#60a5fa; text-align:center; padding:8px;">\uD83D\uDE80 Launching local SwarmUI instance in background...<br><small style="color:var(--muted);">Waiting for HTTP server on port 7801 (this may take 15\u201390 seconds)</small></div>';

    if (badge) {
        badge.style.background   = 'rgba(59,130,246,0.12)';
        badge.style.borderColor  = 'rgba(59,130,246,0.35)';
        badge.style.color        = '#60a5fa';
        if (badge.querySelector('i')) badge.querySelector('i').style.color = '#60a5fa';
    }
    if (badgeTxt) badgeTxt.textContent = 'Starting...';

    try {
        var installPath = pathEl ? pathEl.value.trim() : '';
        var res = await fetch('/hecos/api/plugins/image_gen/local_start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ install_path: installPath })
        });
        var data = await res.json();

        if (data.ok) {
            box.innerHTML = '<div style="color:#2ecc71; font-weight:700; margin-bottom:4px;">\u2705 ' + (data.message || 'SwarmUI started and ready!') + '</div>' +
                            (data.install_path ? '<div style="color:var(--muted); font-size:11px;">\uD83D\uDCC2 Path: <code>' + data.install_path + '</code></div>' : '');
            _updateSwarmUIBadge(data);
            if (typeof window.refreshImageModels === 'function') {
                setTimeout(function() { window.refreshImageModels(); }, 400);
            }
        } else {
            var errMsg = data.error || data.message || 'Failed to start SwarmUI.';
            box.innerHTML = '<div style="color:#e74c3c; font-weight:700; margin-bottom:6px;">\u274c SwarmUI Startup Failed</div>' +
                            '<div style="color:var(--text); font-size:11.5px; white-space:pre-wrap;">' + errMsg + '</div>';
            _updateSwarmUIBadge(data);
        }
    } catch (e) {
        box.innerHTML = '<div style="color:#e74c3c;">\u274c Network error while starting SwarmUI: ' + e.message + '</div>';
    } finally {
        startBtn.disabled = false;
        if (testBtn) testBtn.disabled = false;
        startBtn.innerHTML = '<i class="fas fa-play"></i> Start SwarmUI';
    }
};

// ── Cloud enabled toggle ─────────────────────────────────────────────────────

window.onCloudEnabledChanged = function() {
    var chk     = document.getElementById('igen-cloud-enabled');
    var wrapper = document.getElementById('igen-cloud-wrapper');
    if (!chk || !wrapper) return;
    if (chk.checked) {
        wrapper.classList.remove('cloud-disabled');
    } else {
        wrapper.classList.add('cloud-disabled');
    }
    _igenDebounceSave();
};

// ── Cloud Providers Toggle ───────────────────────────────────────────────────

window._onCloudToggle = function(enabled) {
    var provSel = document.getElementById('igen-provider');
    var mirror  = document.getElementById('igen-cloud-enabled-mirror');
    if (mirror && mirror.checked !== !!enabled) mirror.checked = !!enabled;
    var wrapper = document.getElementById('igen-cloud-wrapper');
    if (wrapper) {
        if (enabled) wrapper.classList.remove('cloud-disabled');
        else wrapper.classList.add('cloud-disabled');
    }
    if (!provSel) return;

    // Disable/enable all cloud options in the dropdown
    var _cloudIds = ['pollinations','gemini','gemini_native','openai','stability','airforce','huggingface','horde'];
    Array.from(provSel.options).forEach(function(opt) {
        if (_cloudIds.indexOf(opt.value) !== -1) {
            opt.disabled = !enabled;
            if (!enabled && opt.selected) {
                // Force switch to swarmui
                provSel.value = 'swarmui';
            }
        }
    });

    // Also disable optgroups visually
    Array.from(provSel.querySelectorAll('optgroup')).forEach(function(g) {
        if (g.label && g.label.indexOf('Cloud') !== -1) {
            g.disabled = !enabled;
        }
    });

    // Only trigger provider change if NOT during a bulk reload (prevents race condition)
    if (!_igenLoadingConfig && !window._igenDisableAutoSave) {
        window.onProviderChanged(true, 0);
    }
};

// Apply cloud toggle state after config loads
window._applyCloudToggleState = function() {
    var chk = document.getElementById('igen-cloud-enabled');
    if (chk) window._onCloudToggle(chk.checked);
};

// ── Other helpers ────────────────────────────────────────────────────────────

// ── Resolution presets & dimension helpers ───────────────────────────────────

window.IGEN_RESOLUTION_PRESETS = {
    '1:1':       [1024, 1024],
    '3:4':       [ 896, 1152],
    '2:3':       [ 832, 1216],
    '9:16':      [ 768, 1344],
    '4:3':       [1152,  896],
    '3:2':       [1216,  832],
    '16:9':      [1344,  768],
    '21:9':      [1536,  640],
    '5:4':       [1152,  896],
    '4:5':       [ 896, 1120],
    '1:1_hd':    [1280, 1280],
    '2:3_hd':    [1024, 1536],
    '3:4_hd':    [1152, 1536],
    '9:16_hd':   [ 896, 1536],
    '3:2_hd':    [1536, 1024],
    '4:3_hd':    [1536, 1152],
    '16:9_hd':   [1536,  896],
    '1:1_fast':  [ 768,  768],
    '3:4_fast':  [ 640,  896],
    '16:9_fast': [ 960,  576],
};

function _updateIgenMpBadge(w, h) {
    var badge = document.getElementById('igen-dims-mp-badge');
    if (!badge) return;
    var wi = parseInt(w, 10), hi = parseInt(h, 10);
    if (wi > 0 && hi > 0) {
        badge.textContent = ((wi * hi) / 1000000).toFixed(2) + ' MP';
    } else {
        badge.textContent = '';
    }
}

function _matchResolutionPresetKey(w, h) {
    var wi = parseInt(w, 10), hi = parseInt(h, 10);
    var keys = Object.keys(window.IGEN_RESOLUTION_PRESETS);
    for (var i = 0; i < keys.length; i++) {
        var pair = window.IGEN_RESOLUTION_PRESETS[keys[i]];
        if (pair[0] === wi && pair[1] === hi) return keys[i];
    }
    return 'custom';
}

window.refreshImageModels = function() { window.onProviderChanged(false, 0); };

window.onAspectRatioChanged = function(userTriggered) {
    var sel = document.getElementById('igen-aspect-ratio');
    var wEl = document.getElementById('igen-width');
    var hEl = document.getElementById('igen-height');
    if (!sel) return;
    var pair = window.IGEN_RESOLUTION_PRESETS[sel.value];
    if (pair && wEl && hEl) {
        wEl.value = pair[0];
        hEl.value = pair[1];
    }
    if (wEl && hEl) _updateIgenMpBadge(wEl.value, hEl.value);
    if (userTriggered && typeof window._igenDebounceSave === 'function') {
        window._igenDebounceSave();
    }
};

window.onCustomDimEdited = function() {
    var sel = document.getElementById('igen-aspect-ratio');
    var wEl = document.getElementById('igen-width');
    var hEl = document.getElementById('igen-height');
    if (!wEl || !hEl) return;
    _updateIgenMpBadge(wEl.value, hEl.value);
    if (sel) {
        var matched = _matchResolutionPresetKey(wEl.value, hEl.value);
        if (Array.from(sel.options).some(function(o) { return o.value === matched; })) {
            sel.value = matched;
        } else {
            sel.value = 'custom';
        }
    }
};

window.swapIgenDimensions = function() {
    var wEl = document.getElementById('igen-width');
    var hEl = document.getElementById('igen-height');
    if (!wEl || !hEl) return;
    var tmp = wEl.value;
    wEl.value = hEl.value;
    hEl.value = tmp;
    window.onCustomDimEdited();
    if (typeof window.updateIgenLiveSummary === 'function') window.updateIgenLiveSummary();
    if (typeof window.updateIgenDirtyState === 'function') window.updateIgenDirtyState();
    if (typeof window._igenDebounceSave === 'function') window._igenDebounceSave();
};

window.reloadIgenPanel = async function() {
    var btn = document.getElementById('igen-refresh-btn');
    if (btn) { btn.innerHTML = '<i class="fas fa-spinner fa-spin" style="font-size:13px;"></i> Loading...'; btn.disabled = true; }
    try {
        _igenLoadingConfig = true;
        window._igenDisableAutoSave = true;

        // 1. Fetch config from server
        var res  = await fetch('/hecos/api/plugins/image_gen/config');
        var data = await res.json();
        var cfg  = data.image_gen || {};

        // 2. Load presets dropdown FIRST so #igen-preset holds active_preset before any change can fire
        await window.loadIgenPresets(cfg.active_preset || '');

        // 3. Apply scalar fields + cloud toggle + pending VAE/LoRAs before building dropdowns
        window.applyIgenConfig(cfg, { fromPreset: false });

        // 4. Clear and rebuild provider dropdown + fetch models/VAEs/LoRAs
        var provSel  = document.getElementById('igen-provider');
        var modelSel = document.getElementById('igen-model');
        var effectiveProv = (!cfg.cloud_enabled && cfg.provider && cfg.provider !== 'swarmui')
            ? 'swarmui'
            : (cfg.provider || 'swarmui');
        if (provSel) provSel.setAttribute('data-initial-val', effectiveProv);
        if (modelSel && cfg.model)   modelSel.setAttribute('data-initial-val', cfg.model);
        if (provSel) provSel.innerHTML = '';
        await window.onProviderChanged(false, 0);

        // Re-apply cloud toggle disabled state onto rebuilt provider options
        window._applyCloudToggleState();

        // 5. Capture baseline for dirty indicator & refresh summary
        if (typeof window.captureIgenPresetBaseline === 'function') {
            await window.captureIgenPresetBaseline(cfg.active_preset || '');
        }
        if (typeof window.updateIgenLiveSummary === 'function') window.updateIgenLiveSummary();
        if (typeof window.updateIgenDirtyState === 'function') window.updateIgenDirtyState();

    } catch(e) {
        console.error('[ImageGen] reloadIgenPanel error:', e);
    } finally {
        _igenLoadingConfig = false;
        window._igenDisableAutoSave = false;
        if (btn) { btn.innerHTML = '<i class="fas fa-sync-alt" style="font-size:13px;"></i> Refresh'; btn.disabled = false; }
    }
};
