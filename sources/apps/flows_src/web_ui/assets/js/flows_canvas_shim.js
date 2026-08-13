/**
 * flows_canvas_shim.js
 * ====================
 * Drop-in replacement for the old flows_canvas.js (LiteGraph-based).
 *
 * Exposes the SAME global function API that flows_api.js, flows_editor.js
 * and flows_logs.js already call — but internally delegates to the
 * ReactFlow bridge (window.HecosFlowsBridge) that is mounted by the
 * React bundle.
 *
 * Function parity with old flows_canvas.js:
 *   initCanvas()                 → no-op (React self-initialises)
 *   renderCanvasFromFlow(flow)   → bridge.renderCanvasFromFlow
 *   syncCanvasToYaml()           → bridge.exportFlowFromCanvas → js-yaml dump
 *   setNodeState(id, state)      → bridge.setNodeState
 *   setNodeAudioState(id, state) → bridge.setNodeAudioState
 *   resetNodeStates()            → bridge.resetNodeStates
 *   deleteSelectedNodes()        → bridge.deleteSelectedNodes
 *   resizeCanvas()               → no-op (React handles resize)
 */

// ── Wait for bridge to be ready ───────────────────────────────────────────────
function _withBridge(fn) {
  if (window.HecosFlowsBridge?._api) {
    fn(window.HecosFlowsBridge);
  } else {
    // Retry up to 3 s, React bundle may still be loading
    let tries = 0;
    const iv = setInterval(() => {
      if (window.HecosFlowsBridge?._api) {
        clearInterval(iv);
        fn(window.HecosFlowsBridge);
      } else if (++tries > 30) {
        clearInterval(iv);
        console.warn('[FlowsShim] ReactFlow bridge not ready after 3s');
      }
    }, 100);
  }
}

// ── No-op stubs for functions that LiteGraph had but React handles internally ─
function initCanvas() {}
function resizeCanvas() {}

// ── Main API ──────────────────────────────────────────────────────────────────

function renderCanvasFromFlow(flowObj) {
  _withBridge(b => b.renderCanvasFromFlow(flowObj));
  // Also render timeline (unchanged)
  if (typeof renderTimeline === 'function') renderTimeline(flowObj);
}

function syncCanvasToYaml() {
  _withBridge(b => {
    const flowObj = b.exportFlowFromCanvas();
    if (!flowObj || !cmEditor || typeof jsyaml === 'undefined') return;

    // Preserve existing top-level YAML keys (name, id, trigger, variables, etc.)
    let existing = {};
    try { existing = jsyaml.load(cmEditor.getValue()) || {}; } catch(e) {}

    const merged = { ...existing, ...flowObj };

    // Ensure required top-level fields are never missing
    if (!merged.id && typeof currentFlowId !== 'undefined' && currentFlowId) merged.id = currentFlowId;
    if (!merged.name) merged.name = (typeof currentFlowId !== 'undefined' && currentFlowId) ? currentFlowId.replace(/_/g, ' ') : 'New Flow';
    if (!merged.trigger) merged.trigger = { type: 'manual' };

    const newYaml = jsyaml.dump(merged, { indent: 2, lineWidth: -1 });
    const scrollInfo = cmEditor.getScrollInfo();
    cmEditor.setValue(newYaml);
    cmEditor.scrollTo(scrollInfo.left, scrollInfo.top);
  });
}

window.setNodeState = function(stepId, state) {
  _withBridge(b => b.setNodeState(stepId, state));
};

window.setNodeAudioState = function(stepId, isPlaying) {
  _withBridge(b => {
    if (typeof b.setNodeAudioState === 'function') b.setNodeAudioState(stepId, isPlaying);
  });
};

window.resetNodeStates = function() {
  _withBridge(b => b.resetNodeStates());
};

window.deleteSelectedNodes = function() {
  _withBridge(b => b.deleteSelectedNodes());
};

