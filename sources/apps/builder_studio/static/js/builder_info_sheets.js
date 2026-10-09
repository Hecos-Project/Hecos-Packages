// ──────────────────────────────────────────────────────────────────
// VIEW ALL CAPABILITIES
// ──────────────────────────────────────────────────────────────────
window.builderGenerateInfoSheetHTML = function(m, archiveInfoHtml = '') {
    const cap = m.capabilities || {};
    const chk = (val) => val ? `<span style="color:#10b981; font-weight:bold;">[Y]</span>` : `<span style="color:#ef4444; font-weight:bold;">[N]</span>`;
    
    return `
    <div style="background:var(--bg3); border:1px solid var(--border-color); border-radius:8px; margin-bottom:20px; overflow:hidden; text-align:left;">
        <div style="background:rgba(255,255,255,0.03); border-bottom:1px solid var(--border-color); padding:12px 16px; font-weight:bold; font-size:1.1em; color:var(--text); text-align:center; letter-spacing:1px;">
            HECOS PACKAGE SHEET: ${m.name || m.id || '-'}
        </div>
        
        <div style="padding:16px; display:flex; flex-direction:column; gap:20px; font-size:0.9em; line-height:1.4;">
            
            <!-- IDENTITY -->
            <div>
                <div style="color:var(--accent); font-weight:bold; border-bottom:1px solid rgba(255,255,255,0.1); margin-bottom:8px; padding-bottom:4px; text-transform:uppercase;">Identity</div>
                <div style="display:grid; grid-template-columns:120px 1fr; gap:4px;">
                    <div style="color:var(--muted)">Name:</div><div style="color:var(--text)">${m.name || '-'}</div>
                    <div style="color:var(--muted)">ID:</div><div style="color:var(--text)">${m.id || '-'}</div>
                    <div style="color:var(--muted)">Version:</div><div style="color:var(--text)">${m.version || '-'}</div>
                    <div style="color:var(--muted)">Author:</div><div style="color:var(--text)">${m.author || '-'}</div>
                    <div style="color:var(--muted)">Type:</div><div style="color:var(--text)">${m.type || '-'}</div>
                    <div style="color:var(--muted)">Tag:</div><div style="color:var(--text)">${m.tag || '-'}</div>
                    <div style="color:var(--muted)">License:</div><div style="color:var(--text)">${m.license || '-'}</div>
                    <div style="color:var(--muted)">Min Hecos:</div><div style="color:var(--text)">${m.hecos_min_version || '-'}</div>
                </div>
                ${m.description ? `<div style="margin-top:10px;"><div style="color:var(--muted)">Description:</div><div style="color:var(--text); padding-left:10px; border-left:2px solid var(--accent); margin-top:4px;">${m.description}</div></div>` : ''}
            </div>
            
            ${archiveInfoHtml}

            <!-- CAPABILITIES -->
            <div>
                <div style="color:var(--accent); font-weight:bold; border-bottom:1px solid rgba(255,255,255,0.1); margin-bottom:8px; padding-bottom:4px; text-transform:uppercase;">Capabilities</div>
                <div style="display:grid; grid-template-columns:120px 1fr; gap:4px;">
                    <div style="color:var(--muted)">Widget:</div><div>${chk(cap.has_widget)}</div>
                    <div style="color:var(--muted)">Config Panel:</div><div>${chk(cap.has_config_panel)}</div>
                    <div style="color:var(--muted)">API Routes:</div><div>${chk(cap.has_api_routes)}</div>
                    <div style="color:var(--muted)">System Calls:</div><div>${chk(cap.has_system_calls)}</div>
                </div>
                
                <div style="margin-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:10px;">
                    <div>
                        <div style="color:var(--muted)">LLM Tools (${(cap.llm_tools || []).length}):</div>
                        <div style="color:var(--text); padding-left:10px;">
                            ${(cap.llm_tools || []).length > 0 ? (cap.llm_tools || []).map(t => `&bull; ${t}`).join('<br>') : '<span style="color:var(--muted)">-</span>'}
                        </div>
                    </div>
                    <div>
                        <div style="color:var(--muted)">Slash Commands (${(cap.slash_commands || []).length}):</div>
                        <div style="color:var(--text); padding-left:10px;">
                            ${(cap.slash_commands || []).length > 0 ? (cap.slash_commands || []).map(c => `&bull; ${c}`).join('<br>') : '<span style="color:var(--muted)">-</span>'}
                        </div>
                    </div>
                </div>
                ${cap.syscall_notes ? `<div style="margin-top:10px;"><div style="color:var(--muted)">System Calls Notes:</div><div style="color:var(--text); padding-left:10px;">${cap.syscall_notes}</div></div>` : ''}
                ${cap.notes ? `<div style="margin-top:10px;"><div style="color:var(--muted)">Notes:</div><div style="color:var(--text); padding-left:10px;">${cap.notes}</div></div>` : ''}
            </div>
            
            <!-- TECHNICAL COMPONENTS -->
            <div>
                <div style="color:var(--accent); font-weight:bold; border-bottom:1px solid rgba(255,255,255,0.1); margin-bottom:8px; padding-bottom:4px; text-transform:uppercase;">Technical Components</div>
                
                <div style="color:var(--muted); margin-bottom:4px;">pip Dependencies (${(m.pip_requirements || []).length}):</div>
                <div style="color:var(--text); padding-left:10px; margin-bottom:10px;">
                    ${(m.pip_requirements || []).length > 0 ? (m.pip_requirements || []).map(r => `&bull; ${r}`).join('<br>') : '<span style="color:var(--muted)">-</span>'}
                </div>
                
                ${(m.widgets || []).length > 0 ? `
                    <div style="color:var(--muted); margin-bottom:4px;">Widgets (${(m.widgets || []).length}):</div>
                    <div style="color:var(--text); padding-left:10px; margin-bottom:10px;">
                        ${m.widgets.map(w => `&bull; <b>${w.id || '-'}</b> &rarr; <span style="color:var(--muted)">${w.extension_path || '-'}</span>`).join('<br>')}
                    </div>
                ` : ''}
                
                ${m.config_panel && Object.keys(m.config_panel).length > 0 ? `
                    <div style="color:var(--muted); margin-bottom:4px;">Config Panel:</div>
                    <div style="display:grid; grid-template-columns:100px 1fr; gap:2px; padding-left:10px; margin-bottom:10px;">
                        <div style="color:var(--muted)">Tab ID:</div><div style="color:var(--text)">${m.config_panel.tab_id || '-'}</div>
                        <div style="color:var(--muted)">Label:</div><div style="color:var(--text)">${m.config_panel.tab_label || '-'}</div>
                        <div style="color:var(--muted)">Category:</div><div style="color:var(--text)">${m.config_panel.category || '-'}</div>
                    </div>
                ` : ''}
                
                ${m.commands && Object.keys(m.commands).length > 0 ? `
                    <div style="color:var(--muted); margin-bottom:4px;">Commands (${Object.keys(m.commands).length}):</div>
                    <div style="color:var(--text); padding-left:10px; margin-bottom:10px;">
                        ${Object.keys(m.commands).map(k => `&bull; <b>${k}</b>: <span style="color:var(--muted)">${(String(m.commands[k]).substring(0, 55))}${String(m.commands[k]).length > 55 ? '...' : ''}</span>`).join('<br>')}
                    </div>
                ` : ''}
                
                ${(m.slash_commands || []).length > 0 ? `
                    <div style="color:var(--muted); margin-bottom:4px;">Slash Commands (details):</div>
                    <div style="color:var(--text); padding-left:10px; margin-bottom:10px;">
                        ${m.slash_commands.map(cmd => `&bull; <b>${cmd.id || ''}</b> <span style="color:var(--accent)">(${(cmd.aliases || []).join(', ')})</span> -- <span style="color:var(--muted)">${(cmd.description || '').substring(0, 45)}</span>`).join('<br>')}
                    </div>
                ` : ''}
            </div>

        </div>
    </div>
    `;
};

