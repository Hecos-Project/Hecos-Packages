/**
 * Hecos Playbooks - State Management & Global Controls
 */
window.HecosPlaybooks = window.HecosPlaybooks || {};

(function(HP) {
  HP.data = [];
  HP.selectedPlaybookId = null;
  HP.playbooksSettings = { single_mode: false, master_enabled: true };
  HP.activeTabMap = {};
  HP.saveTimers = {};

  HP.escapeHtml = function(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  };

  HP.notifyPresenterChange = function() {
    try {
      localStorage.setItem('hecos_playbook_last_update', Date.now().toString());
      window.dispatchEvent(new CustomEvent('hecos:playbook:change'));
      if (window.Presenter && typeof window.Presenter.updatePlaybookStatus === 'function') {
        window.Presenter.updatePlaybookStatus(true);
      }
    } catch (e) {
      console.debug('[Playbooks] Failed to notify Presenter:', e);
    }
  };

  HP.showNotification = function(msg, type = 'info') {
    if (typeof window.showToast === 'function') {
      window.showToast(msg, type);
    } else {
      console.log(`[Playbooks:${type.toUpperCase()}] ${msg}`);
    }
  };

  HP.updateStats = function() {
    const totalPbs = HP.data.length;
    let activePbs = 0;
    let totalTabs = 0;
    let totalChars = 0;

    HP.data.forEach(pb => {
      const meta = pb.meta || {};
      if (meta.enabled) {
        activePbs++;
        if (pb.chat_role && pb.chat_role.enabled && pb.chat_role.brief) {
          totalChars += pb.chat_role.brief.length;
        }
      }
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

    const elToggleAll = document.getElementById('pb-toggle-all-switch');
    if (elToggleAll) {
      elToggleAll.checked = (activePbs > 0);
      elToggleAll.disabled = (totalPbs === 0);
    }
    const elSingleMode = document.getElementById('pb-single-mode-switch');
    if (elSingleMode) {
      elSingleMode.checked = !!HP.playbooksSettings.single_mode;
    }
  };

  HP.reloadList = async function() {
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
        HP.data = data.playbooks;
        if (data.settings) {
          HP.playbooksSettings = Object.assign(HP.playbooksSettings, data.settings);
        }
        if (typeof HP.render === 'function') {
          HP.render(HP.data);
        }
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
            ${HP.escapeHtml(err.message)}
          </p>
          <button class="pb-btn pb-btn-primary" onclick="window.pbReloadList()">
            <i class="fas fa-redo"></i> Retry
          </button>
        </div>
      `;
    }
  };

  HP.toggleAllPlaybooks = async function(enabled) {
    try {
      const res = await fetch('/api/ext/presenter/playbooks/toggle_all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: enabled,
          active_pid: HP.selectedPlaybookId
        })
      });
      const data = await res.json();
      if (data.ok) {
        if (Array.isArray(data.playbooks)) {
          HP.data = data.playbooks;
        } else {
          HP.data.forEach(p => {
            if (p.meta) p.meta.enabled = enabled;
          });
        }
        if (data.settings) {
          HP.playbooksSettings = Object.assign(HP.playbooksSettings, data.settings);
        }
        HP.updateStats();
        if (typeof HP.render === 'function') {
          HP.render(HP.data);
        }
        HP.notifyPresenterChange();
        HP.showNotification(enabled ? 'All playbooks enabled' : 'All playbooks disabled', 'success');
      } else {
        HP.showNotification(data.error || 'Failed to toggle playbooks', 'error');
        HP.updateStats();
      }
    } catch (e) {
      HP.showNotification('Network error', 'error');
      HP.updateStats();
    }
  };

  HP.toggleSingleMode = async function(enabled) {
    try {
      const res = await fetch('/api/ext/presenter/playbooks/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          single_mode: enabled,
          active_pid: HP.selectedPlaybookId
        })
      });
      const data = await res.json();
      if (data.ok) {
        HP.playbooksSettings = Object.assign(HP.playbooksSettings, data.settings || {});
        if (Array.isArray(data.playbooks)) {
          HP.data = data.playbooks;
        } else if (enabled) {
          let kept = false;
          HP.data.forEach(p => {
            if (p.meta) {
              if (p.meta.id === HP.selectedPlaybookId && p.meta.enabled) {
                kept = true;
              } else if (!kept && p.meta.enabled) {
                kept = true;
              } else {
                p.meta.enabled = false;
              }
            }
          });
        }
        HP.updateStats();
        if (typeof HP.render === 'function') {
          HP.render(HP.data);
        }
        HP.notifyPresenterChange();
        HP.showNotification(
          enabled ? 'Single Playbook mode enabled (max 1 active)' : 'Single Playbook mode disabled (multiple can be active)',
          'success'
        );
      } else {
        HP.showNotification(data.error || 'Failed to update setting', 'error');
        HP.updateStats();
      }
    } catch (e) {
      HP.showNotification('Network error', 'error');
      HP.updateStats();
    }
  };

  // Expose global methods
  window.pbReloadList = HP.reloadList;
  window.pbToggleAllPlaybooks = HP.toggleAllPlaybooks;
  window.pbToggleSingleMode = HP.toggleSingleMode;
})(window.HecosPlaybooks);
