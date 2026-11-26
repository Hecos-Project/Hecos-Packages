/**
 * igen_core.js - Image Gen Panel: Core Bootstrap & Utilities
 * Auto-save debouncer, reliable body-mounted modal helpers, global save hook, panel bootstrap.
 */

// -- Auto-save debouncer --
let _igenSaveTimer = null;
let _igenLoadingConfig = false;  // Guard: skip auto-save during initial config / preset apply

function _igenDebounceSave() {
    if (_igenLoadingConfig || window._igenDisableAutoSave) return;
    clearTimeout(_igenSaveTimer);
    _igenSaveTimer = setTimeout(function() { window.saveIgenConfig(true); }, 500);
}

// -- Custom UI Wrappers (always body-mounted, immune to hidden tab containers) --

function _igenAlert(msg, type) {
    type = type || 'error';
    if (window.showToast) window.showToast(msg, type);
    else console.error('[ImageGen]', msg);
}

function _igenConfirm(msg, onYes) {
    // Do NOT delegate to window.hpmShowConfirm: #hpm-confirm-modal lives inside #tab-packages
    // (display:none when #tab-igen is active) and would silently swallow confirmations.
    var modalId = 'igen-custom-confirm-modal';
    var modal = document.getElementById(modalId);
    if (!modal) {
        modal = document.createElement('div');
        modal.id = modalId;
        modal.className = 'no-autosave';
        modal.style.cssText = 'position:fixed; inset:0; width:100%; height:100%; background:rgba(0,0,0,0.68); backdrop-filter:blur(4px); display:none; align-items:center; justify-content:center; z-index:999999;';
        modal.innerHTML =
            '<div style="background:var(--bg2); border:1px solid var(--border); padding:22px 24px; border-radius:12px; max-width:420px; width:90%; box-shadow:0 12px 36px rgba(0,0,0,0.55);">' +
                '<h3 style="margin:0 0 12px 0; color:var(--text); font-size:1.05em; display:flex; align-items:center; gap:8px;">' +
                    '<i class="fas fa-exclamation-triangle" style="color:var(--accent);"></i> Confirm Action' +
                '</h3>' +
                '<p id="' + modalId + '-text" style="margin:0 0 20px 0; color:var(--text); font-size:0.95em; line-height:1.5; white-space:pre-line;"></p>' +
                '<div style="display:flex; justify-content:flex-end; gap:10px;">' +
                    '<button type="button" class="btn btn-secondary btn-sm" id="' + modalId + '-cancel" style="padding:8px 16px;">Cancel</button>' +
                    '<button type="button" class="btn btn-primary btn-sm" id="' + modalId + '-yes" style="padding:8px 16px;">Confirm</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(modal);
    }

    document.getElementById(modalId + '-text').textContent = msg;
    var yesBtn = document.getElementById(modalId + '-yes');
    var cancelBtn = document.getElementById(modalId + '-cancel');

    var onKey = function(e) {
        if (e.key === 'Escape') { e.preventDefault(); cleanup(); }
        else if (e.key === 'Enter') { e.preventDefault(); confirmAction(); }
    };
    var cleanup = function() {
        modal.style.display = 'none';
        document.removeEventListener('keydown', onKey);
    };
    var confirmAction = function() {
        cleanup();
        if (typeof onYes === 'function') onYes();
    };

    cancelBtn.onclick = cleanup;
    yesBtn.onclick = confirmAction;
    modal.onclick = function(e) { if (e.target === modal) cleanup(); };
    document.addEventListener('keydown', onKey);

    modal.style.display = 'flex';
    setTimeout(function() { yesBtn.focus(); }, 50);
}