// ── Wire YAML editor → canvas sync ───────────────────────────────────────────
// Called once the React bundle is ready; wires up onGraphChange
// so that canvas changes automatically update the YAML CodeMirror editor.
function _initBridgeSync() {
  if (!window.HecosFlowsBridge) return;
  window.HecosFlowsBridge.onGraphChange = (flowObj) => {
    if (!cmEditor || typeof jsyaml === 'undefined') return;
    let existing = {};
    try { existing = jsyaml.load(cmEditor.getValue()) || {}; } catch(e) {}
    const merged = { ...existing, ...flowObj };

    // Guarantee required fields are never stripped
    if (!merged.id && typeof currentFlowId !== 'undefined' && currentFlowId) merged.id = currentFlowId;
    if (!merged.name) merged.name = (typeof currentFlowId !== 'undefined' && currentFlowId) ? currentFlowId.replace(/_/g, ' ') : 'New Flow';
    if (!merged.trigger) merged.trigger = { type: 'manual' };

    const newYaml = jsyaml.dump(merged, { indent: 2, lineWidth: -1 });
    const scrollInfo = cmEditor.getScrollInfo();
    cmEditor.setValue(newYaml);
    cmEditor.scrollTo(scrollInfo.left, scrollInfo.top);
    if (typeof validateYaml === 'function') validateYaml(newYaml);
  };
}

// Try immediately and on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
  // Give the React bundle a moment to mount
  setTimeout(_initBridgeSync, 500);
});

// ── Timeline ─────────────────────────────────────────────────────
// Shared state
let _tlRunStartTs    = null;
let _tlDurationTimer = null;
let _tlFlowName      = '';

/** Build a single node-card HTML string */
function _tlNodeCard(step, index, total) {
  const action = step.action || '';
  const method = action.split('__').slice(1).join('__') || action;
  const isLast = index === total - 1;

  let cat = 'action', icon = 'fa-bolt';
  if      (action.startsWith('TRIGGER__'))                          { cat='trigger'; icon='fa-clock'; }
  else if (action.startsWith('LOGIC__if'))                          { cat='logic';   icon='fa-code-branch'; }
  else if (action.startsWith('LOGIC__loop'))                        { cat='logic';   icon='fa-redo'; }
  else if (action.startsWith('LOGIC__delay'))                       { cat='logic';   icon='fa-hourglass-half'; }
  else if (action.startsWith('LOGIC__'))                            { cat='logic';   icon='fa-code-branch'; }
  else if (action.startsWith('AUDIO__')||action.startsWith('TTS__')||action.startsWith('ALARM__')) { cat='audio'; icon='fa-volume-up'; }
  else if (action.startsWith('HTTP__'))                             { cat='http';    icon='fa-globe'; }
  else if (action.startsWith('VAR__')||action.startsWith('LOGIC__set_var')) { cat='var'; icon='fa-database'; }
  else if (action.startsWith('USER__'))                             { cat='action';  icon='fa-user'; }
  else if (action.startsWith('AI__'))                               { cat='ai';      icon='fa-magic'; }

  const params = Object.entries(step.params || {}).slice(0,3)
    .map(([k,v]) => { 
      const val = typeof v === 'string' ? v : (JSON.stringify(v) || 'undefined'); 
      return `${k}: ${val.length > 18 ? val.slice(0,18)+'...' : val}`; 
    })
    .join('<br>');

  const outputLine = step.output_as ? `&rarr; ${step.output_as}` : '';
  const noteLine   = step.note      ? `&#x1F4DD; ${step.note}`   : '';
  const connector  = isLast ? '' : `<div class="tl-connector"><i class="fas fa-chevron-right"></i></div>`;

  return `<div class="tl-node-card" data-cat="${cat}" data-step-id="${step.id}" onclick="tlOpenNodeEditor('${step.id}')" title="${action}">
  <div class="tl-card-top">
    <div class="tl-card-icon"><i class="fas ${icon}"></i></div>
    <div class="tl-card-meta">
      <span class="tl-card-num">#${index+1}</span>
      <span class="tl-card-action">${method}</span>
      <span class="tl-card-id">${step.id}</span>
    </div>
  </div>
  ${params     ? `<div class="tl-card-params">${params}</div>` : ''}
  ${outputLine ? `<div class="tl-card-output">${outputLine}</div>` : ''}
  ${noteLine   ? `<div class="tl-card-note">${noteLine}</div>` : ''}
  <div class="tl-card-timing" id="tl-timing-${step.id}"></div>
</div>${connector}`;
}

