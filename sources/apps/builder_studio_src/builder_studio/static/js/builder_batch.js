window.builderExecuteBatchActions = function() {
    if (window.builderSelectedPackages.size === 0) return;
    const paths = Array.from(window.builderSelectedPackages);
    
    let html = `<div style="padding:15px; text-align:center; max-width:400px; margin:0 auto;">
        <h4 style="margin-bottom:15px; font-weight:800; text-transform:uppercase;">Batch Actions <span style="font-size:0.7em; color:var(--muted)">(${paths.length} packages)</span></h4>
        <p style="color:var(--muted); margin-bottom:20px; font-size:0.9em;">Select an action to perform on all selected packages.</p>
        
        <div style="display:grid; grid-template-columns:1fr; gap:10px;">
            <button class="btn btn-primary" onclick="window.builderExecuteBatchBuildReal()" title="Compile all selected packages to .hpkg" style="padding:10px; font-weight:bold;">
                <i class="fas fa-hammer"></i> Build ${paths.length} Packages
            </button>
            <button class="btn btn-secondary" onclick="window.builderExecuteBatchActionLoop('dev-sync')" title="Compile and install directly to Hecos" style="padding:10px;">
                <i class="fas fa-sync"></i> Build & Install (Dev Sync)
            </button>
            <button class="btn btn-secondary" onclick="window.builderExecuteBatchActionLoop('capabilities')" title="Regenerate capabilities automatically" style="padding:10px;">
                <i class="fas fa-shield-alt"></i> Regenerate Capabilities
            </button>
            <button class="btn btn-secondary" onclick="window.builderExecuteBatchActionLoop('inspect')" title="Run security & structure inspection" style="padding:10px;">
                <i class="fas fa-search"></i> Inspect Info Sheets
            </button>
            <button class="btn btn-secondary" onclick="window.builderExecuteBatchActionLoop('view-caps')" title="View info sheets for selected packages" style="padding:10px;">
                <i class="fas fa-list-ul"></i> Selected Info Sheets
            </button>
            <button class="btn btn-secondary" onclick="window.builderExecuteBatchActionLoop('unpack')" title="Unpack selected .hpkg files to source directories" style="padding:10px; border-top:1px solid rgba(255,255,255,0.1);">
                <i class="fas fa-box-open"></i> Unpack Packages
            </button>
        </div>
    </div>`;
    
    // Show as info modal (isError=false), then override title to be more descriptive
    _builderModal(html, false);
    const titleEl = document.getElementById('builder-info-modal-title');
    if (titleEl) titleEl.innerHTML = '<i class="fas fa-tasks" style="color:var(--accent); margin-right:8px;"></i>Batch Actions';
};

