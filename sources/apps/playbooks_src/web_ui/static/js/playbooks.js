
(function() {
  let playbooksData = [];
  let activeTabMap = {}; // { [playbookId]: activeTabId }
  let saveTimers = {}; // { [tabKey]: timerId }
  let collapsedMap = {}; // { [playbookId]: bool }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function showNotification(msg, type = 'info') {
    if (typeof window.showToast === 'function') {
      window.showToast(msg, type);
    } else {
      console.log(`[Playbooks:${type.toUpperCase()}] ${msg}`);
    }
  }

  window.pbReloadList = async function() {
    const listEl = document.getElementById('playbooks-list');
    if (!listEl) return;

    listEl.innerHTML = `
      <div style="padding: 30px; text-align: center; color: var(--muted, #94a3b8);">
        <i class="fas fa-circle-notch fa-spin fa-2x" style="color: #60a5fa; margin-bottom: 12px;"></i>
        <div style="font-size: 14px; font-weight: 500;">Loading Playbooks...</div>
      </div>
    `;

    try {
      const res = await fetch('/api/ext/presenter/playbooks');
      if (!res.ok) {
        throw new Error(`HTTP error ${res.status}`);
      }
      const data = await res.json();
      if (data.ok && Array.isArray(data.playbooks)) {
        playbooksData = data.playbooks;
        renderPlaybooks(playbooksData);
      } else {
        throw new Error(data.error || 'Invalid API response format');
      }
    } catch (err) {
      console.error('[Playbooks] Failed to load:', err);
      listEl.innerHTML = `
        <div class="pb-empty-state" style="border-color: rgba(239, 68, 68, 0.3); background: rgba(239, 68, 68, 0.04);">
          <div class="pb-empty-icon" style="background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.3); color: #f87171;">
            <i class="fas fa-exclamation-triangle"></i>
          </div>
          <h3 style="margin: 0 0 8px 0; color: #f87171; font-size: 1.1em;">Error Loading Playbooks</h3>
          <p style="color: var(--muted, #94a3b8); font-size: 13px; max-width: 480px; margin: 0 auto 16px auto;">
            ${escapeHtml(err.message)}
          </p>
          <button class="pb-btn pb-btn-primary" onclick="window.pbReloadList()">
            <i class="fas fa-redo"></i> Retry
          </button>
        </div>
      `;
    }
  };

  function updateStats() {
    const totalPbs = playbooksData.length;
    let activePbs = 0;
    let totalTabs = 0;
    let totalChars = 0;

    playbooksData.forEach(pb => {
      const meta = pb.meta || {};
      if (meta.enabled) activePbs++;
      (pb.tabs || []).forEach(t => {
        totalTabs++;
        if (meta.enabled && t.enabled) {
          totalChars += (t.content || '').length;
        }
      });
    });

    const estTokens = Math.round(totalChars / 4);

    const elTotal = document.getElementById('pb-stat-total');
    const elActive = document.getElementById('pb-stat-active');
    const elTabs = document.getElementById('pb-stat-tabs');
    const elTokens = document.getElementById('pb-stat-tokens');

    if (elTotal) elTotal.textContent = totalPbs;
    if (elActive) elActive.textContent = activePbs;
    if (elTabs) elTabs.textContent = totalTabs;
    if (elTokens) elTokens.textContent = `~${estTokens} tokens`;
  }

  function renderPlaybooks(playbooks) {
    const container = document.getElementById('playbooks-list');
    if (!container) return;

    updateStats();

    if (!playbooks || playbooks.length === 0) {
      container.innerHTML = `
        <div class="pb-empty-state">
          <div class="pb-empty-icon">
            <i class="fas fa-book-open"></i>
          </div>
          <h3 style="margin: 0 0 8px 0; color: var(--text, #fff); font-size: 1.25em; font-weight: 700;">No Playbooks Found</h3>
          <p style="color: var(--muted, #94a3b8); font-size: 13px; max-width: 540px; margin: 0 auto; line-height: 1.5;">
            Playbooks transform the Presenter into a specialized trainer, strict coach, roleplay partner, or domain expert. Inject structured educational material and behavioral directives directly into the AI's mind.
          </p>

          <div class="pb-templates-grid">
            <div class="pb-template-card" onclick="window.pbCreateTemplate('english')">
              <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
                <div style="width:32px; height:32px; border-radius:8px; background:rgba(59,130,246,0.15); color:#60a5fa; display:flex; align-items:center; justify-content:center;">
                  <i class="fas fa-graduation-cap"></i>
                </div>
                <div style="font-weight:700; color:var(--text, #fff); font-size:14px;">English Coach</div>
              </div>
              <div style="font-size:12px; color:var(--muted, #94a3b8); line-height:1.4;">
                Grammar guidelines, active corrections, and immersive conversational roleplay scenarios.
              </div>
              <div style="margin-top:10px; font-size:11px; font-weight:600; color:#60a5fa;">
                + Install Starter Pack &rarr;
              </div>
            </div>

            <div class="pb-template-card" onclick="window.pbCreateTemplate('sales')">
              <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
                <div style="width:32px; height:32px; border-radius:8px; background:rgba(16,185,129,0.15); color:#34d399; display:flex; align-items:center; justify-content:center;">
                  <i class="fas fa-chart-line"></i>
                </div>
                <div style="font-weight:700; color:var(--text, #fff); font-size:14px;">Sales Masterclass</div>
              </div>
              <div style="font-size:12px; color:var(--muted, #94a3b8); line-height:1.4;">
                Objection handling frameworks (budget, timing), high-impact power words, and closing guidelines.
              </div>
              <div style="margin-top:10px; font-size:11px; font-weight:600; color:#34d399;">
                + Install Starter Pack &rarr;
              </div>
            </div>

            <div class="pb-template-card" onclick="window.pbOpenCreateModal()">
              <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
                <div style="width:32px; height:32px; border-radius:8px; background:rgba(139,92,246,0.15); color:#c084fc; display:flex; align-items:center; justify-content:center;">
                  <i class="fas fa-plus"></i>
                </div>
                <div style="font-weight:700; color:var(--text, #fff); font-size:14px;">Blank Playbook</div>
              </div>
              <div style="font-size:12px; color:var(--muted, #94a3b8); line-height:1.4;">
                Create a fully customized Playbook from scratch with custom tabs, rules, and scripts.
              </div>
              <div style="margin-top:10px; font-size:11px; font-weight:600; color:#c084fc;">
                + Create from Scratch &rarr;
              </div>
            </div>
          </div>
        </div>
      `;
      return;
    }

    let html = '';
    playbooks.forEach(pb => {
      const meta = pb.meta || {};
      const tabs = pb.tabs || [];
      const pid = meta.id;
      const isHpm = meta.source === 'hpm';
      const isCollapsed = !!collapsedMap[pid];

      if (!activeTabMap[pid] && tabs.length > 0) {
        activeTabMap[pid] = tabs[0].id;
      }
      const curTabId = activeTabMap[pid];
      const curTab = tabs.find(t => t.id === curTabId) || tabs[0] || null;

      let playbookChars = 0;
      tabs.forEach(t => { if (t.enabled) playbookChars += (t.content || '').length; });
      const pbTokens = Math.round(playbookChars / 4);

      html += `
        <div class="pb-card" id="pb-card-${escapeHtml(pid)}">
          <!-- Card Header -->
          <div class="pb-card-header">
            <div class="pb-card-title-group" onclick="window.pbToggleCollapse('${escapeHtml(pid)}')">
              <i class="fas fa-chevron-${isCollapsed ? 'right' : 'down'}" style="color:var(--muted); font-size:12px; width:14px;"></i>
              <div style="width:34px; height:34px; border-radius:8px; background:rgba(255,255,255,0.06); display:flex; align-items:center; justify-content:center; color:#60a5fa;">
                <i class="fas ${escapeHtml(meta.icon || 'fa-book-open')}"></i>
              </div>
              <div>
                <div style="font-weight:700; font-size:14px; color:var(--text, #fff); display:flex; align-items:center; gap:8px;">
                  ${escapeHtml(meta.name || 'Untitled Playbook')}
                  ${isHpm ? '<span class="pb-badge pb-badge-purple">HPM Package</span>' : '<span class="pb-badge pb-badge-blue">Local</span>'}
                  <span class="pb-badge pb-badge-green">${tabs.length} tabs</span>
                  <span style="font-size:11px; font-weight:500; color:var(--muted);">~${pbTokens} tokens</span>
                </div>
                ${meta.description ? `<div style="font-size:12px; color:var(--muted); margin-top:2px;">${escapeHtml(meta.description)}</div>` : ''}
              </div>
            </div>

            <div style="display:flex; align-items:center; gap:12px;">
              <!-- Master Toggle Switch -->
              <label class="switch" title="Enable / Disable Playbook" style="margin:0;">
                <input type="checkbox" ${meta.enabled ? 'checked' : ''} onchange="window.pbToggleEnabled('${escapeHtml(pid)}', this.checked)">
                <span class="slider"></span>
              </label>

              <!-- Edit metadata -->
              <button class="pb-btn pb-btn-outline" style="padding:6px 10px;" onclick="window.pbOpenEditModal('${escapeHtml(pid)}')" title="Edit details">
                <i class="fas fa-pen"></i>
              </button>

              <!-- Delete (local only) -->
              ${!isHpm ? `
                <button class="pb-btn pb-btn-outline" style="padding:6px 10px; color:#f87171; border-color:rgba(239,68,68,0.2);" onclick="window.pbDeletePlaybook('${escapeHtml(pid)}')" title="Delete Playbook">
                  <i class="fas fa-trash"></i>
                </button>
              ` : ''}
            </div>
          </div>

          <!-- Card Body (Tabs & Editor) -->
          <div class="pb-card-body" style="display: ${isCollapsed ? 'none' : 'block'};">
            <!-- Tabs Navigation Bar -->
            <div class="pb-tabs-nav">
              ${tabs.map(t => `
                <button class="pb-tab-pill ${t.id === curTabId ? 'active' : ''}" onclick="window.pbSelectTab('${escapeHtml(pid)}', '${escapeHtml(t.id)}')">
                  <i class="fas ${t.enabled ? 'fa-check-circle' : 'fa-circle'}" style="font-size:10px; color:${t.enabled ? '#34d399' : 'var(--muted)'};"></i>
                  ${escapeHtml(t.name || 'Tab')}
                </button>
              `).join('')}

              ${!isHpm ? `
                <button class="pb-tab-pill" style="border-style:dashed; color:#60a5fa;" onclick="window.pbAddTab('${escapeHtml(pid)}')">
                  <i class="fas fa-plus"></i> Add Tab
                </button>
              ` : ''}
            </div>

            <!-- Tab Editor Content -->
            ${curTab ? `
              <div class="pb-editor-area">
                <div class="pb-editor-toolbar">
                  <div style="display:flex; align-items:center; gap:10px;">
                    <strong style="color:var(--text, #fff);">${escapeHtml(curTab.name)}</strong>
                    <label style="display:inline-flex; align-items:center; gap:5px; font-size:11px; cursor:pointer; color:var(--muted); margin:0;">
                      <input type="checkbox" ${curTab.enabled ? 'checked' : ''} onchange="window.pbToggleTabEnabled('${escapeHtml(pid)}', '${escapeHtml(curTab.id)}', this.checked)">
                      Inject into Prompt
                    </label>
                  </div>

                  <div style="display:flex; align-items:center; gap:8px;">
                    ${!isHpm ? `
                      <button class="pb-btn pb-btn-outline" style="padding:3px 8px; font-size:11px;" onclick="window.pbRenameTab('${escapeHtml(pid)}', '${escapeHtml(curTab.id)}', '${escapeHtml(curTab.name)}')">
                        <i class="fas fa-pen"></i> Rename
                      </button>
                      <button class="pb-btn pb-btn-outline" style="padding:3px 8px; font-size:11px; color:#f87171;" onclick="window.pbDeleteTab('${escapeHtml(pid)}', '${escapeHtml(curTab.id)}')">
                        <i class="fas fa-trash"></i>
                      </button>
                    ` : ''}
                  </div>
                </div>

                <textarea
                  id="pb-textarea-${escapeHtml(pid)}-${escapeHtml(curTab.id)}"
                  class="pb-textarea"
                  placeholder="Enter instructions, reference material, roleplay scripts, or behavioral guidelines..."
                  oninput="window.pbOnTextareaInput('${escapeHtml(pid)}', '${escapeHtml(curTab.id)}', this.value)"
                >${escapeHtml(curTab.content || '')}</textarea>

                <div class="pb-editor-footer">
                  <div style="display:flex; align-items:center; gap:12px;">
                    <span id="pb-status-${escapeHtml(pid)}-${escapeHtml(curTab.id)}" style="color:#34d399;">
                      <i class="fas fa-check"></i> Saved
                    </span>
                    <span>Characters: <strong id="pb-chars-${escapeHtml(pid)}-${escapeHtml(curTab.id)}">${(curTab.content || '').length}</strong></span>
                    <span>Approx. Tokens: <strong id="pb-tokens-${escapeHtml(pid)}-${escapeHtml(curTab.id)}">~${Math.round((curTab.content || '').length / 4)}</strong></span>
                  </div>

                  <div>
                    <button class="pb-btn pb-btn-primary" style="padding:4px 10px; font-size:11px;" onclick="window.pbSaveTabContentNow('${escapeHtml(pid)}', '${escapeHtml(curTab.id)}')">
                      <i class="fas fa-save"></i> Save Now
                    </button>
                  </div>
                </div>
              </div>
            ` : `
              <div style="text-align:center; padding:24px; color:var(--muted); font-size:13px;">
                No tabs in this Playbook yet. Click "Add Tab" to get started.
              </div>
            `}
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
  }

  window.pbToggleCollapse = function(pid) {
    collapsedMap[pid] = !collapsedMap[pid];
    renderPlaybooks(playbooksData);
  };

  window.pbSelectTab = function(pid, tabId) {
    activeTabMap[pid] = tabId;
    renderPlaybooks(playbooksData);
  };

  window.pbToggleEnabled = async function(pid, enabled) {
    try {
      const res = await fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: enabled })
      });
      const data = await res.json();
      if (data.ok) {
        const pb = playbooksData.find(p => p.meta && p.meta.id === pid);
        if (pb && pb.meta) pb.meta.enabled = enabled;
        updateStats();
        showNotification(`Playbook ${enabled ? 'enabled' : 'disabled'}`, 'success');
      } else {
        showNotification(data.error || 'Update failed', 'error');
      }
    } catch (e) {
      showNotification('Network error', 'error');
    }
  };

  window.pbToggleTabEnabled = async function(pid, tabId, enabled) {
    try {
      const res = await fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}/tabs/${encodeURIComponent(tabId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: enabled })
      });
      const data = await res.json();
      if (data.ok) {
        const pb = playbooksData.find(p => p.meta && p.meta.id === pid);
        if (pb) {
          const tab = (pb.tabs || []).find(t => t.id === tabId);
          if (tab) tab.enabled = enabled;
        }
        updateStats();
        showNotification(`Tab ${enabled ? 'enabled' : 'disabled'}`, 'success');
      } else {
        showNotification(data.error || 'Tab update failed', 'error');
      }
    } catch (e) {
      showNotification('Network error', 'error');
    }
  };

  window.pbOnTextareaInput = function(pid, tabId, content) {
    const charsEl = document.getElementById(`pb-chars-${pid}-${tabId}`);
    const tokensEl = document.getElementById(`pb-tokens-${pid}-${tabId}`);
    const statusEl = document.getElementById(`pb-status-${pid}-${tabId}`);

    if (charsEl) charsEl.textContent = content.length;
    if (tokensEl) tokensEl.textContent = `~${Math.round(content.length / 4)}`;
    if (statusEl) {
      statusEl.style.color = '#fbbf24';
      statusEl.innerHTML = '<i class="fas fa-pen"></i> Unsaved changes...';
    }

    // Update in-memory
    const pb = playbooksData.find(p => p.meta && p.meta.id === pid);
    if (pb) {
      const tab = (pb.tabs || []).find(t => t.id === tabId);
      if (tab) tab.content = content;
    }
    updateStats();

    // Debounced autosave
    const key = `${pid}-${tabId}`;
    if (saveTimers[key]) clearTimeout(saveTimers[key]);
    saveTimers[key] = setTimeout(() => {
      window.pbSaveTabContentNow(pid, tabId);
    }, 1000);
  };

  window.pbSaveTabContentNow = async function(pid, tabId) {
    const key = `${pid}-${tabId}`;
    if (saveTimers[key]) clearTimeout(saveTimers[key]);

    const textarea = document.getElementById(`pb-textarea-${pid}-${tabId}`);
    const content = textarea ? textarea.value : '';
    const statusEl = document.getElementById(`pb-status-${pid}-${tabId}`);

    if (statusEl) {
      statusEl.style.color = '#60a5fa';
      statusEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    }

    try {
      const res = await fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}/tabs/${encodeURIComponent(tabId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: content })
      });
      const data = await res.json();
      if (data.ok) {
        if (statusEl) {
          statusEl.style.color = '#34d399';
          statusEl.innerHTML = '<i class="fas fa-check"></i> Saved';
        }
      } else {
        if (statusEl) {
          statusEl.style.color = '#f87171';
          statusEl.innerHTML = '<i class="fas fa-times"></i> Error';
        }
      }
    } catch (e) {
      if (statusEl) {
        statusEl.style.color = '#f87171';
        statusEl.innerHTML = '<i class="fas fa-times"></i> Connection error';
      }
    }
  };

  window.pbAddTab = function(pid) {
    const name = prompt('Enter new tab name (e.g., Grammar Rules, Roleplay Scripts, Directives):');
    if (!name || !name.trim()) return;

    fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}/tabs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim(), content: '' })
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        activeTabMap[pid] = data.tab.id;
        window.pbReloadList();
        showNotification('Tab created successfully', 'success');
      } else {
        showNotification(data.error || 'Failed to create tab', 'error');
      }
    })
    .catch(() => showNotification('Network error', 'error'));
  };

  window.pbRenameTab = function(pid, tabId, oldName) {
    const name = prompt('New tab name:', oldName);
    if (!name || !name.trim() || name.trim() === oldName) return;

    fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}/tabs/${encodeURIComponent(tabId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() })
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        window.pbReloadList();
        showNotification('Tab renamed', 'success');
      } else {
        showNotification(data.error || 'Failed to rename tab', 'error');
      }
    })
    .catch(() => showNotification('Network error', 'error'));
  };

  window.pbDeleteTab = function(pid, tabId) {
    if (!confirm('Are you sure you want to delete this tab?')) return;

    fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}/tabs/${encodeURIComponent(tabId)}`, {
      method: 'DELETE'
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        delete activeTabMap[pid];
        window.pbReloadList();
        showNotification('Tab deleted', 'info');
      } else {
        showNotification(data.error || 'Failed to delete tab', 'error');
      }
    })
    .catch(() => showNotification('Network error', 'error'));
  };

  
  window.pbExportPlaybook = function(pid) {
    window.location.href = `/api/ext/presenter/playbooks/${encodeURIComponent(pid)}/export`;
  };

  window.pbImportPlaybook = function(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    showNotification('Importing playbook...', 'info');
    
    fetch('/api/ext/presenter/playbooks/import', {
      method: 'POST',
      body: formData
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        window.pbReloadList();
        showNotification('Playbook imported successfully!', 'success');
      } else {
        showNotification(data.error || 'Failed to import playbook', 'error');
      }
    })
    .catch(() => showNotification('Network error during import', 'error'))
    .finally(() => {
      event.target.value = ''; // reset
    });
  };

  window.pbDeletePlaybook = function(pid) {
    if (!confirm('Are you sure you want to permanently delete this Playbook and all its tabs?')) return;

    fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}`, {
      method: 'DELETE'
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        window.pbReloadList();
        showNotification('Playbook deleted', 'info');
      } else {
        showNotification(data.error || 'Failed to delete playbook', 'error');
      }
    })
    .catch(() => showNotification('Network error', 'error'));
  };

  window.pbCreateTemplate = function(templateType) {
    fetch('/api/ext/presenter/playbooks/template', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template: templateType })
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        window.pbReloadList();
        showNotification('Template installed successfully!', 'success');
      } else {
        showNotification(data.error || 'Failed to install template', 'error');
      }
    })
    .catch(() => showNotification('Network error', 'error'));
  };

  window.pbOpenCreateModal = function() {
    const modal = document.getElementById('pb-modal-container');
    if (!modal) return;

    modal.innerHTML = `
      <div class="pb-modal-overlay" onclick="if(event.target === this) window.pbCloseModal()">
        <div class="pb-modal-box">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
            <h3 style="margin:0; font-size:16px; color:var(--text, #fff); display:flex; align-items:center; gap:8px;">
              <i class="fas fa-plus-circle" style="color:#60a5fa;"></i> New Playbook
            </h3>
            <button onclick="window.pbCloseModal()" style="background:none; border:none; color:var(--muted); font-size:16px; cursor:pointer;">&times;</button>
          </div>

          <div style="margin-bottom:14px;">
            <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;">Playbook Name</label>
            <input type="text" id="pb-create-name" placeholder="E.g., Learn English, Sales Masterclass, Python Coach..." style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;">
          </div>

          <div style="margin-bottom:14px;">
            <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;">Description (optional)</label>
            <input type="text" id="pb-create-desc" placeholder="Brief description of the domain or purpose..." style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;">
          </div>

          <div style="margin-bottom:20px;">
            <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;">FontAwesome Icon</label>
            <select id="pb-create-icon" style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;">
              <option value="fa-book-open">fa-book-open (Open Book)</option>
              <option value="fa-graduation-cap">fa-graduation-cap (Education / Coaching)</option>
              <option value="fa-chart-line">fa-chart-line (Sales / Business)</option>
              <option value="fa-language">fa-language (Languages / Translation)</option>
              <option value="fa-brain">fa-brain (Psychology / Strategy)</option>
              <option value="fa-shield-alt">fa-shield-alt (Safety / Directives)</option>
              <option value="fa-headset">fa-headset (Customer Support)</option>
              <option value="fa-code">fa-code (Programming / Technical)</option>
            </select>
          </div>

          <div style="display:flex; justify-content:flex-end; gap:10px;">
            <button class="pb-btn pb-btn-outline" onclick="window.pbCloseModal()">Cancel</button>
            <button class="pb-btn pb-btn-primary" onclick="window.pbSubmitCreate()">Create Playbook</button>
          </div>
        </div>
      </div>
    `;
    setTimeout(() => {
      const el = document.getElementById('pb-create-name');
      if (el) el.focus();
    }, 100);
  };

  window.pbOpenEditModal = function(pid) {
    const pb = playbooksData.find(p => p.meta && p.meta.id === pid);
    if (!pb) return;
    const meta = pb.meta || {};

    const modal = document.getElementById('pb-modal-container');
    if (!modal) return;

    modal.innerHTML = `
      <div class="pb-modal-overlay" onclick="if(event.target === this) window.pbCloseModal()">
        <div class="pb-modal-box">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
            <h3 style="margin:0; font-size:16px; color:var(--text, #fff); display:flex; align-items:center; gap:8px;">
              <i class="fas fa-pen" style="color:#60a5fa;"></i> Edit Playbook
            </h3>
            <button onclick="window.pbCloseModal()" style="background:none; border:none; color:var(--muted); font-size:16px; cursor:pointer;">&times;</button>
          </div>

          <div style="margin-bottom:14px;">
            <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;">Playbook Name</label>
            <input type="text" id="pb-edit-name" value="${escapeHtml(meta.name || '')}" style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;">
          </div>

          <div style="margin-bottom:14px;">
            <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;">Description</label>
            <input type="text" id="pb-edit-desc" value="${escapeHtml(meta.description || '')}" style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;">
          </div>

          <div style="margin-bottom:20px;">
            <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;">FontAwesome Icon</label>
            <input type="text" id="pb-edit-icon" value="${escapeHtml(meta.icon || 'fa-book-open')}" style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;">
          </div>

          <div style="display:flex; justify-content:flex-end; gap:10px;">
            <button class="pb-btn pb-btn-outline" onclick="window.pbCloseModal()">Cancel</button>
            <button class="pb-btn pb-btn-primary" onclick="window.pbSubmitEdit('${escapeHtml(pid)}')">Save Changes</button>
          </div>
        </div>
      </div>
    `;
  };

  window.pbSubmitCreate = function() {
    const nameEl = document.getElementById('pb-create-name');
    const descEl = document.getElementById('pb-create-desc');
    const iconEl = document.getElementById('pb-create-icon');

    const name = nameEl ? nameEl.value.trim() : '';
    const desc = descEl ? descEl.value.trim() : '';
    const icon = iconEl ? iconEl.value : 'fa-book-open';

    if (!name) {
      alert('Please enter a name for the Playbook');
      return;
    }

    fetch('/api/ext/presenter/playbooks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, description: desc, icon: icon })
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        window.pbCloseModal();
        window.pbReloadList();
        showNotification('Playbook created successfully!', 'success');
      } else {
        alert(data.error || 'Failed to create playbook');
      }
    })
    .catch(() => alert('Network error'));
  };

  window.pbSubmitEdit = function(pid) {
    const nameEl = document.getElementById('pb-edit-name');
    const descEl = document.getElementById('pb-edit-desc');
    const iconEl = document.getElementById('pb-edit-icon');

    const name = nameEl ? nameEl.value.trim() : '';
    const desc = descEl ? descEl.value.trim() : '';
    const icon = iconEl ? iconEl.value.trim() : 'fa-book-open';

    if (!name) {
      alert('Please enter a name for the Playbook');
      return;
    }

    fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, description: desc, icon: icon })
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        window.pbCloseModal();
        window.pbReloadList();
        showNotification('Playbook updated successfully!', 'success');
      } else {
        alert(data.error || 'Failed to update playbook');
      }
    })
    .catch(() => alert('Network error'));
  };

  window.pbCloseModal = function() {
    const modal = document.getElementById('pb-modal-container');
    if (modal) modal.innerHTML = '';
  };

  window.pbPreviewContext = async function() {
    const modal = document.getElementById('pb-modal-container');
    if (!modal) return;

    modal.innerHTML = `
      <div class="pb-modal-overlay" onclick="if(event.target === this) window.pbCloseModal()">
        <div class="pb-modal-box" style="max-width: 680px; width: 92%;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
            <h3 style="margin:0; font-size:16px; color:var(--text, #fff); display:flex; align-items:center; gap:8px;">
              <i class="fas fa-eye" style="color:#60a5fa;"></i> Injected Context Preview
            </h3>
            <button onclick="window.pbCloseModal()" style="background:none; border:none; color:var(--muted); font-size:16px; cursor:pointer;">&times;</button>
          </div>

          <div style="font-size:12px; color:var(--muted); margin-bottom:12px;">
            This is the active Playbook material compiled and injected directly into the Presenter's system prompt prior to every commentary generation.
          </div>

          <div id="pb-preview-body" style="background:#0d1117; border:1px solid rgba(255,255,255,0.1); border-radius:8px; padding:14px; font-family:monospace; font-size:12px; max-height:360px; overflow-y:auto; white-space:pre-wrap; color:#e6edf3;">
            <i class="fas fa-circle-notch fa-spin"></i> Compiling active context...
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:14px;">
            <span id="pb-preview-tokens" style="font-size:12px; font-weight:600; color:#fbbf24;"></span>
            <button class="pb-btn pb-btn-primary" onclick="window.pbCloseModal()">Close</button>
          </div>
        </div>
      </div>
    `;

    try {
      const res = await fetch('/api/ext/presenter/playbooks/context');
      const data = await res.json();
      const bodyEl = document.getElementById('pb-preview-body');
      const tokEl = document.getElementById('pb-preview-tokens');
      if (data.ok) {
        if (bodyEl) {
          bodyEl.textContent = data.context || '(No active playbooks or tabs currently. Enable at least one playbook tab with text.)';
        }
        if (tokEl) {
          tokEl.textContent = `Estimated Tokens: ~${data.approx_tokens || 0}`;
        }
      } else {
        if (bodyEl) bodyEl.textContent = 'Error: ' + (data.error || 'Failed to compile');
      }
    } catch (e) {
      const bodyEl = document.getElementById('pb-preview-body');
      if (bodyEl) bodyEl.textContent = 'Connection error.';
    }
  };

  // Auto initialize on load
  setTimeout(window.pbReloadList, 150);
})();

