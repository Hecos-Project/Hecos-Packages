// ── SSE Log stream ────────────────────────────────────────────────
function startLogStream(runId, onDone) {
  if (sseSource) sseSource.close();
  const log1 = document.getElementById('log-output');
  const log2 = document.getElementById('canvas-log-output');
  if (log1) log1.innerHTML = '';
  if (log2) log2.innerHTML = '';
  const status = document.getElementById('log-status');
  if (status) status.textContent = `Run: ${runId}`;

  sseSource = new EventSource(`/api/flows/${currentFlowId}/log/stream?run_id=${runId}`);
  sseSource.onmessage = e => {
    const ev = JSON.parse(e.data);
    appendLog(ev);
    if (ev.type === 'stream_end') { 
      sseSource.close();
      if (status) status.textContent = 'Done';
      if (typeof onDone === 'function') onDone();
    }
  };
  sseSource.onerror = () => { 
    if (status) status.textContent = 'Stream ended'; 
    sseSource.close();
    if (typeof onDone === 'function') onDone();
  };
}

function appendLog(ev) {
  const log1 = document.getElementById('log-output');
  const log2 = document.getElementById('canvas-log-output');
  if (log1) {
    const empty = log1.querySelector('.log-empty');
    if (empty) empty.remove();
  }
  if (log2) {
    const empty = log2.querySelector('.log-empty');
    if (empty) empty.remove();
  }

  let cls='info', icon='fa-circle', text='';
  const ts = ev.ts ? ev.ts.slice(11,19) : '';
  
  if (ev.type==='flow_start')    { cls='start'; icon='fa-play-circle';   text=`▶ Flow started: ${ev.flow_id}`;
    if (typeof resetNodeStates === 'function') resetNodeStates();
    if (typeof resetTimelineNodeStates === 'function') resetTimelineNodeStates();
    if (typeof startTimelineRun === 'function') startTimelineRun(ev.flow_id, null);
  }
  else if (ev.type==='flow_done')    { cls='ok';    icon='fa-check-circle';  text=`✅ Flow completed`;
    if (typeof finishTimelineRun === 'function') finishTimelineRun('done');
    if (typeof applyFlowOutcome === 'function') applyFlowOutcome(currentFlowId || ev.flow_id, 'done');
  }
  else if (ev.type==='flow_aborted') { cls='abort';  icon='fa-ban';           text=`⛔ Flow aborted by user`;
    if (typeof resetNodeStates === 'function') resetNodeStates();
    if (typeof finishTimelineRun === 'function') finishTimelineRun('error');
    if (typeof applyFlowOutcome === 'function') applyFlowOutcome(currentFlowId || ev.flow_id, 'aborted');
  }
  else if (ev.type==='flow_error')   { cls='error';  icon='fa-times-circle';  text=`❌ Flow error: ${ev.error}`;
    if (typeof finishTimelineRun === 'function') finishTimelineRun('error');
    if (typeof applyFlowOutcome === 'function') applyFlowOutcome(currentFlowId || ev.flow_id, 'error');
  }
  else if (ev.type==='step_start')   {
    if (ev._subflow) {
      cls='info'; icon='fa-caret-right';
      text=`    ↳ [${ev._subflow_id}] ${(ev.step_id||'').trim()} (${ev.action})`;
    } else {
      cls='info'; icon='fa-cog'; text=`  → ${ev.step_id} (${ev.action})`;
      if (typeof setNodeState === 'function') setNodeState(ev.step_id, 'running');
      if (typeof setTimelineNodeState === 'function') setTimelineNodeState(ev.step_id, 'running');
      if (typeof _tlUpdateHeaders === 'function') _tlUpdateHeaders({ currentStep: ev.step_id });
    }
  }
  else if (ev.type==='step_ok')      {
    if (ev._subflow) {
      cls='ok'; icon='fa-check';
      text=`    ↳ ✓ [${ev._subflow_id}] ${(ev.step_id||'').trim()}${ev.output ? ' → '+ev.output.slice(0,60) : ''}`.trim();
    } else {
      cls='ok'; icon='fa-check';
      text=`  ✓ ${ev.step_id}${ev.output?' → '+ev.output.slice(0,80):''}`.trim();
      if (typeof setNodeState === 'function') setNodeState(ev.step_id, 'done');
      if (typeof setTimelineNodeState === 'function') setTimelineNodeState(ev.step_id, 'done');
    }
  }
  else if (ev.type==='step_error')   {
    if (ev._subflow) {
      cls='error'; icon='fa-exclamation';
      text=`    ↳ ✗ [${ev._subflow_id}] ${(ev.step_id||'').trim()}: ${ev.error}`;
    } else {
      cls='error'; icon='fa-exclamation';
      text=`  ✗ ${ev.step_id}: ${ev.error}`;
      if (typeof setNodeState === 'function') setNodeState(ev.step_id, 'error');
      if (typeof setTimelineNodeState === 'function') setTimelineNodeState(ev.step_id, 'error');
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
    
    if (log1) { log1.appendChild(banner.cloneNode(true)); log1.scrollTop = log1.scrollHeight; }
    if (log2) { log2.appendChild(banner.cloneNode(true)); log2.scrollTop = log2.scrollHeight; }
    
    return;
  }
  else if (ev.type==='audio_start')  { cls='info';   icon='fa-volume-up';     text=`  🔊 ${ev.step_id} playing audio...`;
    if (typeof setNodeAudioState === 'function') setNodeAudioState(ev.step_id, true);
  }
  else if (ev.type==='audio_stop')   { cls='info';   icon='fa-volume-mute';   text=`  🔇 ${ev.step_id} finished audio`;
    if (typeof setNodeAudioState === 'function') setNodeAudioState(ev.step_id, false);
  }
  else if (ev.type==='connected')    { cls='info';   icon='fa-link';          text=`Connected to run ${ev.run_id}`; }
  else if (ev.type==='toast')        {
    if (typeof window.toast === 'function') window.toast(ev.level || 'info', ev.message);
    return;
  }
  else if (ev.type==='step_waiting_input') {
    if (typeof window.toast === 'function') window.toast('info', '⏳ Flow is waiting for your input...');
    
    const line = document.createElement('div');
    line.className = `log-line info`;
    line.innerHTML = `<span class="ts">${ts}</span><span class="evt"><i class="fas fa-microphone"></i> <strong>Waiting for input:</strong> ${ev.prompt}</span>`;
    
    const inputDiv = document.createElement('div');
    inputDiv.style.padding = '8px';
    inputDiv.style.marginTop = '4px';
    inputDiv.style.background = 'rgba(0,0,0,0.2)';
    inputDiv.style.borderRadius = '4px';
    inputDiv.style.display = 'flex';
    inputDiv.style.gap = '8px';
    
    const inputField = document.createElement('input');
    inputField.type = 'text';
    inputField.placeholder = ev.intercept_mode === 'explicit' ? 'Type @flow [your answer]' : 'Type your answer...';
    inputField.style.flex = '1';
    inputField.style.background = 'rgba(255,255,255,0.05)';
    inputField.style.border = '1px solid rgba(255,255,255,0.1)';
    inputField.style.color = '#fff';
    inputField.style.padding = '6px 10px';
    inputField.style.borderRadius = '4px';
    
    const btn = document.createElement('button');
    btn.textContent = 'Send';
    btn.className = 'hc-btn primary';
    btn.style.padding = '4px 12px';
    
    const submit = () => {
      let text = inputField.value.trim();
      if (!text) return;
      if (ev.intercept_mode === 'explicit' && !text.toLowerCase().startsWith('@flow ')) {
        text = '@flow ' + text;
      }
      btn.disabled = true;
      inputField.disabled = true;
      fetch(`/api/flows/run/${ev.run_id}/input`, {
        method: 'POST',
        body: JSON.stringify({ text })
      }).then(r => r.json()).then(d => {
        if (!d.ok && typeof window.toast === 'function') window.toast('error', d.error);
        else {
          btn.textContent = 'Sent';
          btn.style.background = 'var(--flows-ok)';
        }
      });
    };
    
    btn.onclick = submit;
    inputField.onkeydown = e => { if (e.key === 'Enter') submit(); };
    
    inputDiv.appendChild(inputField);
    inputDiv.appendChild(btn);
    line.appendChild(inputDiv);
    
    // Auto focus the input field
    setTimeout(() => inputField.focus(), 100);
    
    // Also append to the other log if it exists
    if (log1 && log2) {
      if (log1) { log1.appendChild(line); log1.scrollTop = log1.scrollHeight; }
      if (log2 && log1) { 
        const lineClone = line.cloneNode(true);
        // We'd need to re-bind events for the clone. For simplicity in wait_input, 
        // we'll just append it to whichever log is currently visible, or both, but only one will have the working button.
        // Actually, better to just append the original to both? No, a node can only be in one place.
        // Let's just append to log2 (the overlay) if it exists, otherwise log1.
        if (log2) {
          log2.appendChild(line);
          log2.scrollTop = log2.scrollHeight;
        } else if (log1) {
          log1.appendChild(line);
          log1.scrollTop = log1.scrollHeight;
        }
      }
    } else {
      const targetLog = log2 || log1;
      if (targetLog) {
        targetLog.appendChild(line);
        targetLog.scrollTop = targetLog.scrollHeight;
      }
    }
    
    return;
  }
  else return;

  const htmlContent = `<span class="ts">${ts}</span><span class="evt"><i class="fas ${icon}"></i> ${text}</span>`;
  
  if (log1) {
    const line1 = document.createElement('div');
    line1.className = `log-line ${cls}`;
    line1.innerHTML = htmlContent;
    log1.appendChild(line1);
    log1.scrollTop = log1.scrollHeight;
  }
  if (log2) {
    const line2 = document.createElement('div');
    line2.className = `log-line ${cls}`;
    line2.innerHTML = htmlContent;
    log2.appendChild(line2);
    log2.scrollTop = log2.scrollHeight;
  }
}

function clearLog() {
  const log1 = document.getElementById('log-output');
  const log2 = document.getElementById('canvas-log-output');
  const msg = '<div class="log-empty">Log cleared.</div>';
  if (log1) log1.innerHTML = msg;
  if (log2) log2.innerHTML = msg;
}
