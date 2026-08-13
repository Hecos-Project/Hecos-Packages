// ── Flows API Calls ───────────────────────────────────────────────
let _allFlows = [];


async function selectFlow(flowId) {
  try {
    const res = await fetch(`/api/flows/${flowId}`);
    const d = await res.json();
    if (!d.ok) throw new Error(d.error);
    currentFlowId = flowId;
    currentFlowData = d.flow;

    // Update sidebar selection
    document.querySelectorAll('.flow-item').forEach(el => {
      el.classList.toggle('active', el.dataset.id === flowId);
    });

    // Populate toolbar
    const tlInput = document.getElementById('flow-title');
    if (tlInput) {
      tlInput.value = d.flow.name || flowId;
      tlInput.title = `ID: ${flowId}`;
    }

    ['btn-run','btn-save','btn-delete','btn-palette','btn-export','btn-flow-settings'].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) btn.disabled = false;
    });

    // Set YAML editor
    if (cmEditor) cmEditor.setValue(d.yaml || '');

    // Render canvas nodes via ReactFlow bridge (flows_canvas_shim.js)
    if (typeof renderCanvasFromFlow === 'function') renderCanvasFromFlow(d.flow);

    // Render timeline (from flows_canvas_shim.js)
    if (typeof renderTimeline === 'function') renderTimeline(d.flow);

    // Sync run button state from backend
    try {
      const sres = await fetch(`/api/flows/${flowId}/status`);
      const sd = await sres.json();
      if (sd.ok && sd.running) {
        setRunningState(true, sd.run_id);
        if (typeof startLogStream === 'function') startLogStream(sd.run_id, () => setRunningState(false));
      }
      else setRunningState(false);
    } catch { setRunningState(false); }

  } catch(e) { toast('error','Could not load flow: '+e.message); }
}

async function saveCurrentFlow(silent = false) {
  if (!currentFlowId && (!cmEditor || !cmEditor.getValue().trim())) return;
  // Always sync canvas → YAML before reading cmEditor, regardless of active tab.
  // This is the ONLY place where canvas positions are flushed to disk.
  if (typeof syncCanvasToYaml === 'function') {
    syncCanvasToYaml(); 
  }
  let yaml = cmEditor.getValue();

  // Auto-deduplicate step IDs
  if (typeof jsyaml !== 'undefined') {
    try {
      const flowObj = jsyaml.load(yaml);
      if (flowObj && Array.isArray(flowObj.pipeline)) {
        let changed = false;
        let seen = new Set();
        flowObj.pipeline.forEach((step, idx) => {
          if (!step.id) { step.id = 'step_' + idx; changed = true; }
          if (seen.has(step.id)) {
            let baseId = String(step.id).replace(/(_copy\d*|\s\(\d+\)|\s\d+)$/, '').trim();
            let count = 1;
            let newId = baseId + ' ' + count;
            while(seen.has(newId)) { count++; newId = baseId + ' ' + count; }
            step.id = newId;
            changed = true;
          }
          seen.add(step.id);
        });
        if (changed) {
          yaml = jsyaml.dump(flowObj, { indent: 2, lineWidth: -1 });
          const scrollInfo = cmEditor.getScrollInfo();
          cmEditor.setValue(yaml);
          cmEditor.scrollTo(scrollInfo.left, scrollInfo.top);
          if (typeof renderCanvasFromFlow === 'function') renderCanvasFromFlow(flowObj);
          if (!silent) toast('info', 'Auto-corrected duplicate step IDs.');
        }
      }
    } catch(e) { console.warn("Deduplication error:", e); }
  }
  try {
    const res = await fetch('/api/flows/save', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({yaml})
    });
    const d = await res.json();
    if (!d.ok) {
      if (!silent) {
        const errs = d.errors || [d.error || 'Unknown error'];
        toast('error', '❌ Save failed:\n' + errs.map((e,i) => `${i+1}. ${e}`).join('\n'));
      }
      console.warn('[Flows] Save validation errors:', d.errors || d.error);
      return;
    }
    if (!silent) {
      toast('ok','✓ Synced');
      loadFlowsList();
    }
    currentFlowId = d.flow_id;
  } catch(e) { 
    if (!silent) toast('error','Save failed: '+e.message); 
  }
}

// ── Export / Import ──────────────────────────────────────────────

/**
 * Inject the Hecos flow type marker into a YAML string.
 * Adds \`_type: hecos_flow\` after the first line (or at top if missing).
 */
function _injectFlowTypeMarker(yaml) {
  if (yaml.includes('_type: hecos_flow')) return yaml;
  // Insert after first non-empty line
  const lines = yaml.split('\n');
  const insertAt = lines.findIndex(l => l.trim() !== '');
  if (insertAt === -1) return '_type: hecos_flow\n' + yaml;
  lines.splice(insertAt + 1, 0, '_type: hecos_flow');
  return lines.join('\n');
}

