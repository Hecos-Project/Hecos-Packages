// ── Init LiteGraph ────────────────────────────────────────────────

// Global step-id → LiteGraph node map (populated on each canvas render)
let _nodeMap = {};
let _nodeOrigColors = {};  // step_id → { color, bgcolor }

// Node state colours
const NODE_STATE_COLORS = {
  running: { color: '#0e7490', bgcolor: '#164e63' },  // cyan
  done:    { color: '#15803d', bgcolor: '#14532d' },  // green
  error:   { color: '#b91c1c', bgcolor: '#7f1d1d' },  // red
};

let _blinkInterval = null;

function initCanvas() {
  const cv = document.getElementById('flows-canvas');
  if(!cv) return;
  lgraph = new LGraph();
  lgcanvas = new LGraphCanvas('#flows-canvas', lgraph);
  lgcanvas.background_image = null;
  lgcanvas.render_canvas_border = false;
  lgcanvas.render_connections_border = false;
  lgcanvas.default_link_color = '#00d4ff55';

  // Register node types
  _registerNodeTypes();

  // Resize canvas to container
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);

  // Selection change handler for toolbar delete button
  lgcanvas.onSelectionChange = (nodes) => {
    const btn = document.getElementById('btn-delete-node');
    if (!btn) return;
    const hasSelection = nodes && Object.keys(nodes).length > 0;
    btn.style.display = hasSelection ? 'inline-block' : 'none';
  };
  // Node Editor hook
  lgcanvas.onNodeDblClicked = (node) => {
    if (typeof openNodeEditor === 'function') openNodeEditor(node);
  };

  // ── Override LiteGraph's internal deleteSelectedNodes ──────────────
  // This is called by LiteGraph's OWN keyboard handler (bound at canvas
  // creation time, so processKey overrides don't reach it).
  // By replacing this method on the instance we intercept ALL three paths:
  //   1. Delete / Backspace key  (LiteGraph calls this internally)
  //   2. Context-menu → "Remove" (LiteGraph also calls this)
  //   3. Toolbar "Delete Node" button (calls our global wrapper below)
  // ── Override LiteGraph's internal deleteSelectedNodes ──────────────
  let _deleteInProgress = false;
  lgcanvas.deleteSelectedNodes = function() {
    if (_deleteInProgress) return;
    const nodesToDelete = Object.values(this.selected_nodes || {});
    if (!nodesToDelete.length) return;

    _deleteInProgress = true;
    try {
      nodesToDelete.forEach(node => {
        this.graph.remove(node);
        delete _nodeMap[node.title];
      });
      if (typeof this.deselectAllNodes === 'function') {
        this.deselectAllNodes();
      } else {
        this.selected_nodes = {};
      }
      this.draw(true, true);
      if (typeof syncCanvasToYaml === 'function') syncCanvasToYaml();
      if (typeof toast === 'function') toast('ok', `🗑️ ${nodesToDelete.length} node(s) deleted`);
    } finally {
      _deleteInProgress = false;
    }
  };

  // Canvas global keyboard shortcut (enables deletion even when canvas loses focus)
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Delete' && e.key !== 'Backspace' && e.keyCode !== 46 && e.keyCode !== 8) return;
    const active = document.activeElement;
    if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable)) return;
    
    const canvasTab = document.getElementById('tab-canvas');
    if (canvasTab && canvasTab.classList.contains('active')) {
      if (typeof deleteSelectedNodes === 'function') deleteSelectedNodes();
      e.preventDefault();
    }
  }, true);
}


function resizeCanvas() {
  const wrap = document.getElementById('canvas-wrap');
  const cv = document.getElementById('flows-canvas');
  if (!wrap || !cv) return;
  cv.width = wrap.clientWidth;
  cv.height = wrap.clientHeight;
  if (lgcanvas) lgcanvas.resize();
}

