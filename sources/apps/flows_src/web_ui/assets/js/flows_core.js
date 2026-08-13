// ── State ────────────────────────────────────────────────────────
let currentFlowId = null;
let currentFlowData = null;
let compiledYaml = null;
let lgraph = null;
let lgcanvas = null;
let cmEditor = null;
let sseSource = null;
let mediaRecorder = null;
let isRecording = false;

// ── Shared Utils ──────────────────────────────────────────────────
function debounce(fn, ms) {
  let t; return (...args) => { clearTimeout(t); t=setTimeout(()=>fn(...args),ms); };
}

// ── Toast ─────────────────────────────────────────────────────────
function toast(type, msg) {
  const icon = type==='ok'?'fa-check-circle':type==='error'?'fa-times-circle':'fa-info-circle';
  const el = document.createElement('div');
  el.className=`toast-item ${type}`;
  el.innerHTML=`<i class="fas ${icon}"></i><span>${msg}</span>`;
  document.getElementById('flows-toast').appendChild(el);
  setTimeout(()=>el.remove(), 4000);
}

// ── Overlay Panels (Canvas) ───────────────────────────────────────
window.toggleLogPanel = function() {
  const p = document.getElementById('canvas-log-panel');
  if (p) {
    p.classList.toggle('closed');
    const btn = document.getElementById('btn-toggle-log');
    if (btn) btn.style.background = p.classList.contains('closed') ? '' : 'rgba(255,255,255,0.15)';
  }
};
window.openLogPanel = function() {
  const p = document.getElementById('canvas-log-panel');
  if (p) {
    p.classList.remove('closed');
    const btn = document.getElementById('btn-toggle-log');
    if (btn) btn.style.background = 'rgba(255,255,255,0.15)';
  }
};

window.toggleTimelinePanel = function() {
  const p = document.getElementById('canvas-timeline-panel');
  if (p) {
    p.classList.toggle('closed');
    const btn = document.getElementById('btn-toggle-timeline');
    if (btn) btn.style.background = p.classList.contains('closed') ? '' : 'rgba(255,255,255,0.15)';
  }
};
window.openTimelinePanel = function() {
  const p = document.getElementById('canvas-timeline-panel');
  if (p) {
    p.classList.remove('closed');
    const btn = document.getElementById('btn-toggle-timeline');
    if (btn) btn.style.background = 'rgba(255,255,255,0.15)';
  }
};

window.setInteractionMode = function(mode) {
  const btnSelect = document.getElementById('btn-mode-select');
  const btnHand = document.getElementById('btn-mode-hand');
  if (mode === 'select') {
    if (btnSelect) { btnSelect.classList.add('active'); btnSelect.style.color = 'var(--flows-accent)'; }
    if (btnHand) { btnHand.classList.remove('active'); btnHand.style.color = ''; }
  } else {
    if (btnHand) { btnHand.classList.add('active'); btnHand.style.color = 'var(--flows-accent)'; }
    if (btnSelect) { btnSelect.classList.remove('active'); btnSelect.style.color = ''; }
  }
  
  // Call React bridge
  if (window.HecosFlowsBridge && typeof window.HecosFlowsBridge.setInteractionMode === 'function') {
    window.HecosFlowsBridge.setInteractionMode(mode);
  }
};

window.resetOverlayPosition = function(id) {
  const p = document.getElementById(id);
  if (p) {
    p.style.left = '';
    p.style.top = '';
    p.style.right = '';
    p.style.bottom = '';
    p.style.width = '';
    p.style.height = '';
  }
};

// ── Overlay Dragging & Z-Index ────────────────────────────────────
function initOverlaysInteraction() {
  let highestZ = 9000;
  
  document.querySelectorAll('.canvas-overlay').forEach(panel => {
    // Bring to front when clicked anywhere
    panel.addEventListener('mousedown', () => {
      highestZ++;
      panel.style.zIndex = highestZ;
    });

    const header = panel.querySelector('.overlay-header, .tl-header');
    if (header) {
      header.style.cursor = 'move';
      let isDragging = false;
      let startX, startY, startLeft, startTop;

      header.addEventListener('mousedown', (e) => {
        if (e.target.closest('button')) return; // Ignore buttons
        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;
        
        // Compute current offset relative to its parent (#canvas-wrap)
        const rect = panel.getBoundingClientRect();
        const parentRect = panel.parentElement.getBoundingClientRect();
        
        startLeft = rect.left - parentRect.left;
        startTop = rect.top - parentRect.top;
        
        // Remove bottom/right CSS pinning so left/top takes full control
        panel.style.right = 'auto';
        panel.style.bottom = 'auto';
        panel.style.left = startLeft + 'px';
        panel.style.top = startTop + 'px';
      });

      document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        
        let newTop = startTop + dy;
        if (newTop < 0) newTop = 0; // Prevent header from going under topbar
        
        panel.style.left = (startLeft + dx) + 'px';
        panel.style.top = newTop + 'px';
      });

      document.addEventListener('mouseup', () => {
        isDragging = false;
      });
    }
  });
}

// ── Tab switching ─────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
      if (btn.dataset.tab === 'canvas' && lgcanvas) lgcanvas.draw(true, true);
      if (btn.dataset.tab === 'yaml' && cmEditor) cmEditor.refresh();
    });
  });
}