window.builderViewAllCaps = async function() {
    const sources = window.builderSourcesData;
    if (!sources || sources.length === 0) {
        window.builderLog('All Info Sheets: No packages found. Run a scan first.', 'error');
        return;
    }
    
    // We construct full paths from rel_paths
    const baseDir = document.getElementById('builder-sources-root')?.value || '';
    const paths = sources.map(s => baseDir + '\\\\' + s.rel_path);
    
    let combinedReport = [];
    let successCount = 0;
    
    _builderModal(`<div style="padding:20px; text-align:center;">
        <i class="fas fa-circle-notch fa-spin fa-2x"></i><br><br>
        <span id="batch-progress-text">Generating Info Sheets: 0 / ${paths.length}...</span>
    </div>`, false);
    const tEl = document.getElementById('builder-info-modal-title');
    if (tEl) tEl.innerHTML = `<i class="fas fa-list-ul" style="color:var(--accent); margin-right:8px;"></i>All Info Sheets: Scanning...`;

    for (let i = 0; i < paths.length; i++) {
        const path = paths[i];
        const pText = document.getElementById('batch-progress-text');
        if (pText) pText.innerText = `Generating Info Sheets: ${i+1} / ${paths.length}...`;
        
        try {
            const resp = await fetch('/api/hpm/builder/load', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ src_dir: path }) });
            const data = await resp.json();
            if (data.ok && data.manifest) {
                const html = window.builderGenerateInfoSheetHTML(data.manifest);
                combinedReport.push(html);
                successCount++;
            }
        } catch(e) { }
    }
    
    const html = `<div style="padding:15px; max-height:60vh; overflow-y:auto; text-align:left; font-size:0.9em; line-height:1.4;" class="custom-scrollbar">
        <h4 style="margin-bottom:15px; text-transform:uppercase; font-weight:800; text-align:center;">All Package Info Sheets <span style="color:var(--muted); font-size:0.7em;">(${successCount} packages)</span></h4>
        <div style="background:rgba(255,255,255,0.02); padding:15px; border-radius:8px; border:1px solid rgba(255,255,255,0.05);">
            ${combinedReport.join('')}
        </div>
        <div style="text-align:center; margin-top:20px;">
            <button class="btn btn-primary" onclick="_builderModal(false)">Close Sheets</button>
        </div>
    </div>`;
    _builderModal(html, false);
    const tEl2 = document.getElementById('builder-info-modal-title');
    if (tEl2) tEl2.innerHTML = '<i class="fas fa-list-ul" style="color:var(--accent); margin-right:8px;"></i>All Package Info Sheets';
};