// ── Node type definitions ─────────────────────────────────────────
function _registerNodeTypes() {
  if (typeof LiteGraph === 'undefined') return;
  const types = [
    { type:'hecos/trigger',  title:'TRIGGER',   color:'#4c1d95', labelColor:'#c4b5fd' },
    { type:'hecos/action',   title:'ACTION',    color:'#0c4a6e', labelColor:'#7dd3fc' },
    { type:'hecos/if_else',  title:'IF / ELSE', color:'#78350f', labelColor:'#fcd34d' },
    { type:'hecos/loop',     title:'LOOP',      color:'#064e3b', labelColor:'#6ee7b7' },
    { type:'hecos/delay',    title:'DELAY',     color:'#1e1b4b', labelColor:'#a5b4fc' },
    { type:'hecos/speak',    title:'SPEAK',     color:'#134e4a', labelColor:'#5eead4' },
    { type:'hecos/http',     title:'HTTP REQ',  color:'#172554', labelColor:'#93c5fd' },
    { type:'hecos/variable', title:'VARIABLE',  color:'#3f3f46', labelColor:'#d4d4d8' },
  ];
  types.forEach(t => {
    function Node() {
      this.addOutput('out', 'flow');
      this.addInput('in', 'flow');
      this.title = t.title;
      this.size = [200, 80];
      this.bgcolor = t.color;
      this.properties = { note: "" };
      this.addWidget("text", "Note", "", (v) => { this.properties.note = v; });
    }
    Node.title = t.title;
    Node.title_color = t.labelColor || '#fff';
    LiteGraph.registerNodeType(t.type, Node);
  });
}

// ── Canvas renderer ───────────────────────────────────────────────
function renderCanvasFromFlow(flow) {
  if (!lgraph || typeof LiteGraph === 'undefined') return;
  lgraph.clear();
  const steps = flow.pipeline || [];
  const posMap = {};
  let x = 80, y = 80;
  
  steps.forEach((step, i) => {
    const action = step.action || '';
    let nodeType = 'hecos/action';
    if (action.startsWith('LOGIC__if')) nodeType = 'hecos/if_else';
    else if (action.startsWith('LOGIC__loop')) nodeType = 'hecos/loop';
    else if (action.startsWith('LOGIC__delay')) nodeType = 'hecos/delay';
    else if (action.startsWith('LOGIC__set_var')) nodeType = 'hecos/variable';
    else if (action.startsWith('AUDIO__speak')) nodeType = 'hecos/speak';
    else if (action.startsWith('LOGIC__http')) nodeType = 'hecos/http';
    else if (action.startsWith('TRIGGER__')) nodeType = 'hecos/trigger';

    const node = LiteGraph.createNode(nodeType);
    if(node) {
      node.title = step.id;
      node.pos = [x + (i % 3) * 250, y + Math.floor(i/3) * 120];
      node.properties = { action, params: JSON.stringify(step.params||{}), output_as: step.output_as||'', note: step.note||'' };
      if(step.note) node.widgets[0].value = step.note;
      posMap[step.id] = node;
      lgraph.add(node);
    }
  });

  // Wire depends_on connections
  steps.forEach(step => {
    const deps = step.depends_on || [];
    deps.forEach(dep => {
      const src = posMap[dep];
      const dst = posMap[step.id];
      if (src && dst) src.connect(0, dst, 0);
    });
  });

  // Expose node map for state tracking
  _nodeMap = posMap;
  _nodeOrigColors = {};
  Object.entries(posMap).forEach(([id, n]) => {
    _nodeOrigColors[id] = { color: n.color, bgcolor: n.bgcolor };
  });

  if (lgcanvas) lgcanvas.draw(true, true);
}

// ── Node execution state ─────────────────────────────────────────
function setNodeState(stepId, state) {
  const node = _nodeMap[stepId];
  if (!node || typeof LiteGraph === 'undefined') return;

  const colors = NODE_STATE_COLORS[state];
  if (!colors) return;

  node.color   = colors.color;
  node.bgcolor = colors.bgcolor;

  // Pulsing outline for 'running' via boxcolor animation
  if (state === 'running') {
    node.boxcolor = '#00d4ff';
    let bright = true;
    if (_blinkInterval) clearInterval(_blinkInterval);
    _blinkInterval = setInterval(() => {
      if (!_nodeMap[stepId]) { clearInterval(_blinkInterval); return; }
      node.boxcolor = bright ? '#00d4ff' : '#00d4ff44';
      bright = !bright;
      if (lgcanvas) lgcanvas.draw(true, true);
    }, 420);
  } else {
    if (_blinkInterval) { clearInterval(_blinkInterval); _blinkInterval = null; }
    node.boxcolor = state === 'done' ? '#22c55e' : '#ef4444';
  }

  if (lgcanvas) lgcanvas.draw(true, true);
}

