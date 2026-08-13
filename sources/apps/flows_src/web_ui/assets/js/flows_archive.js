// ── Archive Loading & Rendering ──────────────────────────────────────────────

async function loadArchive() {
    const listEl = document.getElementById('archive-list');
    if (!listEl) return;
    listEl.innerHTML = '<div class="log-empty"><i class="fas fa-circle-notch fa-spin"></i> Loading...</div>';
    
    try {
        const res = await fetch('/api/flows/archive');
        const data = await res.json();
        
        if (!data.ok) {
            listEl.innerHTML = `<div class="log-empty" style="color:var(--flows-danger)">Error: ${data.error}</div>`;
            return;
        }
        
        if (!data.runs || data.runs.length === 0) {
            listEl.innerHTML = '<div class="log-empty">No archived runs found.</div>';
            return;
        }
        
        renderArchiveList(data.runs);
    } catch (err) {
        listEl.innerHTML = `<div class="log-empty" style="color:var(--flows-danger)">Failed to load archive: ${err}</div>`;
    }
}

function renderArchiveList(runs) {
    const listEl = document.getElementById('archive-list');
    listEl.innerHTML = '';
    
    // Group by date
    const groups = {};
    for (const run of runs) {
        // Date in local format
        const d = new Date(run.started_at);
        const dateKey = d.toLocaleDateString(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
        if (!groups[dateKey]) groups[dateKey] = [];
        groups[dateKey].push(run);
    }
    
    for (const [dateKey, groupRuns] of Object.entries(groups)) {
        const groupEl = document.createElement('div');
        groupEl.className = 'archive-group';
        
        const titleEl = document.createElement('div');
        titleEl.className = 'archive-group-title';
        titleEl.innerHTML = `<i class="fas fa-calendar-day"></i> ${dateKey}`;
        groupEl.appendChild(titleEl);
        
        for (const run of groupRuns) {
            const itemEl = document.createElement('div');
            itemEl.className = 'archive-item';
            
            let icon = 'fa-question-circle', color = 'var(--flows-muted)';
            if (run.outcome === 'done') { icon = 'fa-check-circle'; color = 'var(--flows-success)'; }
            else if (run.outcome === 'error') { icon = 'fa-times-circle'; color = 'var(--flows-danger)'; }
            else if (run.outcome === 'aborted') { icon = 'fa-ban'; color = '#a855f7'; }
            
            const timeStr = new Date(run.started_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            
            // Calculate duration if possible
            let durationStr = '';
            if (run.ended_at) {
                const ms = new Date(run.ended_at) - new Date(run.started_at);
                if (ms < 1000) durationStr = `${ms}ms`;
                else durationStr = `${(ms/1000).toFixed(1)}s`;
            }
            
            itemEl.innerHTML = `
                <div class="archive-item-icon"><i class="fas ${icon}" style="color:${color}"></i></div>
                <div class="archive-item-content">
                    <div class="archive-item-title">${run.flow_name || run.flow_id}</div>
                    <div class="archive-item-meta">${timeStr} &bull; ${run.step_count || 0} steps ${durationStr ? '&bull; ' + durationStr : ''}</div>
                </div>
            `;
            
            itemEl.onclick = () => {
                document.querySelectorAll('.archive-item').forEach(el => el.classList.remove('active'));
                itemEl.classList.add('active');
                loadArchivedRun(run.run_id);
            };
            
            groupEl.appendChild(itemEl);
        }
        
        listEl.appendChild(groupEl);
    }
}

async function loadArchivedRun(runId) {
    const headerEl = document.getElementById('archive-details-header');
    const logsEl = document.getElementById('archive-details-logs');
    
    logsEl.innerHTML = '<div class="log-empty"><i class="fas fa-circle-notch fa-spin"></i> Loading run details...</div>';
    headerEl.style.display = 'none';
    
    try {
        const res = await fetch(`/api/flows/archive/${runId}`);
        const data = await res.json();
        
        if (!data.ok) {
            logsEl.innerHTML = `<div class="log-empty" style="color:var(--flows-danger)">Error: ${data.error}</div>`;
            return;
        }
        
        const run = data.run;
        
        // Update header
        document.getElementById('ad-flow-name').textContent = run.flow_name || run.flow_id;
        document.getElementById('ad-run-id').textContent = run.run_id;
        document.getElementById('ad-date').textContent = new Date(run.started_at).toLocaleString();
        
        let outcomeStr = `<span style="color:var(--flows-success)">Done</span>`;
        if (run.outcome === 'error') outcomeStr = `<span style="color:var(--flows-danger)">Error</span>`;
        if (run.outcome === 'aborted') outcomeStr = `<span style="color:#a855f7">Aborted</span>`;
        document.getElementById('ad-outcome').innerHTML = outcomeStr;
        
        headerEl.style.display = 'block';
        
        // Render events
        logsEl.innerHTML = '';
        if (!run.events || run.events.length === 0) {
            logsEl.innerHTML = '<div class="log-empty">No events recorded for this run.</div>';
            return;
        }
        
        renderHistoricalEvents(run.events, logsEl);
        
    } catch (err) {
        logsEl.innerHTML = `<div class="log-empty" style="color:var(--flows-danger)">Failed to load run: ${err}</div>`;
    }
}

function renderHistoricalEvents(events, container) {
    container.innerHTML = '';
    
    for (const ev of events) {
        let cls='info', icon='fa-circle', text='';
        const ts = ev.ts ? ev.ts.slice(11,19) : '';
        
        if (ev.type==='flow_start')    { cls='start'; icon='fa-play-circle';   text=`▶ Flow started: ${ev.flow_id}`; }
        else if (ev.type==='flow_done')    { cls='ok';    icon='fa-check-circle';  text=`✅ Flow completed`; }
        else if (ev.type==='flow_aborted') { cls='abort';  icon='fa-ban';           text=`⛔ Flow aborted by user`; }
        else if (ev.type==='flow_error')   { cls='error';  icon='fa-times-circle';  text=`❌ Flow error: ${ev.error}`; }
        else if (ev.type==='step_start')   {
          if (ev._subflow) {
            cls='info'; icon='fa-caret-right';
            text=`    ↳ [${ev._subflow_id}] ${(ev.step_id||'').trim()} (${ev.action})`;
          } else {
            cls='info'; icon='fa-cog'; text=`  → ${ev.step_id} (${ev.action})`;
          }
        }
        else if (ev.type==='step_ok')      {
          if (ev._subflow) {
            cls='ok'; icon='fa-check';
            text=`    ↳ ✓ [${ev._subflow_id}] ${(ev.step_id||'').trim()}${ev.output ? ' → '+ev.output.slice(0,60) : ''}`.trim();
          } else {
            cls='ok'; icon='fa-check';
            text=`  ✓ ${ev.step_id}${ev.output?' → '+ev.output.slice(0,80):''}`.trim();
          }
        }
        else if (ev.type==='step_error')   {
          if (ev._subflow) {
            cls='error'; icon='fa-exclamation';
            text=`    ↳ ✗ [${ev._subflow_id}] ${(ev.step_id||'').trim()}: ${ev.error}`;
          } else {
            cls='error'; icon='fa-exclamation';
            text=`  ✗ ${ev.step_id}: ${ev.error}`;
          }
        }
        else if (ev.type==='subflow_start') {
            const fname = ev._subflow_name || ev.flow_id || ev._subflow_id || 'Unknown Flow';
            const rid = ev._sub_run_id || ev.run_id || 'unknown_run';
            
            const banner = document.createElement('div');
            banner.className = 'log-subflow-banner';
            banner.innerHTML = `
              <div class="banner-top"><i class="fas fa-bolt"></i> SUB-FLOW STARTED: <strong>${fname}</strong></div>
              <div class="banner-bot">Run ID: ${rid}</div>
            `;
            container.appendChild(banner);
            continue;
        }
        else if (ev.type==='audio_start')  { cls='info';   icon='fa-volume-up';     text=`  🔊 ${ev.step_id} playing audio...`; }
        else if (ev.type==='audio_stop')   { cls='info';   icon='fa-volume-mute';   text=`  🔇 ${ev.step_id} finished audio`; }
        else if (ev.type==='connected')    { cls='info';   icon='fa-link';          text=`Connected to run ${ev.run_id}`; }
        else continue;

        const line = document.createElement('div');
        line.className = `log-line ${cls}`;
        line.innerHTML = `<span class="ts">${ts}</span><span class="evt"><i class="fas ${icon}"></i> ${text}</span>`;
        container.appendChild(line);
    }
}

// Ensure loadArchive is called when the tab is switched
document.addEventListener('DOMContentLoaded', () => {
    const archiveBtn = document.querySelector('.tab-btn[data-tab="archive"]');
    if (archiveBtn) {
        archiveBtn.addEventListener('click', () => {
            // Give the UI a tiny moment to switch tabs before loading
            setTimeout(loadArchive, 50);
        });
    }
});
