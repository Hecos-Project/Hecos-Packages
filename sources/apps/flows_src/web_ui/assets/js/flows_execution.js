// ── Flows Execution & Lifecycle ──────────────────────────────────
// ── Sidebar running-state badges ──────────────────────────────────

/** Last known running map: { flow_id: run_id } – shared across polling & setRunningState */
let _lastKnownRunning = {};

/** Last run outcome per flow: { flow_id: 'done' | 'error' | 'aborted' } */
let _flowLastOutcome = {};

/**
 * Apply last-run outcome class to a sidebar item element.
 * Called after polling clears 'running' state, or on initial render.
 */
function applyFlowOutcome(flowId, outcome) {
  _flowLastOutcome[flowId] = outcome;
  const el = document.querySelector(`.flow-item[data-id="${flowId}"]`);
  if (!el) return;
  el.classList.remove('state-done', 'state-error', 'state-aborted');
  const indicator = el.querySelector('.flow-status-indicator');
  const txtStatus = el.querySelector('.flow-run-text-status');
  if (outcome === 'done') {
    el.classList.add('state-done');
    if (indicator) { indicator.classList.remove('enabled','disabled','error','running','aborted'); indicator.classList.add('done'); indicator.title = 'Last run: OK'; }
    if (txtStatus) { txtStatus.textContent = 'Done'; txtStatus.style.color = 'var(--flows-accent)'; }
  } else if (outcome === 'error') {
    el.classList.add('state-error');
    // Re-trigger CSS animation
    el.style.animation = 'none';
    el.offsetHeight; // reflow
    el.style.animation = '';
    if (indicator) { indicator.classList.remove('enabled','disabled','done','running','aborted'); indicator.classList.add('error'); indicator.title = 'Last run: Error'; }
    if (txtStatus) { txtStatus.textContent = 'Error'; txtStatus.style.color = 'var(--flows-danger)'; }
  } else if (outcome === 'aborted') {
    el.classList.add('state-aborted');
    if (indicator) { indicator.classList.remove('enabled','disabled','done','running','error'); indicator.classList.add('aborted'); indicator.title = 'Last run: Aborted'; }
    if (txtStatus) { txtStatus.textContent = 'Aborted'; txtStatus.style.color = '#fb923c'; }
  }
}
window.applyFlowOutcome = applyFlowOutcome;

/**
 * Update the sidebar spinner badges based on a running-map snapshot.
 * Does NOT modify _lastKnownRunning — call this purely for DOM sync.
 */
function _applyRunningBadges(runningMap) {
  const list = document.getElementById('flows-list');
  if (!list) return;
  list.querySelectorAll('.flow-item[data-id]').forEach(el => {
    const flowId = el.dataset.id;
    const isRunning = !!runningMap[flowId];
    el.classList.toggle('is-running', isRunning);
    const indicator = el.querySelector('.flow-status-indicator');
    const txtStatus = el.querySelector('.flow-run-text-status');

    if (isRunning) {
      // Clear any previous outcome state while running
      el.classList.remove('state-done', 'state-error', 'state-aborted');
      if (indicator) { indicator.className = 'flow-status-indicator running'; indicator.title = 'Running'; }
      if (txtStatus) { txtStatus.textContent = 'Running'; txtStatus.style.color = 'var(--flows-danger)'; }
    } else {
      // Check if we have a stored last-run outcome to show
      const outcome = _flowLastOutcome[flowId];
      if (outcome) {
        // applyFlowOutcome already handles DOM — just call it
        applyFlowOutcome(flowId, outcome);
      } else {
        // No outcome recorded yet: restore generic enabled/disabled dot
        el.classList.remove('state-done', 'state-error', 'state-aborted');
        if (indicator) {
          const wasEnabled = el.dataset.enabled !== 'false';
          indicator.className = 'flow-status-indicator ' + (wasEnabled ? 'enabled' : 'disabled');
          indicator.title = wasEnabled ? 'Enabled' : 'Disabled';
        }
        if (txtStatus) { txtStatus.textContent = 'Stopped'; txtStatus.style.color = 'var(--flows-success)'; }
      }
    }
  });
}

// ── Status polling ────────────────────────────────────────────────
let _statusPollTimer = null;

async function _pollRunningFlows() {
  try {
    const res = await fetch('/api/flows/running');
    if (!res.ok) return;
    const d = await res.json();
    if (!d.ok) return;
    _lastKnownRunning = d.running || {};
    _applyRunningBadges(_lastKnownRunning);

    // If we are viewing a flow that is no longer running, sync the Run/Stop button
    if (currentFlowId && !_lastKnownRunning[currentFlowId] && _currentRunId) {
      setRunningState(false);
    }

    // Stop polling automatically when nothing is running
    if (Object.keys(_lastKnownRunning).length === 0) {
      stopStatusPolling();
    }
  } catch { /* network hiccup – stay silent */ }
}

