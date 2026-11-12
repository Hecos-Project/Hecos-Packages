
// Strip ANSI terminal escape codes from a string
function _stripAnsi(str) {
    // Covers ESC[ ... m sequences (colors, bold, etc.)
    return str.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').replace(/\x1b\][^\x07]*\x07/g, '');
}

window.builderLog = function(rawMsg, type='info') {
    // Strip ANSI codes first
    let msg = _stripAnsi(String(rawMsg));
    
    // Auto-detect type from content if not explicitly set or is generic 'info'
    if (type === 'info') {
        const m = msg.trim();
        if (/^\[OK\]/i.test(m) || /^\[SUCCESS\]/i.test(m))       type = 'success';
        else if (/^\[WARN\]/i.test(m) || /^\[WARNING\]/i.test(m)) type = 'warn';
        else if (/^\[ERROR\]/i.test(m) || /^\[FAIL\]/i.test(m))  type = 'error';
    }
    
    const term = document.getElementById('builder-terminal');
    console.log(`[Builder] ${msg}`);
    if (!term) return;
    
    const now = new Date();
    const time = now.getHours().toString().padStart(2,'0') + ':' + 
                 now.getMinutes().toString().padStart(2,'0') + ':' + 
                 now.getSeconds().toString().padStart(2,'0');
    
    let color = '#a3a3a3';
    let icon = '';
    if (type === 'error')   { color = '#ef4444'; icon = 'fa-times-circle'; }
    if (type === 'success') { color = '#10b981'; icon = 'fa-check'; }
    if (type === 'warn')    { color = '#f59e0b'; icon = 'fa-exclamation-triangle'; }
    
    const div = document.createElement('div');
    div.style.color = color;
    div.innerHTML = `<span style="color:#4b5563;">[${time}]</span> ${icon ? `<i class="fas ${icon}"></i> ` : ''}${msg}`;
    term.appendChild(div);
    term.scrollTop = term.scrollHeight;
};

// Package Builder Logic

let currentManifest = {};

// Use native Hecos Modal instead of browser alert
function _builderModal(msg, isError = true) {
    const modal = document.getElementById('builder-info-modal');
    if (msg === false) {
        if (modal) modal.style.display = 'none';
        return;
    }
    const titleEl = document.getElementById('builder-info-modal-title');
    const textEl = document.getElementById('builder-info-modal-text');
    
    if (titleEl && textEl && modal) {
        if (isError) {
            titleEl.innerHTML = '<i class="fas fa-exclamation-triangle" style="color:#ff4a4a; margin-right:8px;"></i>Builder Error';
        } else {
            titleEl.innerHTML = '<i class="fas fa-info-circle" style="color:#3b82f6; margin-right:8px;"></i>Builder Info';
        }
        textEl.innerHTML = msg;
        modal.style.display = 'flex';
    } else {
        console.error("Modal not found. Fallback:", msg);
        alert(msg);
    }
}

function _builderConfirmModal(msg, onConfirm) {
    const modal = document.getElementById('builder-confirm-modal');
    const textEl = document.getElementById('builder-confirm-modal-text');
    const yesBtn = document.getElementById('builder-confirm-modal-yes');
    
    if (modal && textEl && yesBtn) {
        textEl.innerHTML = msg;
        yesBtn.onclick = () => {
            modal.style.display = 'none';
            if (onConfirm) onConfirm();
        };
        modal.style.display = 'flex';
    } else {
        if (confirm(msg)) {
            if (onConfirm) onConfirm();
        }
    }
}

window.builderSourcesData = [];
window.builderActiveCategoryFilters = new Set();


const _BUILDER_DEFAULT_REPOS = [
    { id: 'repo-1', name: 'Hecos Packages', desc: 'Free / Core Packages', src: 'C:\\Hecos-Packages\\sources', dest: 'C:\\Hecos-Packages\\packages' },
    { id: 'repo-2', name: 'Hecos Elite', desc: 'Premium Packages', src: 'C:\\Hecos-Elite\\sources', dest: 'C:\\Hecos-Elite\\packages' }
];

