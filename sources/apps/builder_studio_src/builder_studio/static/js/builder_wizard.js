
// ──────────────────────────────────────────────────────────────────
// NEW PACKAGE WIZARD
// ──────────────────────────────────────────────────────────────────
window.builderNewPackage = function() {
    const types = window.HPM_TYPE_META ? Object.entries(window.HPM_TYPE_META).sort((a,b) => (a[1].order||99)-(b[1].order||99)) : [['module', {label:'Module', icon:'fa-cube', color:'#6b7280'}]];
    const typeOptions = types.map(([k, m]) =>
        `<option value="${k}"><i class="fas ${m.icon}"></i> ${m.label}</option>`
    ).join('');

    const html = `
    <div style="padding:20px; min-width:380px;">
        <h4 style="margin-bottom:20px; font-weight:800; text-transform:uppercase; letter-spacing:1px;">
            <i class="fas fa-plus-circle" style="color:var(--accent); margin-right:8px;"></i>New Package
        </h4>
        <div style="display:grid; gap:14px;">
            <div>
                <label style="font-size:0.8em; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:0.5px;">Package Name</label>
                <input id="newpkg-name" class="form-control" type="text" placeholder="e.g. my_awesome_plugin" 
                       style="width:100%; margin-top:4px; font-family:monospace;"
                       oninput="document.getElementById('newpkg-id').value = this.value.toLowerCase().replace(/[^a-z0-9_]/g,'_')">
            </div>
            <div>
                <label style="font-size:0.8em; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:0.5px;">Package ID</label>
                <input id="newpkg-id" class="form-control" type="text" placeholder="auto-generated from name" 
                       style="width:100%; margin-top:4px; font-family:monospace; opacity:0.7;">
            </div>
            <div>
                <label style="font-size:0.8em; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:0.5px;">Version</label>
                <input id="newpkg-version" class="form-control" type="text" value="1.0.0" 
                       style="width:100%; margin-top:4px; font-family:monospace;">
            </div>
            <div>
                <label style="font-size:0.8em; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:0.5px;">Author</label>
                <input id="newpkg-author" class="form-control" type="text" placeholder="Your Name"
                       style="width:100%; margin-top:4px;">
            </div>
            <div>
                <label style="font-size:0.8em; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:0.5px;">Type</label>
                <select id="newpkg-type" class="form-control" style="width:100%; margin-top:4px;">
                    ${typeOptions}
                </select>
            </div>
            <div>
                <label style="font-size:0.8em; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:0.5px;">Description</label>
                <textarea id="newpkg-desc" class="form-control" rows="2" placeholder="Short description..."
                          style="width:100%; margin-top:4px; resize:vertical;"></textarea>
            </div>
            <div style="display:flex; gap:10px; margin-top:10px;">
                <button class="btn btn-primary" style="flex:1; padding:10px; font-weight:bold;" onclick="window.builderCreateNewPackage()">
                    <i class="fas fa-plus"></i> Create Package
                </button>
                <button class="btn btn-secondary" style="padding:10px 16px;" onclick="_builderModal(false)">
                    Cancel
                </button>
            </div>
        </div>
    </div>`;

    _builderModal(html, false);
    const titleEl = document.getElementById('builder-info-modal-title');
    if (titleEl) titleEl.innerHTML = '<i class="fas fa-plus-circle" style="color:var(--accent); margin-right:8px;"></i>New Package';
    setTimeout(() => document.getElementById('newpkg-name') && document.getElementById('newpkg-name').focus(), 100);
};

window.builderCreateNewPackage = async function() {
    const name = (document.getElementById('newpkg-name')?.value || '').trim();
    const id   = (document.getElementById('newpkg-id')?.value || '').trim() || name.toLowerCase().replace(/[^a-z0-9_]/g, '_');
    const version = (document.getElementById('newpkg-version')?.value || '1.0.0').trim();
    const author  = (document.getElementById('newpkg-author')?.value || '').trim();
    const type    = document.getElementById('newpkg-type')?.value || 'module';
    const desc    = (document.getElementById('newpkg-desc')?.value || '').trim();

    if (!name) {
        window.builderLog('New Package: Name is required.', 'error');
        return;
    }

    const baseDir = document.getElementById('builder-sources-root')?.value || '';
    if (!baseDir) {
        window.builderLog('New Package: Sources root not configured. Open Setup first.', 'error');
        _builderModal('Please configure the Sources Root directory in Setup first.', true);
        return;
    }

    _builderModal(`<div style="padding:20px; text-align:center;">
        <i class="fas fa-circle-notch fa-spin fa-2x"></i><br><br>Creating package scaffold...
    </div>`, false);

    try {
        const resp = await fetch('/api/hpm/builder/new-package', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, id, version, author, type, description: desc, base_dir: baseDir })
        });
        const data = await resp.json();
        _builderModal(false);
        if (data.ok) {
            window.builderLog(`Package "${name}" created at: ${data.path}`, 'success');
            window.builderRefreshSources();
            // Auto-select the new package
            if (data.path) {
                document.getElementById('builder-source-dir').value = data.path;
                window.builderLoadManifest();
            }
        } else {
            window.builderLog('Failed to create package: ' + data.error, 'error');
            _builderModal('Failed to create package: ' + data.error, true);
        }
    } catch(e) {
        _builderModal(false);
        window.builderLog('Error creating package: ' + e.message, 'error');
        _builderModal('Error: ' + e.message, true);
    }
};