/**
 * Export the current flow as a .heflow file.
 * Uses the native OS Save-As dialog (File System Access API) when available,
 * falling back to a standard browser download.
 * The exported file is a YAML with an injected \`_type: hecos_flow\` marker
 * so it can be reliably distinguished from generic YAML files.
 */
async function exportCurrentFlow() {
  if (!currentFlowId && (!cmEditor || !cmEditor.getValue().trim())) {
    toast('info', window.t('flows_export_select_first'));
    return;
  }
  const rawYaml = cmEditor ? cmEditor.getValue() : '';
  if (!rawYaml.trim()) { toast('error', window.t('flows_export_empty')); return; }

  // Inject type marker so the file is self-identifying
  const yamlToSave = _injectFlowTypeMarker(rawYaml);

  // Suggested filename: <flow_id>.heflow
  const suggestedName = (currentFlowId || 'flow_export') + '.heflow';

  // ── Strategy 1: native OS Save-As dialog (Chrome/Edge) ───────────────
  if (typeof window.showSaveFilePicker === 'function') {
    try {
      const fileHandle = await window.showSaveFilePicker({
        suggestedName,
        types: [{
          description: 'Hecos Flow File',
          accept: { 'text/plain': ['.heflow'] },
        }],
      });
      const writable = await fileHandle.createWritable();
      await writable.write(yamlToSave);
      await writable.close();
      toast('ok', window.t('flows_export_saved').replace('{name}', fileHandle.name));
      return;
    } catch (err) {
      // User cancelled the dialog — do nothing
      if (err.name === 'AbortError') return;
      // Unexpected error — fall through to download fallback
      console.warn('[Flows] showSaveFilePicker failed, falling back to download:', err);
    }
  }

  // ── Strategy 2: standard browser download (fallback) ───────────────
  const blob = new Blob([yamlToSave], { type: 'text/plain' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = suggestedName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  toast('ok', window.t('flows_export_done').replace('{name}', suggestedName));
}

/**
 * Import a .heflow (or .yaml) file from disk into the YAML editor.
 * Validates that the file is a genuine Hecos flow before loading.
 * Fires after the user picks a file from the hidden <input type="file">.
 * Does NOT auto-save — the user must click Save after review.
 */
function importFlowFromFile(inputEl) {
  const file = inputEl.files[0];
  if (!file) return;
  inputEl.value = '';

  const reader = new FileReader();
  reader.onload = e => {
    const yaml = e.target.result;
    if (!yaml || !yaml.trim()) {
      toast('error', window.t('flows_import_empty_file'));
      return;
    }

    // ── Validation: is this actually a Hecos flow? ──────────────────
    const isHeflowExt = file.name.toLowerCase().endsWith('.heflow');
    let parsed = null;
    try {
      if (typeof jsyaml !== 'undefined') parsed = jsyaml.load(yaml);
    } catch(parseErr) {
      toast('error', window.t('flows_import_yaml_invalid').replace('{error}', parseErr.message));
      return;
    }

    // Must have either .heflow extension OR _type marker OR pipeline field
    const hasTypeMarker = parsed && parsed._type === 'hecos_flow';
    const hasPipeline   = parsed && Array.isArray(parsed.pipeline);
    if (!isHeflowExt && !hasTypeMarker && !hasPipeline) {
      toast('error', window.t('flows_import_invalid_file'));
      return;
    }

    // ── Extract name / id ───────────────────────────────────────
    let flowName = file.name.replace(/\.(heflow|ya?ml)$/i, '');
    let flowId   = flowName;
    if (parsed) {
      if (parsed.name) flowName = parsed.name;
      if (parsed.id)   flowId   = parsed.id;
    }

    // Load into editor
    if (cmEditor) cmEditor.setValue(yaml);
    currentFlowId   = flowId;
    currentFlowData = null;

    // Update toolbar
    const tlInput = document.getElementById('flow-title');
    if (tlInput) { 
      tlInput.value = flowName; 
      tlInput.disabled = false; 
      tlInput.title = `ID: ${flowId}`;
    }
    ['btn-save','btn-export'].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) btn.disabled = false;
    });
    ['btn-run','btn-delete'].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) btn.disabled = true;
    });

    // Mark in sidebar
    const _list = document.getElementById('flows-list');
    if (_list) {
      _list.querySelectorAll('.flow-item').forEach(el => el.classList.remove('active'));
      const existing = _list.querySelector(`.flow-item[data-id="${CSS.escape(flowId)}"]`);
      if (existing) {
        existing.classList.add('active');
      } else {
        const prev = _list.querySelector('.flow-item-unsaved');
        if (prev) prev.remove();
        const newEl = document.createElement('div');
        newEl.className = 'flow-item active flow-item-unsaved';
        newEl.innerHTML = `
          <span class="flow-drag-handle">⠿</span>
          <div class="flow-item-name">
            <span class="flow-status-dot disabled"></span>
            ↑ ${flowName} <em style="font-size:.7rem;opacity:.6">(imported)</em>
          </div>
          <div class="flow-item-meta"><span>manual</span><span>—</span></div>`;
        _list.prepend(newEl);
      }
    }

    const stepCount = hasPipeline ? parsed.pipeline.length : '?';
    toast('ok', window.t('flows_import_done').replace('{name}', flowName).replace('{count}', stepCount));
    const yamlTabBtn = document.querySelector('.tab-btn[data-tab="yaml"]');
    if (yamlTabBtn) yamlTabBtn.click();
  };
  reader.onerror = () => toast('error', window.t('flows_import_read_error'));
  reader.readAsText(file);
}