/** Render both timelines (tab + canvas overlay) */
window.renderTimeline = function(flow) {
  const empty       = document.getElementById('timeline-empty');
  const stepsTab    = document.getElementById('timeline-steps');
  const stepsCanvas = document.getElementById('canvas-timeline-steps');
  const trackWrap   = document.getElementById('tl-tab-track-wrap');

  _tlFlowName = flow?.name || '';
  if (typeof _tlUpdateHeaders === 'function') _tlUpdateHeaders({ name: _tlFlowName, steps: flow?.pipeline?.length||0, status:'idle' });

  if (!flow || !flow.pipeline?.length) {
    if (empty)     empty.style.display = 'flex';
    if (trackWrap) trackWrap.style.display = 'none';
    if (stepsCanvas) stepsCanvas.innerHTML = '';
    if (stepsTab)    stepsTab.innerHTML = '';
    _tlBuildRuler(0);
    return;
  }

  if (empty)     empty.style.display = 'none';
  if (trackWrap) trackWrap.style.display = 'flex';

  const total = flow.pipeline.length;
  const html  = flow.pipeline.map((s,i) => _tlNodeCard(s, i, total)).join('');
  if (stepsTab)    stepsTab.innerHTML    = html;
  if (stepsCanvas) stepsCanvas.innerHTML = html;
  _tlBuildRuler(total);
};

/** Draw ruler ticks on both rulers */
function _tlBuildRuler(stepCount) {
  ['ttl-ruler','ctl-ruler'].forEach(id => {
    const ruler = document.getElementById(id);
    if (!ruler) return;
    ruler.querySelectorAll('.tl-ruler-tick').forEach(t => t.remove());
    if (stepCount <= 0) return;
    const ticks = Math.min(stepCount * 2, 40);
    for (let i=0; i<=ticks; i++) {
      const major = i % 4 === 0;
      const tick  = document.createElement('div');
      tick.className = `tl-ruler-tick tl-ruler-tick-${major?'major':'minor'}`;
      tick.style.left = `${(i/ticks)*100}%`;
      const line = document.createElement('div'); line.className='tl-ruler-line'; tick.appendChild(line);
      if (major) {
        const lbl = document.createElement('span'); lbl.className='tl-ruler-label';
        lbl.textContent = `${(i*0.5).toFixed(1)}s`; tick.appendChild(lbl);
      }
      ruler.appendChild(tick);
    }
  });
}

function _tlSetPlayhead(fraction) {
  ['ttl-playhead','ctl-playhead'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.left = `${Math.min(1,fraction)*100}%`;
  });
}

/** Open node editor from a timeline card click */
window.tlOpenNodeEditor = function(stepId) {
  if (typeof window._hcEditNode === 'function') { window._hcEditNode(stepId); return; }
  window.dispatchEvent(new CustomEvent('hecos-timeline-select-node', { detail: { id: stepId } }));
};

