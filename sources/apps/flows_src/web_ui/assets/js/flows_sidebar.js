// ── Flows Sidebar & Settings ────────────────────────────────────
// ── Sidebar order persistence ─────────────────────────────────────
const FLOWS_ORDER_KEY = 'hecos_flows_order';

function getSavedOrder() {
  try { return JSON.parse(localStorage.getItem(FLOWS_ORDER_KEY)) || []; }
  catch { return []; }
}

function saveOrder(ids) {
  localStorage.setItem(FLOWS_ORDER_KEY, JSON.stringify(ids));
}

function sortFlowsByOrder(flows) {
  const order = getSavedOrder();
  if (!order.length) return flows;
  const ranked = [];
  const remaining = [...flows];
  order.forEach(id => {
    const idx = remaining.findIndex(f => f.id === id);
    if (idx !== -1) ranked.push(remaining.splice(idx, 1)[0]);
  });
  return [...ranked, ...remaining]; // unseen flows go to end
}

let _sidebarViewMode = localStorage.getItem('flows_sidebar_view') || 'compact';

window.toggleSidebarViewMode = function() {
  _sidebarViewMode = _sidebarViewMode === 'compact' ? 'detailed' : 'compact';
  localStorage.setItem('flows_sidebar_view', _sidebarViewMode);
  renderSidebar(_allFlows);
};

async function loadFlowsList() {
  try {
    const res = await fetch('/api/flows/list');
    const d = await res.json();
    if (!d.ok) throw new Error(d.error);
    _allFlows = d.flows || [];
    renderSidebar(_allFlows);
  } catch(e) { toast('error','Could not load flows: '+e.message); }
}

