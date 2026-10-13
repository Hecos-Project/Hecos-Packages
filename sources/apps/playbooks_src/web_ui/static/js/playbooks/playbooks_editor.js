/**
 * Hecos Playbooks - Editor & Tab Operations
 * Handles tab selection, toggling, content autosave, and tab CRUD.
 */
window.HecosPlaybooks = window.HecosPlaybooks || {};

(function(HP) {
  window.pbSelectPlaybook = function(pid) {
    HP.selectedPlaybookId = pid;
    HP.render();
  };

  window.pbSelectTab = function(pid, tabId) {
    HP.activeTabMap[pid] = tabId;
    HP.render();
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
        if (enabled && HP.playbooksSettings.single_mode) {
          HP.data.forEach(p => {
            if (p.meta) p.meta.enabled = (p.meta.id === pid);
          });
        } else {
          const pb = HP.data.find(p => p.meta && p.meta.id === pid);
          if (pb && pb.meta) pb.meta.enabled = enabled;
        }
        HP.updateStats();
        HP.render();
        if (typeof HP.notifyPresenterChange === 'function') HP.notifyPresenterChange();
        HP.showNotification(`Playbook ${enabled ? 'enabled' : 'disabled'}`, 'success');
      } else {
        HP.showNotification(data.error || 'Update failed', 'error');
      }
    } catch (e) {
      HP.showNotification('Network error', 'error');
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
        const pb = HP.data.find(p => p.meta && p.meta.id === pid);
        if (pb) {
          const tab = (pb.tabs || []).find(t => t.id === tabId);
          if (tab) tab.enabled = enabled;
        }
        HP.updateStats();
        if (typeof HP.notifyPresenterChange === 'function') HP.notifyPresenterChange();
        HP.showNotification(`Tab ${enabled ? 'enabled' : 'disabled'}`, 'success');
      } else {
        HP.showNotification(data.error || 'Tab update failed', 'error');
      }
    } catch (e) {
      HP.showNotification('Network error', 'error');
    }
  };

  window.pbChangeTabTarget = async function(pid, tabId, target) {
    try {
      const res = await fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}/tabs/${encodeURIComponent(tabId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: target })
      });
      const data = await res.json();
      if (data.ok) {
        const pb = HP.data.find(p => p.meta && p.meta.id === pid);
        if (pb) {
          const tab = (pb.tabs || []).find(t => t.id === tabId);
          if (tab) tab.target = target;
        }
        const info = (typeof HP.getTargetInfo === 'function') ? HP.getTargetInfo(target) : { title: target };
        HP.render();
        if (typeof HP.notifyPresenterChange === 'function') HP.notifyPresenterChange();
        HP.showNotification(`Target updated: ${info.title}`, 'success');
      } else {
        HP.showNotification(data.error || 'Failed to update target', 'error');
      }
    } catch (e) {
      HP.showNotification('Network error', 'error');
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
    const pb = HP.data.find(p => p.meta && p.meta.id === pid);
    if (pb) {
      const tab = (pb.tabs || []).find(t => t.id === tabId);
      if (tab) tab.content = content;
    }
    HP.updateStats();

    // Debounced autosave
    const key = `${pid}-${tabId}`;
    if (HP.saveTimers[key]) clearTimeout(HP.saveTimers[key]);
    HP.saveTimers[key] = setTimeout(() => {
      window.pbSaveTabContentNow(pid, tabId);
    }, 1000);
  };

  window.pbSaveTabContentNow = async function(pid, tabId) {
    const key = `${pid}-${tabId}`;
    if (HP.saveTimers[key]) clearTimeout(HP.saveTimers[key]);

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
        HP.activeTabMap[pid] = data.tab.id;
        window.pbReloadList();
        HP.showNotification('Tab created successfully', 'success');
      } else {
        HP.showNotification(data.error || 'Failed to create tab', 'error');
      }
    })
    .catch(() => HP.showNotification('Network error', 'error'));
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
        HP.showNotification('Tab renamed', 'success');
      } else {
        HP.showNotification(data.error || 'Rename failed', 'error');
      }
    })
    .catch(() => HP.showNotification('Network error', 'error'));
  };

  window.pbDeleteTab = function(pid, tabId) {
    if (!confirm('Are you sure you want to delete this tab? All tab content will be lost.')) return;

    fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}/tabs/${encodeURIComponent(tabId)}`, {
      method: 'DELETE'
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        delete HP.activeTabMap[pid];
        window.pbReloadList();
        HP.showNotification('Tab deleted', 'success');
      } else {
        HP.showNotification(data.error || 'Delete failed', 'error');
      }
    })
    .catch(() => HP.showNotification('Network error', 'error'));
  };
})(window.HecosPlaybooks);