/** Update header info bars (both timelines) */
window._tlUpdateHeaders = function({ name, steps, status, currentStep, duration }) {
  const sets = [
    { name:'ttl-flow-name', count:'ttl-step-count', dur:'ttl-duration', stat:'ttl-status', cur:'ttl-current-step' },
    { name:'ctl-flow-name', count:'ctl-step-count', dur:'ctl-duration', stat:'ctl-status', cur:null },
  ];
  sets.forEach(s => {
    const n  = document.getElementById(s.name);
    const c  = document.getElementById(s.count);
    const d  = document.getElementById(s.dur);
    const st = document.getElementById(s.stat);
    const cu = s.cur ? document.getElementById(s.cur) : null;
    if (n  && name      !==undefined) n.textContent  = name||'—';
    if (c  && steps     !==undefined) c.textContent  = steps;
    if (d  && duration  !==undefined) d.textContent  = duration;
    if (cu && currentStep!==undefined) cu.innerHTML = currentStep ? `<i class="fas fa-bolt" style="color:var(--flows-accent);"></i> ${currentStep}` : '';
    if (st && status    !==undefined) {
      const m = { idle:{i:'fa-circle',c:'var(--flows-muted)',l:'idle'}, running:{i:'fa-spinner fa-spin',c:'var(--flows-accent)',l:'running'}, done:{i:'fa-check-circle',c:'var(--flows-success)',l:'done'}, error:{i:'fa-times-circle',c:'var(--flows-danger)',l:'error'} };
      const v = m[status]||m.idle;
      st.innerHTML = `<i class="fas ${v.i}" style="color:${v.c}"></i> ${v.l}`;
    }
  });
};

/** Highlight a node in both timelines and scroll to center it */
window.setTimelineNodeState = function(stepId, state) {
  ['timeline-steps','canvas-timeline-steps'].forEach(cid => {
    const cont = document.getElementById(cid);
    if (!cont) return;
    const card = cont.querySelector(`.tl-node-card[data-step-id="${stepId}"]`);
    if (!card) return;
    card.classList.remove('running','done','error');
    if (state) card.classList.add(state);
    if (state==='running') card.scrollIntoView({ behavior:'smooth', block:'nearest', inline:'center' });
  });

  if (state==='running') {
    const start = Date.now();
    const ticker = setInterval(() => {
      const ms = Date.now()-start;
      document.querySelectorAll(`#tl-timing-${stepId}`).forEach(el => {
        el.textContent = `${(ms/1000).toFixed(2)}s`;
        el.className='tl-card-timing active';
      });
      if (!document.querySelector(`.tl-node-card[data-step-id="${stepId}"].running`)) clearInterval(ticker);
    }, 80);
  } else if (state==='done'||state==='error') {
    document.querySelectorAll(`#tl-timing-${stepId}`).forEach(el => { el.className='tl-card-timing'; });
  }
};

/** Reset all cards to neutral */
window.resetTimelineNodeStates = function() {
  document.querySelectorAll('.tl-node-card').forEach(c => c.classList.remove('running','done','error'));
  document.querySelectorAll('.tl-card-timing').forEach(el => { el.textContent=''; el.className='tl-card-timing'; });
  _tlSetPlayhead(0);
  if (typeof _tlUpdateHeaders === 'function') _tlUpdateHeaders({ status:'idle', currentStep:'', duration:'0.0s' });
  if (_tlDurationTimer) { clearInterval(_tlDurationTimer); _tlDurationTimer=null; }
  _tlRunStartTs=null;
};

/** Start live stopwatch */
window.startTimelineRun = function(flowName, stepCount) {
  _tlRunStartTs=Date.now();
  if (typeof _tlUpdateHeaders === 'function') _tlUpdateHeaders({ name:flowName||_tlFlowName, steps:stepCount, status:'running', currentStep:'', duration:'0.0s' });
  if (_tlDurationTimer) clearInterval(_tlDurationTimer);
  _tlDurationTimer=setInterval(() => {
    const ms=Date.now()-_tlRunStartTs;
    if (typeof _tlUpdateHeaders === 'function') _tlUpdateHeaders({ duration:`${(ms/1000).toFixed(1)}s` });
    _tlSetPlayhead(Math.min(ms/((stepCount||1)*1500), 0.95));
  }, 100);
};

/** Finish run */
window.finishTimelineRun = function(status) {
  if (_tlDurationTimer) { clearInterval(_tlDurationTimer); _tlDurationTimer=null; }
  const ms=_tlRunStartTs?Date.now()-_tlRunStartTs:0;
  if (typeof _tlUpdateHeaders === 'function') _tlUpdateHeaders({ status, currentStep:'', duration:ms>0?`${(ms/1000).toFixed(2)}s`:'—' });
  _tlSetPlayhead(status==='done'?1:0.5);
};