function renderSidebar(flows) {
  const list = document.getElementById('flows-list');
  const empty = document.getElementById('flows-sidebar-empty');
  if(!list) return;
  
  // Rimuove i gruppi e gli item per non distruggere l'elemento "empty" dal DOM
  list.querySelectorAll('.flow-item, .flow-group').forEach(el => el.remove());

  const viewToggleBtn = document.getElementById('btn-flows-view-toggle');
  if (viewToggleBtn) {
    viewToggleBtn.innerHTML = _sidebarViewMode === 'compact' ? '<i class="fas fa-th-list"></i>' : '<i class="fas fa-list"></i>';
  }

  if (!flows.length && _allFlows.length === 0) {
    if(empty) empty.style.display='flex';
    return;
  }
  if(empty) empty.style.display = 'none';

  // Apply sorting
  let sorted = [...flows];
  const sortSelect = document.getElementById('flows-sort-order');
  const sortMode = sortSelect ? sortSelect.value : 'custom';
  
  if (sortMode === 'custom') {
    sorted = sortFlowsByOrder(sorted);
  } else if (sortMode === 'name') {
    sorted.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  } else if (sortMode === 'updated') {
    sorted.sort((a, b) => new Date(b.updated_at || b.created_at || 0) - new Date(a.updated_at || a.created_at || 0));
  } else if (sortMode === 'created') {
    sorted.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
  } else if (sortMode === 'last_run_desc') {
    sorted.sort((a, b) => new Date(b.last_run || 0) - new Date(a.last_run || 0));
  } else if (sortMode === 'last_run_asc') {
    sorted.sort((a, b) => {
      const ta = a.last_run ? new Date(a.last_run).getTime() : Infinity;
      const tb = b.last_run ? new Date(b.last_run).getTime() : Infinity;
      return ta - tb;
    });
  } else if (sortMode === 'never_run') {
    sorted = sorted.filter(f => !f.last_run).concat(sorted.filter(f => !!f.last_run));
  }

  // Populate tags filter
  const tagFilter = document.getElementById('flows-tag-filter');
  if (tagFilter && flows === _allFlows) {
    const currentVal = tagFilter.value;
    const allTags = new Set();
    _allFlows.forEach(f => (f.tags || []).forEach(t => allTags.add(t)));
    tagFilter.innerHTML = '<option value="">All Tags</option>';
    Array.from(allTags).sort().forEach(tag => {
      tagFilter.innerHTML += `<option value="${tag}">${tag}</option>`;
    });
    tagFilter.value = currentVal;
  }

  // Group by folder
  const groups = {};
  sorted.forEach(f => {
    const g = f.group || "General";
    if (!groups[g]) groups[g] = [];
    groups[g].push(f);
  });

  Object.keys(groups).sort().forEach(gName => {
    const groupContainer = document.createElement('details');
    groupContainer.className = 'flow-group';
    groupContainer.open = true;
    groupContainer.style.marginBottom = '6px';
    
    const summary = document.createElement('summary');
    summary.style.cursor = 'pointer';
    summary.style.padding = '6px 12px';
    summary.style.background = 'rgba(255,255,255,0.05)';
    summary.style.color = 'var(--flows-text-muted)';
    summary.style.fontWeight = '600';
    summary.style.fontSize = '0.85rem';
    summary.style.userSelect = 'none';
    summary.innerHTML = `<i class="fas fa-folder-open" style="margin-right:6px;color:var(--flows-accent);"></i> ${gName} <span style="font-size: 0.75rem; color: var(--flows-text-muted); opacity: 0.7; margin-left: 4px;">(${groups[gName].length})</span>`;
    groupContainer.appendChild(summary);

    const groupList = document.createElement('div');
    groupList.className = 'flow-group-list';
    groupList.style.paddingLeft = '10px';
    groupList.style.marginTop = '4px';
    groupList.style.display = 'flex';
    groupList.style.flexDirection = 'column';
    groupList.style.gap = '4px';

    groups[gName].forEach(f => {
      const el = document.createElement('div');
      el.className = 'flow-item' + (f.id === currentFlowId ? ' active' : '');
      el.dataset.id = f.id;
      el.dataset.enabled = f.enabled ? 'true' : 'false';
      el.draggable = true;
      const tooltip = [
        f.description ? f.description : null,
        `Trigger: ${f.trigger_type}${f.trigger_expr?' ('+f.trigger_expr+')':''}`,
        `Steps: ${f.step_count}`,
        `Tags: ${(f.tags && f.tags.length) ? f.tags.join(', ') : 'None'}`,
        `Last Run: ${f.last_run ? new Date(f.last_run).toLocaleString() : 'Never'}`
      ].filter(x=>x).join('\n');
      
      el.title = tooltip;
      if (_sidebarViewMode === 'compact') {
        el.innerHTML = `
          <div style="display:flex; align-items:center; width:100%; gap:.4rem; min-width:0; overflow:hidden;">
            <span class="flow-drag-handle" style="cursor:grab; opacity:0.4; font-size:.8rem; flex-shrink:0;">⠿</span>
            <span class="flow-status-indicator ${f.enabled ? 'enabled' : 'disabled'}" style="flex-shrink:0;"></span>
            <span class="flow-item-name--compact" onmouseenter="(function(el){const inner=el.querySelector('span');if(inner){const overflow=inner.scrollWidth-el.offsetWidth;el.style.setProperty('--hc-overflow',(-Math.max(overflow,0)-8)+'px');}})(this)"><span>${f.name}</span></span>
            <div style="display:flex; align-items:center; margin-left:4px; position:relative; flex-shrink:0; min-width:60px; justify-content:flex-end;">
              <span class="flow-run-text-status flow-run-text-status-compact" style="color:var(--flows-success);">Stopped</span>
              <button class="flow-item-toggle compact-btn" data-flow-id="${f.id}" data-enabled="${f.enabled ? 'true' : 'false'}">
                <i class="fas ${f.enabled ? 'fa-toggle-on' : 'fa-toggle-off'}"></i>
              </button>
              <button class="flow-item-del compact-btn" data-flow-id="${f.id}"><i class="fas fa-trash"></i></button>
            </div>
          </div>`;
      } else {
        el.innerHTML = `
          <span class="flow-drag-handle" title="${window.t('flows_drag_to_reorder')}">⠿</span>
          <div class="flow-item-name">
            <span class="flow-status-indicator ${f.enabled ? 'enabled' : 'disabled'}"></span>
            ${f.name}
          </div>
          <div class="flow-item-meta" style="flex-wrap:wrap; margin-top:2px;">
            <span><i class="fas fa-bolt" style="font-size:.6rem"></i> ${f.trigger_type}${f.trigger_expr?' ('+f.trigger_expr+')':''}</span>
            <span>${f.step_count} steps</span>
            <span>${f.last_run ? '<i class="fas fa-history" style="font-size:.6rem; color:var(--flows-accent);"></i>' : '<i class="fas fa-minus-circle" style="font-size:.6rem; color:var(--flows-muted);"></i>'} ${f.last_run ? new Date(f.last_run).toLocaleString() : 'Never'}</span>
            <span class="flow-run-text-status" style="font-weight:700; font-size:0.6rem; color:var(--flows-success); text-transform:uppercase;">Stopped</span>
            ${(f.tags && f.tags.length > 0) ? `<span style="color:var(--flows-accent); font-size:0.6rem;">[${f.tags.join(', ')}]</span>` : ''}
            <button class="flow-item-toggle" title="${f.enabled ? 'Disable flow' : 'Enable flow'}" data-flow-id="${f.id}" data-enabled="${f.enabled ? 'true' : 'false'}">
              <i class="fas ${f.enabled ? 'fa-toggle-on' : 'fa-toggle-off'}"></i>
            </button>
            <button class="flow-item-del" title="${window.t('flows_delete_flow')}" data-flow-id="${f.id}"><i class="fas fa-trash"></i></button>
          </div>`;
      }
      el.querySelector('.flow-item-del').addEventListener('click', e => {
        e.stopPropagation();
        deleteFlowById(f.id, f.name);
      });
      el.querySelector('.flow-item-toggle').addEventListener('click', async e => {
        e.stopPropagation();
        const btn = e.currentTarget;
        const flowId = btn.dataset.flowId;
        const isEnabled = btn.dataset.enabled === 'true';
        const action = isEnabled ? 'disable' : 'enable';
        btn.style.opacity = '0.4';
        try {
          const r = await fetch(`/api/flows/${flowId}/${action}`, { method: 'POST' });
          const d = await r.json();
          if (!d.ok) throw new Error(d.error);
          // Update local _allFlows state
          const flowObj = _allFlows.find(x => x.id === flowId);
          if (flowObj) flowObj.enabled = !isEnabled;
          // Update DOM directly without full reload
          btn.dataset.enabled = isEnabled ? 'false' : 'true';
          btn.title = isEnabled ? 'Enable flow' : 'Disable flow';
          btn.querySelector('i').className = `fas ${isEnabled ? 'fa-toggle-off' : 'fa-toggle-on'}`;
          const indicator = el.querySelector('.flow-status-indicator');
          indicator.className = `flow-status-indicator ${isEnabled ? 'disabled' : 'enabled'}`;
          el.dataset.enabled = isEnabled ? 'false' : 'true';
          toast('success', `Flow ${isEnabled ? 'disabled' : 'enabled'}.`);
        } catch(err) {
          toast('error', 'Could not toggle flow: ' + err.message);
        } finally {
          btn.style.opacity = '1';
        }
      });
      el.addEventListener('click', e => {
        if (e.target.closest('.flow-drag-handle') || e.target.closest('.flow-item-del') || e.target.closest('.flow-item-toggle')) return;
        selectFlow(f.id);
      });
      groupList.appendChild(el);
    });
    groupContainer.appendChild(groupList);
    list.appendChild(groupContainer);
  });

  // Re-apply current running state on the new DOM
  _applyRunningBadges(_lastKnownRunning);

  initSidebarDragSort();
}