window.builderExecuteBatchActionLoop = async function(action) {
    const paths = Array.from(window.builderSelectedPackages);
    let successCount = 0;
    let failCount = 0;
    let combinedReport = [];
    
    _builderModal(`<div style="padding:20px; text-align:center;">
        <i class="fas fa-circle-notch fa-spin fa-2x"></i><br><br>
        <span id="batch-progress-text">Processing 0 / ${paths.length}...</span>
    </div>`, false);
    const tEl = document.getElementById('builder-info-modal-title');
    if (tEl) tEl.innerHTML = `<i class="fas fa-tasks" style="color:var(--accent); margin-right:8px;"></i>Batch: Running...`;
    
    for (let i = 0; i < paths.length; i++) {
        const path = paths[i];
        document.getElementById('batch-progress-text').innerText = `Processing ${i+1} / ${paths.length}...`;
        
        try {
            if (action === 'dev-sync') {
                const resp = await fetch('/api/hpm/builder/dev-sync', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ src_dir: path }) });
                const data = await resp.json();
                if (data.ok) successCount++; else failCount++;
            } 
            else if (action === 'capabilities') {
                const resp = await fetch('/api/hpm/builder/capabilities', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ src_dir: path }) });
                const data = await resp.json();
                if (data.ok) successCount++; else failCount++;
            }
            else if (action === 'inspect') {
                const resp = await fetch('/api/hpm/builder/inspect', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ src_dir: path }) });
                const data = await resp.json();
                if (data.ok) successCount++; else failCount++;
            }
            else if (action === 'view-caps') {
                const resp = await fetch('/api/hpm/builder/load', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ src_dir: path }) });
                const data = await resp.json();
                if (data.ok && data.manifest) {
                    const html = window.builderGenerateInfoSheetHTML(data.manifest);
                    combinedReport.push(html);
                    successCount++;
                } else {
                    failCount++;
                }
            }
            else if (action === 'unpack') {
                const loadResp = await fetch('/api/hpm/builder/load', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ src_dir: path }) });
                const loadData = await loadResp.json();
                if (loadData.ok && loadData.manifest && loadData.manifest.id) {
                    const setup = window.builderLoadSetup();
                    const unpackDest = setup.unpackDest || setup.src || 'C:\\Hecos-Packages\\sources';
                    const resp = await fetch('/api/hpm/builder/unpack', { 
                        method: 'POST', 
                        headers: {'Content-Type': 'application/json'}, 
                        body: JSON.stringify({ 
                            builder_cli_dir: setup.cli,
                            pkg_id: loadData.manifest.id,
                            packages_dir: setup.dest,
                            unpack_dest: unpackDest,
                            src_dir_root: setup.src
                        }) 
                    });
                    const data = await resp.json();
                    if (data.ok) successCount++; else failCount++;
                } else {
                    failCount++;
                }
            }
        } catch(e) {
            failCount++;
        }
    }
    
    if (action === 'view-caps') {
        const html = `<div style="padding:15px; max-height:60vh; overflow-y:auto; text-align:left; font-size:0.9em; line-height:1.4;" class="custom-scrollbar">
            <h4 style="margin-bottom:15px; text-transform:uppercase; font-weight:800; text-align:center;">Selected Info Sheets <span style="color:var(--muted); font-size:0.7em;">(${successCount} packages)</span></h4>
            <div style="background:rgba(255,255,255,0.02); padding:15px; border-radius:8px; border:1px solid rgba(255,255,255,0.05);">
                ${combinedReport.join('')}
            </div>
            <div style="text-align:center; margin-top:20px;">
                <button class="btn btn-primary" onclick="_builderModal(false)">Close Sheets</button>
            </div>
        </div>`;
        _builderModal(html, false);
        const tEl = document.getElementById('builder-info-modal-title');
        if (tEl) tEl.innerHTML = '<i class="fas fa-list-ul" style="color:var(--accent); margin-right:8px;"></i>Selected Info Sheets';
    } else {
        _builderModal(false);
        window.builderLog(`Batch ${action} complete. Success: ${successCount}, Failed: ${failCount}`, failCount > 0 ? 'warn' : 'success');
        window.builderToggleSelectMode(); // disable selection mode
        window.builderRefreshSources(); // Refresh UI
    }
};

window.builderExecuteBatchBuildReal = async function() {
    _builderModal('<div style="padding:20px; text-align:center;"><i class="fas fa-circle-notch fa-spin fa-2x"></i><br><br>Batch building... Check console.</div>', false);
    
    const paths = Array.from(window.builderSelectedPackages);
    const packages = [];
    paths.forEach(p => {
        const parts = p.split('\\\\');
        packages.push(parts[parts.length - 1]);
    });
    
    try {
        const baseDir = document.getElementById('builder-sources-root') ? document.getElementById('builder-sources-root').value : '';
        const outDir = document.getElementById('builder-dest-root') ? document.getElementById('builder-dest-root').value : '';
        const resp = await fetch('/api/hpm/builder/batch-build', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ packages: packages, base_dir: baseDir, out_dir: outDir })
        });
        const data = await resp.json();
        
        _builderModal(false);
        if (data.ok) {
            window.builderLog(`Batch build complete. Success: ${data.success_count}, Failed: ${data.fail_count}`, 'success');
            window.builderToggleSelectMode();
        } else {
            window.builderLog(`Batch build failed: ${data.error}`, 'error');
        }
    } catch(e) {
        _builderModal(false);
        window.builderLog(`Batch build exception: ${e}`, 'error');
    }
};