// ── Boot ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initOverlaysInteraction();
  if (typeof initEditor === 'function') initEditor();
  if (typeof initCanvas === 'function') initCanvas();
  if (typeof loadFlowsList === 'function') loadFlowsList();

  // ── Keyboard Shortcuts ───────────────────────────────────────────
  document.addEventListener('keydown', e => {
    const inInput = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.closest('.CodeMirror');
    const ctrl    = e.ctrlKey || e.metaKey;

    // Ctrl+S — Save
    if (ctrl && e.key === 's') {
      e.preventDefault();
      if (typeof saveCurrentFlow === 'function') saveCurrentFlow();
      return;
    }
    // Ctrl+N — New flow
    if (ctrl && e.key === 'n') {
      e.preventDefault();
      if (typeof openNlpModal === 'function') openNlpModal();
      return;
    }
    // Ctrl+E — Export
    if (ctrl && e.key === 'e') {
      e.preventDefault();
      if (typeof exportCurrentFlow === 'function') exportCurrentFlow();
      return;
    }
    // Ctrl+Delete — Delete selected flow
    if (ctrl && (e.key === 'Delete' || e.key === 'Backspace')) {
      e.preventDefault();
      if (typeof deleteCurrentFlow === 'function') deleteCurrentFlow();
      return;
    }
    // Ctrl+G — Group selected nodes
    if (ctrl && e.key.toLowerCase() === 'g' && !e.shiftKey) {
      e.preventDefault();
      if (typeof window.groupSelected === 'function') window.groupSelected();
      return;
    }
    // Ctrl+Shift+G — Ungroup selected nodes
    if (ctrl && e.key.toLowerCase() === 'g' && e.shiftKey) {
      e.preventDefault();
      if (typeof window.ungroupSelected === 'function') window.ungroupSelected();
      return;
    }
    // Escape — Close all overlays / modals
    if (e.key === 'Escape') {
      const logPanel = document.getElementById('canvas-log-panel');
      const tlPanel  = document.getElementById('canvas-timeline-panel');
      const modal    = document.getElementById('confirm-modal-bg');
      if (modal  && modal.style.display  !== 'none') { modal.style.display = 'none'; return; }
      if (logPanel && !logPanel.classList.contains('closed')) { window.toggleLogPanel?.(); return; }
      if (tlPanel  && !tlPanel.classList.contains('closed'))  { window.toggleTimelinePanel?.(); return; }
      return;
    }

    // Single-key shortcuts — block when in text fields
    if (inInput) return;

    // F5 — Run / Stop toggle
    if (e.key === 'F5') {
      e.preventDefault();
      if (typeof runCurrentFlow === 'function') runCurrentFlow();
      return;
    }
    // L — Log panel
    if (e.key.toLowerCase() === 'l' && !ctrl) {
      if (typeof window.toggleLogPanel === 'function') window.toggleLogPanel();
      return;
    }
    // T — Timeline panel
    if (e.key.toLowerCase() === 't' && !ctrl) {
      if (typeof window.toggleTimelinePanel === 'function') window.toggleTimelinePanel();
      return;
    }
    // A — Select Mode
    if (e.key.toLowerCase() === 'a' && !ctrl) {
      if (typeof window.setInteractionMode === 'function') window.setInteractionMode('select');
      return;
    }
    // B — Hand/Pan Mode
    if (e.key.toLowerCase() === 'b' && !ctrl) {
      if (typeof window.setInteractionMode === 'function') window.setInteractionMode('hand');
      return;
    }
    // Tab — Node Palette
    if (e.key === 'Tab' && !ctrl) {
      e.preventDefault(); // Prevent default focus switching
      if (typeof window.togglePalette === 'function') window.togglePalette();
      return;
    }
    // Delete / Backspace — Delete selected canvas node
    if ((e.key === 'Delete' || e.key === 'Backspace') && !ctrl) {
      if (typeof deleteSelectedNodes === 'function') deleteSelectedNodes();
      return;
    }
  }, { capture: true });

  // ── Prevent Browser Scroll on Hidden Overflow ────────────────────
  // When pressing Tab, the browser may try to scroll the hidden container
  // to bring a focused element into view. This resets it immediately.
  const canvasWrap = document.getElementById('canvas-wrap');
  if (canvasWrap) {
    canvasWrap.addEventListener('scroll', () => {
      if (canvasWrap.scrollTop !== 0) canvasWrap.scrollTop = 0;
      if (canvasWrap.scrollLeft !== 0) canvasWrap.scrollLeft = 0;
    });
  }
  const tabPane = document.getElementById('tab-canvas');
  if (tabPane) {
    tabPane.addEventListener('scroll', () => {
      if (tabPane.scrollTop !== 0) tabPane.scrollTop = 0;
      if (tabPane.scrollLeft !== 0) tabPane.scrollLeft = 0;
    });
  }

  // Flow title rename: sync new name back to YAML on blur or Enter
  const _titleInput = document.getElementById('flow-title');
  if (_titleInput) {
    const _applyRename = () => {
      const newName = _titleInput.value.trim();
      if (!newName || !cmEditor) return;
      const yaml = cmEditor.getValue();
      const updated = yaml.replace(/^name:.*$/m, `name: ${newName}`);
      if (updated !== yaml) cmEditor.setValue(updated);
    };
    _titleInput.addEventListener('blur', _applyRename);
    _titleInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); _applyRename(); _titleInput.blur(); }
    });
  }
});