function _igenPrompt(msg, onSave, defaultVal) {
    var modalId = 'igen-custom-prompt-modal';
    var modal = document.getElementById(modalId);
    if (!modal) {
        modal = document.createElement('div');
        modal.id = modalId;
        modal.className = 'no-autosave';
        modal.style.cssText = 'position:fixed; inset:0; width:100%; height:100%; background:rgba(0,0,0,0.68); backdrop-filter:blur(4px); display:none; align-items:center; justify-content:center; z-index:999999;';
        modal.innerHTML =
            '<div style="background:var(--bg2); border:1px solid var(--border); padding:22px 24px; border-radius:12px; max-width:430px; width:90%; box-shadow:0 12px 36px rgba(0,0,0,0.55);">' +
                '<h3 style="margin:0 0 12px 0; color:var(--text); font-size:1.05em; display:flex; align-items:center; gap:8px;">' +
                    '<i class="fas fa-keyboard" style="color:var(--accent);"></i> Preset Name' +
                '</h3>' +
                '<p id="' + modalId + '-text" style="margin:0 0 14px 0; color:var(--text); font-size:0.95em; line-height:1.5; white-space:pre-line;"></p>' +
                '<input type="text" id="' + modalId + '-input" class="config-input no-autosave" style="width:100%; box-sizing:border-box; margin-bottom:20px; border:1px solid var(--border); background:var(--bg3); color:var(--text); padding:9px 12px; border-radius:7px; font-size:13.5px;">' +
                '<div style="display:flex; justify-content:flex-end; gap:10px;">' +
                    '<button type="button" class="btn btn-secondary btn-sm" id="' + modalId + '-cancel" style="padding:8px 16px;">Cancel</button>' +
                    '<button type="button" class="btn btn-primary btn-sm" id="' + modalId + '-save" style="padding:8px 16px;">Save</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(modal);
    }

    document.getElementById(modalId + '-text').textContent = msg;
    var input = document.getElementById(modalId + '-input');
    input.value = (defaultVal !== undefined && defaultVal !== null) ? String(defaultVal) : '';

    var cleanup = function() { modal.style.display = 'none'; };
    var submit = function() {
        var val = input.value.trim();
        if (!val) {
            input.focus();
            _igenAlert('Please enter a preset name.', 'warning');
            return;
        }
        cleanup();
        if (typeof onSave === 'function') onSave(val);
    };

    document.getElementById(modalId + '-cancel').onclick = cleanup;
    document.getElementById(modalId + '-save').onclick = submit;
    modal.onclick = function(e) { if (e.target === modal) cleanup(); };
    input.onkeydown = function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            submit();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cleanup();
        }
    };

    modal.style.display = 'flex';
    setTimeout(function() {
        input.focus();
        if (input.select) input.select();
    }, 60);
}

// -- Auto-save wiring --

function _igenAttachAutoSave() {
    var fields = [
        'igen-provider', 'igen-model', 'igen-enabled', 'igen-cloud-enabled',
        'igen-hf-provider', 'igen-routing-override', 'horde-nsfw', 'horde-worker-blacklist',
        'igen-aspect-ratio', 'igen-width', 'igen-height', 'igen-seed',
        'igen-sampler', 'igen-scheduler', 'igen-guidance', 'igen-steps',
        'igen-flux-guidance', 'igen-sigma-shift',
        'igen-use-neg-prompt', 'igen-neg-prompt',
        'igen-auto-enrich', 'igen-enrich-keywords',
        'igen-style', 'igen-nologo', 'igen-show-metadata',
        'igen-optimize-flux', 'igen-flux-refiner-instructions',
        'igen-vae', 'igen-loras',
        'igen-local-autostart', 'igen-local-install-path'
    ];
    fields.forEach(function(id) {
        var el = document.getElementById(id);
        if (!el) return;
        var evt = (el.type === 'checkbox' || el.tagName === 'SELECT') ? 'change' : 'input';
        el.addEventListener(evt, _igenDebounceSave);
    });
}

// -- Hook into Hecos global saveConfig --
function _igenHookGlobalSave() {
    if (typeof window.saveConfig !== 'function' || window._igenGlobalSaveHooked) return;
    window._igenGlobalSaveHooked = true;
    var _orig = window.saveConfig;
    window.saveConfig = async function(silent) {
        await _orig.call(this, silent);
        if (document.getElementById('igen-provider')) {
            await window.saveIgenConfig(true);
        }
    };
}

// -- Bootstrap --