function filterFlowsList() {
  const query = (document.getElementById('flows-search-input')?.value || '').toLowerCase();
  const tag = document.getElementById('flows-tag-filter')?.value || '';
  
  let filtered = _allFlows.filter(f => {
    const matchQuery = !query || (f.name && f.name.toLowerCase().includes(query)) || (f.id && f.id.toLowerCase().includes(query));
    const matchTag = !tag || (f.tags && f.tags.includes(tag));
    return matchQuery && matchTag;
  });
  renderSidebar(filtered);
}

// ── Sidebar drag-to-reorder ───────────────────────────────────────
function initSidebarDragSort() {
  const list = document.getElementById('flows-list');
  if (!list) return;

  let dragSrc = null;

  list.querySelectorAll('.flow-item[draggable]').forEach(item => {
    item.addEventListener('dragstart', e => {
      dragSrc = item;
      item.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', item.dataset.id);
    });

    item.addEventListener('dragend', () => {
      item.classList.remove('dragging');
      list.querySelectorAll('.flow-item').forEach(el => {
        el.classList.remove('drag-over-top', 'drag-over-bottom');
      });
      dragSrc = null;
      // Save the new order
      const ids = [...list.querySelectorAll('.flow-item[data-id]')].map(el => el.dataset.id);
      saveOrder(ids);
    });

    item.addEventListener('dragover', e => {
      e.preventDefault();
      if (!dragSrc || dragSrc === item) return;
      e.dataTransfer.dropEffect = 'move';
      list.querySelectorAll('.flow-item').forEach(el => {
        el.classList.remove('drag-over-top', 'drag-over-bottom');
      });
      const rect = item.getBoundingClientRect();
      const mid  = rect.top + rect.height / 2;
      if (e.clientY < mid) {
        item.classList.add('drag-over-top');
      } else {
        item.classList.add('drag-over-bottom');
      }
    });

    item.addEventListener('dragleave', () => {
      item.classList.remove('drag-over-top', 'drag-over-bottom');
    });

    item.addEventListener('drop', e => {
      e.preventDefault();
      if (!dragSrc || dragSrc === item) return;
      const rect = item.getBoundingClientRect();
      const mid  = rect.top + rect.height / 2;
      if (e.clientY < mid) {
        list.insertBefore(dragSrc, item);
      } else {
        item.after(dragSrc);
      }
      item.classList.remove('drag-over-top', 'drag-over-bottom');
    });
  });
}