window.builderExecuteBatchBuildCat = function(type) {
    if (!window.builderSourcesData) return;
    const pkgs = window.builderSourcesData.filter(s => (s.type || 'other') === type);
    window.builderSelectMode = true;
    window.builderSelectedPackages.clear();
    
    const baseDir = document.getElementById('builder-sources-root') ? document.getElementById('builder-sources-root').value : '';
    
    pkgs.forEach(src => {
        let d = baseDir;
        if (!d.endsWith("\\\\") && !d.endsWith("/")) d += "\\\\";
        window.builderSelectedPackages.add(d + src.rel_path);
    });
    window.builderRenderGrid();
    window.builderExecuteBatchActions();
};


// ──────────────────────────────────────────────────────────────────
// BUILD ALL
// ──────────────────────────────────────────────────────────────────
window.builderBuildAll = async function() {
    const sources = window.builderSourcesData;
    if (!sources || sources.length === 0) {
        window.builderLog('Build All: No packages found. Run a scan first.', 'error');
        return;
    }

    const html = `
    <div style="padding:15px; text-align:center;">
        <h4 style="margin-bottom:10px; font-weight:800; text-transform:uppercase;">Build All Packages</h4>
        <p style="color:var(--muted); margin-bottom:20px; font-size:0.9em;">
            Compile all <b style="color:var(--text);">${sources.length} packages</b> found in the sources directory?
        </p>
        <div style="display:flex; gap:10px; justify-content:center;">
            <button class="btn btn-primary" style="padding:10px 24px; font-weight:bold;" onclick="window.builderBuildAllConfirmed()">
                <i class="fas fa-layer-group"></i> Build All ${sources.length}
            </button>
            <button class="btn btn-secondary" style="padding:10px 16px;" onclick="_builderModal(false)">Cancel</button>
        </div>
    </div>`;
    _builderModal(html, false);
    const titleEl = document.getElementById('builder-info-modal-title');
    if (titleEl) titleEl.innerHTML = '<i class="fas fa-layer-group" style="color:var(--accent); margin-right:8px;"></i>Build All';
};

window.builderBuildAllConfirmed = async function() {
    const sources = window.builderSourcesData || [];
    const packages = sources.map(s => s.rel_path);

    const baseDir = document.getElementById('builder-sources-root')?.value || '';
    const outDir  = document.getElementById('builder-dest-root')?.value || '';

    _builderModal(`<div style="padding:20px; text-align:center;">
        <i class="fas fa-circle-notch fa-spin fa-2x"></i><br><br>
        <span id="buildall-progress">Building ${packages.length} packages...</span>
    </div>`, false);
    const tEl = document.getElementById('builder-info-modal-title');
    if (tEl) tEl.innerHTML = `<i class="fas fa-layer-group" style="color:var(--accent); margin-right:8px;"></i>Build All: Running...`;

    window.builderLog(`Build All: starting ${packages.length} packages...`, 'warn');

    try {
        const resp = await fetch('/api/hpm/builder/batch-build', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ packages, base_dir: baseDir, out_dir: outDir })
        });
        const data = await resp.json();
        _builderModal(false);
        if (data.ok) {
            if (data.logs) {
                const lines = data.logs.split('\n');
                lines.forEach(l => {
                    if (l.trim()) {
                        if (l.includes("[ERROR]")) window.builderLog(l, "error");
                        else if (l.includes("[WARN]")) window.builderLog(l, "warning");
                        else window.builderLog(l, "info");
                    }
                });
            }
            window.builderLog(`Build All complete. Success: ${data.success_count}, Failed: ${data.fail_count}`, data.fail_count > 0 ? 'warn' : 'success');
        } else {
            window.builderLog('Build All failed: ' + data.error, 'error');
            _builderModal('Build All failed: ' + data.error, true);
        }
    } catch(e) {
        _builderModal(false);
        window.builderLog('Build All error: ' + e.message, 'error');
        _builderModal('Error: ' + e.message, true);
    }
};