var _igenInitDone = false;
var _igenInitInFlight = null;

var _IGEN_REQUIRED_FNS = [
    'loadIgenPresets', 'applyIgenConfig', 'onProviderChanged',
    'saveIgenConfig', 'collectIgenConfig', 'checkIgenPresetUI',
    'reloadIgenPanel', 'renderLoRAList', 'updateLoRACompatibility'
];

function _igenAllModulesReady() {
    return _IGEN_REQUIRED_FNS.every(function(fn) { return typeof window[fn] === 'function'; });
}

var initImageGenPanel = async function(forceReload) {
    var provEl = document.getElementById('igen-provider');
    if (!provEl) return false;

    // Wait for all sibling igen_*.js modules if still loading
    if (!_igenAllModulesReady()) {
        var waited = 0;
        while (!_igenAllModulesReady() && waited < 15000) {
            await new Promise(function(r) { setTimeout(r, 60); });
            waited += 60;
        }
        if (!_igenAllModulesReady()) {
            var missing = _IGEN_REQUIRED_FNS.filter(function(fn) { return typeof window[fn] !== 'function'; });
            console.error('[ImageGen] Required modules still missing after wait:', missing);
            return false;
        }
    }

    // Re-fetch element in case DOM changed while awaiting modules
    provEl = document.getElementById('igen-provider');
    if (!provEl) return false;

    // Attach auto-save listeners once per DOM element instance
    if (provEl.dataset.igenBound !== 'true') {
        _igenAttachAutoSave();
        _igenHookGlobalSave();
        provEl.dataset.igenBound = 'true';
    }

    // Determine if the current DOM instance needs data loading
    var needsLoad = !!forceReload || provEl.dataset.igenLoaded !== 'true' || provEl.options.length === 0;
    if (!needsLoad) {
        return true;
    }

    if (_igenInitInFlight) {
        return _igenInitInFlight;
    }

    _igenInitInFlight = (async function() {
        console.log('[ImageGen] All modules and DOM ready - initializing panel...');
        try {
            if (typeof window.reloadIgenPanel === 'function') {
                await window.reloadIgenPanel();
            }
            var currentProv = document.getElementById('igen-provider');
            if (currentProv && currentProv.options.length > 0) {
                currentProv.dataset.igenLoaded = 'true';
                _igenInitDone = true;
                console.log('[ImageGen] Panel ready.');
                return true;
            }
            return false;
        } catch (e) {
            console.error('[ImageGen] Bootstrap error:', e);
            return false;
        } finally {
            _igenInitInFlight = null;
        }
    })();

    return _igenInitInFlight;
};

function _watchIgenPanelMount() {
    // 1. Check immediately if already in DOM
    if (document.getElementById('igen-provider')) {
        initImageGenPanel(false);
    }

    // 2. Observe #panel-container (or document.body) for lazy injection of #tab-igen at any point in the session
    if (typeof MutationObserver !== 'undefined' && !window._igenMutationObserver) {
        var target = document.getElementById('panel-container') || document.body;
        if (target) {
            window._igenMutationObserver = new MutationObserver(function() {
                var provEl = document.getElementById('igen-provider');
                if (provEl && (provEl.dataset.igenLoaded !== 'true' || provEl.options.length === 0)) {
                    initImageGenPanel(false);
                }
            });
            window._igenMutationObserver.observe(target, { childList: true, subtree: true });
        }
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _watchIgenPanelMount);
} else {
    _watchIgenPanelMount();
}

// Only refresh SwarmUI badge silently on tab visibility — never clobber user edits!
document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible' && _igenInitDone) {
        var tab = document.getElementById('tab-igen');
        if (tab && tab.classList.contains('active') && typeof window.checkSwarmUIBadgeSilent === 'function') {
            window.checkSwarmUIBadgeSilent();
        }
    }
});

window.initImageGenPanel = initImageGenPanel;
window._igenDebounceSave = _igenDebounceSave;
window._igenAlert        = _igenAlert;
window._igenConfirm      = _igenConfirm;
window._igenPrompt       = _igenPrompt;