// ── Flow Settings (Modal) ─────────────────────────────────────────

function openFlowSettings() {
  if (!currentFlowId) return;
  const flow = _allFlows.find(f => f.id === currentFlowId);
  if (!flow) return;
  document.getElementById('fs-name').value = flow.name || '';
  document.getElementById('fs-group').value = flow.group || '';
  document.getElementById('fs-tags').value = (flow.tags || []).join(', ');
  document.getElementById('fs-description').value = flow.description || '';
  document.getElementById('modal-flow-settings').classList.add('open');
}

function closeFlowSettings() {
  const modal = document.getElementById('modal-flow-settings');
  if (modal) modal.classList.remove('open');
}

function saveFlowSettings() {
  if (!currentFlowId) return;
  const newName = document.getElementById('fs-name').value.trim();
  const newGroup = document.getElementById('fs-group').value.trim();
  const newTags = document.getElementById('fs-tags').value.split(',').map(t => t.trim()).filter(t => t);
  const newDesc = document.getElementById('fs-description').value.trim();

  if (typeof syncCanvasToYaml === 'function') syncCanvasToYaml();
  if (!cmEditor) { toast('error', 'Editor not ready.'); return; }

  let yamlStr = cmEditor.getValue();
  try {
    const flowObj = jsyaml.load(yamlStr) || {};
    if (newName) flowObj.name = newName;
    if (newGroup) flowObj.group = newGroup; else delete flowObj.group;
    if (newTags.length > 0) flowObj.tags = newTags; else delete flowObj.tags;
    if (newDesc) flowObj.description = newDesc; else delete flowObj.description;
    yamlStr = jsyaml.dump(flowObj, { indent: 2, lineWidth: -1 });
    cmEditor.setValue(yamlStr);
    closeFlowSettings();
    saveCurrentFlow(false);
  } catch(e) {
    toast('error', 'Could not apply settings: ' + e.message);
  }
}