window.builderInitRepos = function() {
    try {
        const stored = localStorage.getItem('hpm-builder-repos');
        if (stored) {
            const parsed = JSON.parse(stored);
            if (Array.isArray(parsed) && parsed.length > 0) {
                let mutated = false;
                parsed.forEach((r, i) => {
                    if (r && !r.id) {
                        r.id = 'repo-' + (i + 1);
                        mutated = true;
                    }
                });
                window.builderRepos = parsed;
                if (mutated) localStorage.setItem('hpm-builder-repos', JSON.stringify(window.builderRepos));
                return window.builderRepos;
            }
        }
    } catch (e) {
        // Fall back to defaults if stored repositories JSON is invalid.
    }
    window.builderRepos = _BUILDER_DEFAULT_REPOS.map(r => Object.assign({}, r));
    localStorage.setItem('hpm-builder-repos', JSON.stringify(window.builderRepos));
    return window.builderRepos;
};

window.builderGetActiveRepo = function() {
    if (!Array.isArray(window.builderRepos) || !window.builderRepos.length) {
        window.builderInitRepos();
    }
    const repos = window.builderRepos || [];
    if (!repos.length) return { idx: 0, repo: null };

    const sel = document.getElementById('builder-repo-selector');
    let idx = -1;

    // Ignore placeholder <option value="0"> in static HTML until dropdown is synced with all repos.
    if (sel && sel.dataset && sel.dataset.reposSynced === '1' && sel.options.length === repos.length) {
        const parsedSel = parseInt(sel.value, 10);
        if (!isNaN(parsedSel) && parsedSel >= 0 && parsedSel < repos.length) {
            idx = parsedSel;
        }
    }

    if (idx === -1) {
        const savedId = localStorage.getItem('hpm-builder-active-repo-id');
        if (savedId) {
            idx = repos.findIndex(r => r && r.id === savedId);
        }
    }

    if (idx === -1) {
        const savedIdx = parseInt(localStorage.getItem('hpm-builder-active-repo-idx'), 10);
        if (!isNaN(savedIdx)) {
            idx = Math.max(0, Math.min(savedIdx, repos.length - 1));
        }
    }

    if (idx < 0 || idx >= repos.length) idx = 0;
    return { idx, repo: repos[idx] };
};

window.builderApplyActiveRepo = function(idxOverride) {
    if (!Array.isArray(window.builderRepos) || !window.builderRepos.length) {
        window.builderInitRepos();
    }
    const repos = window.builderRepos || [];
    if (!repos.length) return { idx: 0, repo: null };

    let idx;
    let repo;
    if (typeof idxOverride === 'number' && !isNaN(idxOverride) && idxOverride >= 0 && idxOverride < repos.length) {
        idx = idxOverride;
        repo = repos[idx];
    } else {
        const active = window.builderGetActiveRepo();
        idx = active.idx;
        repo = active.repo;
    }
    if (!repo) return { idx: 0, repo: null };

    if (repo.id) localStorage.setItem('hpm-builder-active-repo-id', repo.id);
    localStorage.setItem('hpm-builder-active-repo-idx', String(idx));
    localStorage.setItem('hpm-builder-src', repo.src || '');
    localStorage.setItem('hpm-builder-dest', repo.dest || '');

    const srcEl = document.getElementById('builder-sources-root');
    const destEl = document.getElementById('builder-dest-root');
    const titleEl = document.getElementById('builder-active-repo-name');
    const sel = document.getElementById('builder-repo-selector');

    if (srcEl) srcEl.value = repo.src || '';
    if (destEl) destEl.value = repo.dest || '';
    if (titleEl) titleEl.innerText = (repo.name && repo.name.trim()) ? repo.name : ('Repo ' + (idx + 1));
    if (sel && sel.dataset && sel.dataset.reposSynced === '1' && idx < sel.options.length) {
        sel.value = String(idx);
    }

    return { idx, repo };
};

window.builderEnsureActiveRepo = function() {
    window.builderInitRepos();
    const sel = document.getElementById('builder-repo-selector');
    if (sel && (sel.dataset.reposSynced !== '1' || sel.options.length !== window.builderRepos.length)) {
        if (typeof window.builderSyncHeaderDropdown === 'function') {
            window.builderSyncHeaderDropdown(true);
        }
    }
    return window.builderApplyActiveRepo();
};