// ── Manual Flow Creation ──────────────────────────────────────────

function newEmptyCanvas() {
  currentFlowId = 'new_flow_' + Date.now().toString(36);
  const startNode = {
    id: 'start_1',
    action: 'CONTROL__start',
    params: { priority: 0 },
    disable_mode: 'stop',
    position: { x: 200, y: 150 }
  };
  currentFlowData = { name: 'New Flow', trigger: { type: 'manual' }, pipeline: [startNode] };
  
  const tlInput = document.getElementById('flow-title');
  if (tlInput) {
    tlInput.value = 'New Flow';
    tlInput.disabled = false;
  }
  
  if (typeof renderCanvasFromFlow === 'function') renderCanvasFromFlow(currentFlowData);
  if (cmEditor) cmEditor.setValue(`id: ${currentFlowId}\nname: New Flow\ntrigger:\n  type: manual\npipeline:\n  - id: start_1\n    action: CONTROL__start\n    params:\n      priority: 0\n    disable_mode: stop\n    position:\n      x: 200\n      y: 150`);
  
  // Add a temporary unsaved entry to the sidebar so the new flow is visible
  document.querySelectorAll('.flow-item').forEach(el => el.classList.remove('active'));
  const _list = document.getElementById('flows-list');
  const _emptyHint = document.getElementById('flows-sidebar-empty');
  if (_emptyHint) _emptyHint.style.display = 'none';
  if (_list) {
    const prev = _list.querySelector('.flow-item-unsaved');
    if (prev) prev.remove();
    const newEl = document.createElement('div');
    newEl.className = 'flow-item active flow-item-unsaved';
    newEl.innerHTML = `
      <div class="flow-item-name">
        <span class="flow-status-dot disabled"></span>
        ✦ New Flow <em style="font-size:.7rem;opacity:.6">(unsaved)</em>
      </div>
      <div class="flow-item-meta"><span><i class="fas fa-bolt" style="font-size:.6rem"></i> manual</span><span>0 steps</span></div>`;
    _list.prepend(newEl);
  }
  
  // Enable save and palette, disable run/delete for now
  ['btn-save', 'btn-palette'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = false;
  });
  ['btn-run', 'btn-delete'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = true;
  });
  
  if (typeof renderTimeline === 'function') renderTimeline(currentFlowData);
}

// ── Autosave Interval ─────────────────────────────────────────────
let autosaveTimer = null;

// ── Keyboard Shortcuts (Hotkeys) ──────────────────────────────────
function initHotkeys() {
  document.addEventListener('keydown', function(e) {
    const isInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName);
    
    if (e.key === 's' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      saveCurrentFlow();
    }
    
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      runCurrentFlow();
    }
    
    if (e.key === 'Tab') {
      if (!isInput || e.target.id === 'flows-search-input') {
        e.preventDefault();
        togglePalette();
      }
    }
    
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (!isInput) {
        if (typeof deleteSelectedNodes === 'function') {
           deleteSelectedNodes();
        }
      }
    }
  });
}

document.addEventListener('DOMContentLoaded', initHotkeys);

// ── Autosave ──────────────────────────────────────────────────────
async function initFlowsAutosave() {
  try {
    const res = await fetch('/hecos/config');
    const cfg = await res.json();
    const flowsCfg = cfg?.plugins?.FLOWS || {};
    const enabled = flowsCfg.autosave_enabled !== false;
    const intervalMinutes = flowsCfg.autosave_interval_minutes || 1;
    if (enabled) {
      const ms = intervalMinutes * 60000;
      autosaveTimer = setInterval(() => {
        const saveBtn = document.getElementById('btn-save');
        if (currentFlowId && saveBtn && !saveBtn.disabled) saveCurrentFlow(true);
      }, ms);
    }
  } catch(e) {
    autosaveTimer = setInterval(() => {
      const saveBtn = document.getElementById('btn-save');
      if (currentFlowId && saveBtn && !saveBtn.disabled) saveCurrentFlow(true);
    }, 60000);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  setTimeout(initFlowsAutosave, 1000);
});