function startStatusPolling() {
  if (_statusPollTimer) return; // Already polling
  _statusPollTimer = setInterval(_pollRunningFlows, 2000);
  _pollRunningFlows(); // Immediate first tick
}

function stopStatusPolling() {
  if (_statusPollTimer) {
    clearInterval(_statusPollTimer);
    _statusPollTimer = null;
  }
}

// ── Run state helpers ────────────────────────────────────────────
let _currentRunId = null;

function setRunningState(running, runId) {
  _currentRunId = running ? runId : null;
  const btn = document.getElementById('btn-run');
  if (!btn) return;
  if (running) {
    btn.classList.add('running');
    btn.innerHTML = '<i class="fas fa-stop-circle"></i> Stop';
    btn.title = 'Click to stop the running flow';
    // Start global polling so all sidebar items light up correctly
    startStatusPolling();
  } else {
    btn.classList.remove('running');
    btn.innerHTML = '<i class="fas fa-play"></i> Run';
    btn.title = 'Execute this flow';
    // Trigger one last poll to clear badges, then polling auto-stops when idle
    _pollRunningFlows();
  }
}

async function runCurrentFlow() {
  if (!currentFlowId) return;
  await saveCurrentFlow(true); // Ensure latest changes are saved before running

  // If already running — act as STOP
  if (_currentRunId) {
    try {
      const res = await fetch(`/api/flows/${currentFlowId}/stop`, { method: 'POST' });
      const d = await res.json();
      if (d.ok) {
        toast('info', '⏹ Stop signal sent — flow will halt after current step.');
      } else {
        toast('error', 'Could not stop: ' + (d.error || 'unknown'));
      }
    } catch(e) { toast('error', 'Stop failed: ' + e.message); }
    return;
  }

  try {
    const res = await fetch(`/api/flows/${currentFlowId}/run`, { method: 'POST' });
    const d = await res.json();

    // 409 = already running
    if (res.status === 409) {
      toast('info', '⚠️ Flow is already running (run: ' + d.run_id + ')');
      // Reconnect to existing stream
      setRunningState(true, d.run_id);
      if (typeof window.openLogPanel === 'function') window.openLogPanel();
      if (typeof startLogStream === 'function') startLogStream(d.run_id);
      return;
    }

    if (!d.ok) throw new Error(d.error);

    setRunningState(true, d.run_id);
    toast('info', `▶ Flow started (run: ${d.run_id})`);

    if (typeof window.openLogPanel === 'function') window.openLogPanel();
    if (typeof startLogStream === 'function') startLogStream(d.run_id, () => setRunningState(false));
  } catch(e) { toast('error', 'Run failed: ' + e.message); }
}

async function deleteCurrentFlow() {
  if (!currentFlowId) { toast('info', window.t('flows_select_first')); return; }
  await deleteFlowById(currentFlowId, currentFlowData?.name || currentFlowId);
}

async function deleteFlowById(flowId, flowName) {
  const bg = document.getElementById('confirm-modal-bg');
  const text = document.getElementById('confirm-modal-text');
  const yesBtn = document.getElementById('confirm-modal-yes');
  
  if(bg && text && yesBtn) {
    text.innerText = window.t('flows_confirm_delete_text').replace('{name}', flowName);
    bg.style.display = 'flex';
    yesBtn.onclick = async () => {
      bg.style.display = 'none';
      await _doDeleteFlowById(flowId);
    };
  } else {
    if (!confirm(window.t('flows_confirm_delete_text').replace('{name}', flowName))) return;
    await _doDeleteFlowById(flowId);
  }
}

async function _doDeleteFlowById(flowId) {
  try {
    const res = await fetch(`/api/flows/${flowId}`, {method:'DELETE'});
    const d = await res.json();
    if (!d.ok) throw new Error(d.error);

    if (currentFlowId === flowId) {
      currentFlowId = null;
      currentFlowData = null;
      if (cmEditor) cmEditor.setValue('');
      // Clear ReactFlow canvas via bridge
      if (typeof renderCanvasFromFlow === 'function') renderCanvasFromFlow({ pipeline: [] });
      const tlInput = document.getElementById('flow-title');
      if (tlInput) tlInput.value='';
      ['btn-run','btn-save','btn-delete','btn-export'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.disabled=true;
      });
      if (typeof renderTimeline === 'function') renderTimeline(null);
    }

    toast('ok', window.t('flows_deleted_toast'));
    loadFlowsList();
  } catch(e) { toast('error', window.t('flows_delete_failed_toast').replace('{error}', e.message)); }
}