window.builderLoadSetup = function() {
    const active = (typeof window.builderGetActiveRepo === 'function') ? window.builderGetActiveRepo() : null;
    const srcEl = document.getElementById('builder-sources-root');
    const destEl = document.getElementById('builder-dest-root');
    const cliEl = document.getElementById('builder-cli-root');

    const src = (active && active.repo)
        ? (active.repo.src || '')
        : ((srcEl && srcEl.value) || localStorage.getItem('hpm-builder-src') || 'C:\\Hecos-Packages\\sources');
    const dest = (active && active.repo)
        ? (active.repo.dest || '')
        : ((destEl && destEl.value) || localStorage.getItem('hpm-builder-dest') || 'C:\\Hecos-Packages\\packages');
    const cli = localStorage.getItem('hpm-builder-cli') || 'C:\\Hecos-Packages\\Hecos_HPM_Builder';
    const priv = localStorage.getItem('hpm-builder-priv') || 'C:\\Hecos\\data\\trusted_keys\\hpm_private.pem';
    const pub = localStorage.getItem('hpm-builder-pub') || 'C:\\Hecos\\data\\trusted_keys';
    const unpackDest = localStorage.getItem('hpm-builder-unpack') || src;
    const hecos = localStorage.getItem('hpm-builder-hecos') || 'C:\\Hecos\\hecos';

    if (srcEl && active && active.repo) srcEl.value = src;
    else if (srcEl && !srcEl.value) srcEl.value = src;
    if (destEl && active && active.repo) destEl.value = dest;
    else if (destEl && !destEl.value) destEl.value = dest;
    if (cliEl) cliEl.value = cli;

    return {src, dest, cli, priv, pub, unpackDest, hecos};
};

window.builderSaveSetup = function() {
    const srcInput = document.getElementById('setup-sources-root') || document.getElementById('setup-src-root');
    const src = srcInput ? srcInput.value : '';
    const dest = document.getElementById('setup-dest-root') ? document.getElementById('setup-dest-root').value : '';
    const cli = document.getElementById('setup-cli-root') ? document.getElementById('setup-cli-root').value : '';
    const priv = document.getElementById('setup-private-key') ? document.getElementById('setup-private-key').value : '';
    const pub = document.getElementById('setup-public-keys') ? document.getElementById('setup-public-keys').value : '';
    
    if (src) localStorage.setItem('hpm-builder-src', src);
    if (dest) localStorage.setItem('hpm-builder-dest', dest);
    if (cli) localStorage.setItem('hpm-builder-cli', cli);
    if (priv) localStorage.setItem('hpm-builder-priv', priv);
    if (pub) localStorage.setItem('hpm-builder-pub', pub);
    const unpackDest = document.getElementById('setup-unpack-dest') ? document.getElementById('setup-unpack-dest').value : '';
    const hecos = document.getElementById('setup-hecos-root') ? document.getElementById('setup-hecos-root').value : '';
    if (unpackDest) localStorage.setItem('hpm-builder-unpack', unpackDest);
    if (hecos) localStorage.setItem('hpm-builder-hecos', hecos);
    
    window.builderLoadSetup();
    
    document.getElementById('hpm-builder-setup-modal').style.display='none';
    window.builderLog('Builder settings saved successfully.', 'success');
    window.builderRefreshSources();
};

window.builderOpenSetup = function() {
    const setup = window.builderLoadSetup();
    const srcInput = document.getElementById('setup-sources-root') || document.getElementById('setup-src-root');
    if(srcInput) srcInput.value = setup.src;
    if(document.getElementById('setup-dest-root')) document.getElementById('setup-dest-root').value = setup.dest;
    if(document.getElementById('setup-cli-root')) document.getElementById('setup-cli-root').value = setup.cli;
    if(document.getElementById('setup-private-key')) document.getElementById('setup-private-key').value = setup.priv;
    if(document.getElementById('setup-public-keys')) document.getElementById('setup-public-keys').value = setup.pub;
    if(document.getElementById('setup-unpack-dest')) document.getElementById('setup-unpack-dest').value = setup.unpackDest;
    if(document.getElementById('setup-hecos-root')) document.getElementById('setup-hecos-root').value = setup.hecos;
    
    document.getElementById('hpm-builder-setup-modal').style.display='flex';
};