function resetNodeStates() {
  if (_blinkInterval) { clearInterval(_blinkInterval); _blinkInterval = null; }
  Object.entries(_nodeMap).forEach(([id, node]) => {
    const orig = _nodeOrigColors[id];
    if (orig) {
      node.color   = orig.color;
      node.bgcolor = orig.bgcolor;
    }
    node.boxcolor = null;
  });
  if (lgcanvas) lgcanvas.draw(true, true);
}

// ── Node Actions ──────────────────────────────────────────────────────────────

// Global wrapper for toolbar button — delegates to the overridden canvas method
function deleteSelectedNodes() {
  if (lgcanvas && typeof lgcanvas.deleteSelectedNodes === 'function') {
    lgcanvas.deleteSelectedNodes();
  }
}


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

  const params = Object.entries(step.params || {}).slice(0,3)
    .map(([k,v]) => { const val = typeof v==='string'?v:JSON.stringify(v); return `${k}: ${val.length>18?val.slice(0,18)+'...':val}`; })
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
function renderTimeline(flow) {
  const empty       = document.getElementById('timeline-empty');
  const stepsTab    = document.getElementById('timeline-steps');
  const stepsCanvas = document.getElementById('canvas-timeline-steps');
  const trackWrap   = document.getElementById('tl-tab-track-wrap');

  _tlFlowName = flow?.name || '';
  _tlUpdateHeaders({ name: _tlFlowName, steps: flow?.pipeline?.length||0, status:'idle' });

  if (!flow || !flow.pipeline?.length) {
    if (empty)     empty.style.display = 'flex';
    if (trackWrap) trackWrap.style.display = 'none';
    if (stepsCanvas) stepsCanvas.innerHTML = '';
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
}

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
function tlOpenNodeEditor(stepId) {
  if (typeof window._hcEditNode === 'function') { window._hcEditNode(stepId); return; }
  window.dispatchEvent(new CustomEvent('hecos-timeline-select-node', { detail: { id: stepId } }));
}

/** Update header info bars (both timelines) */
function _tlUpdateHeaders({ name, steps, status, currentStep, duration }) {
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
    if (cu && currentStep!==undefined) cu.textContent = currentStep ? `&#9889; ${currentStep}` : '';
    if (st && status    !==undefined) {
      const m = { idle:{i:'fa-circle',c:'var(--flows-muted)',l:'idle'}, running:{i:'fa-spinner fa-spin',c:'var(--flows-accent)',l:'running'}, done:{i:'fa-check-circle',c:'var(--flows-success)',l:'done'}, error:{i:'fa-times-circle',c:'var(--flows-danger)',l:'error'} };
      const v = m[status]||m.idle;
      st.innerHTML = `<i class="fas ${v.i}" style="color:${v.c}"></i> ${v.l}`;
    }
  });
}

/** Highlight a node in both timelines and scroll to center it */
function setTimelineNodeState(stepId, state) {
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
}

/** Reset all cards to neutral */
function resetTimelineNodeStates() {
  document.querySelectorAll('.tl-node-card').forEach(c => c.classList.remove('running','done','error'));
  document.querySelectorAll('.tl-card-timing').forEach(el => { el.textContent=''; el.className='tl-card-timing'; });
  _tlSetPlayhead(0);
  _tlUpdateHeaders({ status:'idle', currentStep:'', duration:'0.0s' });
  if (_tlDurationTimer) { clearInterval(_tlDurationTimer); _tlDurationTimer=null; }
  _tlRunStartTs=null;
}

/** Start live stopwatch */
function startTimelineRun(flowName, stepCount) {
  _tlRunStartTs=Date.now();
  _tlUpdateHeaders({ name:flowName||_tlFlowName, steps:stepCount, status:'running', currentStep:'', duration:'0.0s' });
  if (_tlDurationTimer) clearInterval(_tlDurationTimer);
  _tlDurationTimer=setInterval(() => {
    const ms=Date.now()-_tlRunStartTs;
    _tlUpdateHeaders({ duration:`${(ms/1000).toFixed(1)}s` });
    _tlSetPlayhead(Math.min(ms/((stepCount||1)*1500), 0.95));
  }, 100);
}

/** Finish run */
function finishTimelineRun(status) {
  if (_tlDurationTimer) { clearInterval(_tlDurationTimer); _tlDurationTimer=null; }
  const ms=_tlRunStartTs?Date.now()-_tlRunStartTs:0;
  _tlUpdateHeaders({ status, currentStep:'', duration:ms>0?`${(ms/1000).toFixed(2)}s`:'—' });
  _tlSetPlayhead(status==='done'?1:0.5);
}