// Auto load on init while preserving currently selected repository
setTimeout(() => {
    if (typeof window.builderEnsureActiveRepo === 'function') window.builderEnsureActiveRepo();
    if (typeof window.builderLoadSetup === 'function') window.builderLoadSetup();
}, 500);
window.builderInitialLists = {
    author: ['Hecos Developer', 'Antonio Meloni'],
    type: ['plugin', 'persona', 'theme', 'app', 'widget', 'system_app', 'core_module', 'extension', 'skill_pack', 'library'],
    license: ['MIT', 'GPL-3.0', 'Apache-2.0', 'Proprietary', 'admin']
};

window.builderPrimaryDefaults = {
    author: 'Antonio Meloni',
    license: 'GPL-3.0'
};

window.builderDefaultLists = JSON.parse(JSON.stringify(window.builderInitialLists));

window.builderLoadDefaults = function() {
    let saved = localStorage.getItem('hecos_builder_defaults');
    if (saved) {
        try {
            let parsed = JSON.parse(saved);
            Object.keys(parsed).forEach(k => { window.builderDefaultLists[k] = parsed[k]; });
        } catch(e) {}
    }
    let savedPrim = localStorage.getItem('hecos_builder_primary');
    if (savedPrim) {
        try {
            let parsed = JSON.parse(savedPrim);
            Object.keys(parsed).forEach(k => { 
                if(k !== 'type') window.builderPrimaryDefaults[k] = parsed[k]; 
            });
        } catch(e) {}
    }
    
    // Populate the dropdowns
    ['author', 'type', 'license'].forEach(field => {
        const select = document.getElementById('builder-' + field + '-select');
        if (!select) return;
        select.innerHTML = '<option value="" selected></option>';
        const list = window.builderDefaultLists[field] || [];
        list.forEach(val => {
            let opt = document.createElement('option');
            opt.value = val;
            let isPrimary = window.builderPrimaryDefaults[field] === val;
            opt.innerText = isPrimary ? val + ' ★' : val;
            select.appendChild(opt);
        });
    });
};

window.builderSaveDefaults = function() {
    localStorage.setItem('hecos_builder_defaults', JSON.stringify(window.builderDefaultLists));
    localStorage.setItem('hecos_builder_primary', JSON.stringify(window.builderPrimaryDefaults));
    window.builderLoadDefaults();
};

window.builderAddDefault = function(field) {
    const input = document.getElementById('builder-' + field);
    if (!input || !input.value.trim()) return;
    const val = input.value.trim();
    if (!window.builderDefaultLists[field]) window.builderDefaultLists[field] = [];
    if (!window.builderDefaultLists[field].includes(val)) {
        window.builderDefaultLists[field].push(val);
        window.builderSaveDefaults();
        window.builderLog('Added \'' + val + '\' to ' + field + ' presets.', 'success');
    }
};

window.builderRemoveDefault = function(field) {
    const input = document.getElementById('builder-' + field);
    if (!input || !input.value.trim()) return;
    const val = input.value.trim();
    if (window.builderDefaultLists[field] && window.builderDefaultLists[field].includes(val)) {
        window.builderDefaultLists[field] = window.builderDefaultLists[field].filter(item => item !== val);
        window.builderSaveDefaults();
        window.builderLog('Removed \'' + val + '\' from ' + field + ' presets.', 'warn');
        input.value = '';
    }
};

window.builderSetPrimaryDefault = function(field) {
    const input = document.getElementById('builder-' + field);
    if (!input || !input.value.trim()) return;
    const val = input.value.trim();
    
    // Auto-add to list if not present
    if (!window.builderDefaultLists[field]) window.builderDefaultLists[field] = [];
    if (!window.builderDefaultLists[field].includes(val)) {
        window.builderDefaultLists[field].push(val);
    }
    
    window.builderPrimaryDefaults[field] = val;
    window.builderSaveDefaults();
    window.builderLog('Set \'' + val + '\' as the primary default for ' + field + '.', 'success');
};

setTimeout(window.builderLoadDefaults, 600);

