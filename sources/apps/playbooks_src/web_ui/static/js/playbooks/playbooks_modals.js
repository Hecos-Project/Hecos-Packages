/**
 * Hecos Playbooks - Modals & Templates
 * Handles Create, Edit, Preview Context, and Starter Pack templates.
 */
window.HecosPlaybooks = window.HecosPlaybooks || {};

(function(HP) {
  window.pbCloseModal = function() {
    const modal = document.getElementById('pb-modal-container');
    if (modal) modal.innerHTML = '';
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

          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-bottom:20px;">
            <div>
              <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;" title="Operating mode: defines how Chat and Presenter collaborate">
                Operating Mode <i class="fas fa-info-circle" style="color:#60a5fa; font-size:10px;"></i>
              </label>
              <select id="pb-create-mode" style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;" title="Choose playbook operating mode">
                <option value="training" title="Training: Chat plays the counterpart (e.g. customer, passerby) and Presenter coaches you with real-time tips">🎯 Training / Coaching</option>
                <option value="roleplay" title="Roleplay: Chat adopts a character or scenario for open simulation">🎭 Roleplay / Simulation</option>
                <option value="learning" title="Learning: Targeted conversation to practice languages or professional skills">🎓 Language / Skills Learning</option>
                <option value="freestyle" title="Freestyle: General directives and reference knowledge without rigid roles">📖 Freestyle (General Knowledge)</option>
              </select>
            </div>
            <div>
              <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;">FontAwesome Icon</label>
              <select id="pb-create-icon" style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;">
                <option value="fa-book-open">fa-book-open (Open Book)</option>
                <option value="fa-graduation-cap">fa-graduation-cap (Education / Coach)</option>
                <option value="fa-chart-line">fa-chart-line (Sales / Business)</option>
                <option value="fa-language">fa-language (Languages / Translation)</option>
                <option value="fa-brain">fa-brain (Psychology / Strategy)</option>
                <option value="fa-shield-alt">fa-shield-alt (Security / Rules)</option>
                <option value="fa-headset">fa-headset (Customer Support)</option>
                <option value="fa-code">fa-code (Programming / Technical)</option>
                <option value="fa-dharmachakra">fa-dharmachakra (Wheel / Spiritual)</option>
              </select>
            </div>
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
    const pb = HP.data.find(p => p.meta && p.meta.id === pid);
    if (!pb) return;
    const meta = pb.meta || {};
    const chatRole = pb.chat_role || {};
    const currentMode = meta.mode || pb.mode || 'training';

    const modal = document.getElementById('pb-modal-container');
    if (!modal) return;

    modal.innerHTML = `
      <div class="pb-modal-overlay" onclick="if(event.target === this) window.pbCloseModal()">
        <div class="pb-modal-box" style="max-width: 580px; width: 94%;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
            <h3 style="margin:0; font-size:16px; color:var(--text, #fff); display:flex; align-items:center; gap:8px;">
              <i class="fas fa-pen" style="color:#60a5fa;"></i> Edit Playbook
            </h3>
            <button onclick="window.pbCloseModal()" style="background:none; border:none; color:var(--muted); font-size:16px; cursor:pointer;">&times;</button>
          </div>

          <div style="margin-bottom:14px;">
            <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;">Playbook Name</label>
            <input type="text" id="pb-edit-name" value="${HP.escapeHtml(meta.name || '')}" style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;">
          </div>

          <div style="margin-bottom:14px;">
            <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;">Description</label>
            <input type="text" id="pb-edit-desc" value="${HP.escapeHtml(meta.description || '')}" style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;">
          </div>

          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-bottom:16px;">
            <div>
              <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;" title="Operating mode: defines how Chat and Presenter collaborate">
                Operating Mode <i class="fas fa-info-circle" style="color:#60a5fa; font-size:10px;"></i>
              </label>
              <select id="pb-edit-mode" style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;" title="Choose playbook operating mode">
                <option value="training" ${currentMode === 'training' ? 'selected' : ''} title="Training: Chat plays the counterpart (e.g. customer, passerby) and Presenter coaches you with real-time tips">🎯 Training / Coaching</option>
                <option value="roleplay" ${currentMode === 'roleplay' ? 'selected' : ''} title="Roleplay: Chat adopts a character or scenario for open simulation">🎭 Roleplay / Simulation</option>
                <option value="learning" ${currentMode === 'learning' ? 'selected' : ''} title="Learning: Targeted conversation to practice languages or professional skills">🎓 Language / Skills Learning</option>
                <option value="freestyle" ${currentMode === 'freestyle' ? 'selected' : ''} title="Freestyle: General directives and reference knowledge without rigid roles">📖 Freestyle (General Knowledge)</option>
              </select>
            </div>
            <div>
              <label style="display:block; font-size:12px; font-weight:600; color:var(--muted); margin-bottom:6px;">FontAwesome Icon</label>
              <input type="text" id="pb-edit-icon" value="${HP.escapeHtml(meta.icon || 'fa-book-open')}" style="width:100%; box-sizing:border-box; padding:8px 12px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:13px; outline:none;">
            </div>
          </div>

          <!-- Chat Role Configuration Card -->
          <div style="background:rgba(59,130,246,0.06); border:1px solid rgba(59,130,246,0.22); border-radius:8px; padding:12px; margin-bottom:18px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
              <label style="font-size:12px; font-weight:700; color:#93c5fd; display:flex; align-items:center; gap:6px; margin:0;" title="When enabled, the Chat model will adopt the role and persona defined below">
                <i class="fas fa-robot"></i> Chat Model Persona / Roleplay (Chat LLM)
              </label>
              <label class="switch" style="margin:0;" title="Enable/Disable roleplay prompt injection into the chat model">
                <input type="checkbox" id="pb-edit-chat-enabled" ${chatRole.enabled ? 'checked' : ''}>
                <span class="slider"></span>
              </label>
            </div>
            <div style="font-size:11px; color:var(--muted); margin-bottom:8px;">
              Directives instructing the conversational Chat AI (e.g., Urania) what persona or stance to adopt during interaction:
            </div>
            <textarea id="pb-edit-chat-brief" placeholder="E.g., You are a curious but skeptical passerby who has encountered a street preacher..." style="width:100%; box-sizing:border-box; padding:8px 10px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:12px; min-height:68px; resize:vertical; outline:none; font-family:inherit;">${HP.escapeHtml(chatRole.brief || '')}</textarea>
            <div style="display:flex; align-items:center; gap:8px; margin-top:8px;">
              <span style="font-size:11px; color:var(--muted); font-weight:600;" title="Psychological resistance level the Chat model exerts during conversation">Difficulty / Resistance:</span>
              <select id="pb-edit-chat-diff" style="padding:4px 8px; border-radius:6px; background:#0f172a; border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:11px; outline:none;" title="Adjusts how receptive or resistant the chat counterpart is">
                <option value="easy" ${chatRole.difficulty === 'easy' ? 'selected' : ''} title="Easy: Receptive and readily persuaded or compliant">Easy (Receptive / Compliant)</option>
                <option value="medium" ${(chatRole.difficulty || 'medium') === 'medium' ? 'selected' : ''} title="Medium: Balanced and skeptical, requires convincing arguments">Medium (Skeptical / Balanced)</option>
                <option value="hard" ${chatRole.difficulty === 'hard' ? 'selected' : ''} title="Hard: Strong pushback, highly argumentative and resistant">Hard (Strong Resistance)</option>
                <option value="expert" ${chatRole.difficulty === 'expert' ? 'selected' : ''} title="Expert: Extreme pushback, intensely scrutinizes and challenges every dogma">Expert (Maximum Challenge)</option>
              </select>
            </div>
          </div>

          <div style="display:flex; justify-content:flex-end; gap:10px;">
            <button class="pb-btn pb-btn-outline" onclick="window.pbCloseModal()">Cancel</button>
            <button class="pb-btn pb-btn-primary" onclick="window.pbSubmitEdit('${HP.escapeHtml(pid)}')">Save Changes</button>
          </div>
        </div>
      </div>
    `;
  };

  window.pbSubmitCreate = function() {
    const nameEl = document.getElementById('pb-create-name');
    const descEl = document.getElementById('pb-create-desc');
    const iconEl = document.getElementById('pb-create-icon');
    const modeEl = document.getElementById('pb-create-mode');

    const name = nameEl ? nameEl.value.trim() : '';
    const desc = descEl ? descEl.value.trim() : '';
    const icon = iconEl ? iconEl.value : 'fa-book-open';
    const mode = modeEl ? modeEl.value : 'training';

    if (!name) {
      alert('Please enter a name for the Playbook');
      return;
    }

    fetch('/api/ext/presenter/playbooks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, description: desc, icon: icon, mode: mode })
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        if (data.playbook && data.playbook.meta && data.playbook.meta.id) {
          HP.selectedPlaybookId = data.playbook.meta.id;
        }
        window.pbCloseModal();
        window.pbReloadList();
        if (typeof HP.notifyPresenterChange === 'function') HP.notifyPresenterChange();
        HP.showNotification('Playbook created successfully!', 'success');
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
    const modeEl = document.getElementById('pb-edit-mode');
    const chatEnEl = document.getElementById('pb-edit-chat-enabled');
    const chatBriefEl = document.getElementById('pb-edit-chat-brief');
    const chatDiffEl = document.getElementById('pb-edit-chat-diff');

    const name = nameEl ? nameEl.value.trim() : '';
    const desc = descEl ? descEl.value.trim() : '';
    const icon = iconEl ? iconEl.value.trim() : 'fa-book-open';
    const mode = modeEl ? modeEl.value : 'training';
    const chatEnabled = chatEnEl ? chatEnEl.checked : false;
    const chatBrief = chatBriefEl ? chatBriefEl.value.trim() : '';
    const chatDiff = chatDiffEl ? chatDiffEl.value : 'medium';

    if (!name) {
      alert('Please enter a name for the Playbook');
      return;
    }

    fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        description: desc,
        icon: icon,
        mode: mode,
        chat_role: {
          enabled: chatEnabled,
          brief: chatBrief,
          difficulty: chatDiff
        }
      })
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        window.pbCloseModal();
        window.pbReloadList();
        if (typeof HP.notifyPresenterChange === 'function') HP.notifyPresenterChange();
        HP.showNotification('Playbook updated successfully!', 'success');
      } else {
        alert(data.error || 'Failed to update playbook');
      }
    })
    .catch(() => alert('Network error'));
  };

  window.pbDeletePlaybook = function(pid) {
    const pb = HP.data.find(p => p.meta && p.meta.id === pid);
    const name = pb && pb.meta ? pb.meta.name : 'this Playbook';
    if (!confirm(`Are you sure you want to delete "${name}"? This cannot be undone.`)) return;

    fetch(`/api/ext/presenter/playbooks/${encodeURIComponent(pid)}`, {
      method: 'DELETE'
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        if (HP.selectedPlaybookId === pid) {
          HP.selectedPlaybookId = null;
        }
        window.pbReloadList();
        if (typeof HP.notifyPresenterChange === 'function') HP.notifyPresenterChange();
        HP.showNotification('Playbook deleted', 'success');
      } else {
        HP.showNotification(data.error || 'Failed to delete playbook', 'error');
      }
    })
    .catch(() => HP.showNotification('Network error', 'error'));
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
        if (data.playbook && data.playbook.meta && data.playbook.meta.id) {
          HP.selectedPlaybookId = data.playbook.meta.id;
        }
        window.pbReloadList();
        if (typeof HP.notifyPresenterChange === 'function') HP.notifyPresenterChange();
        HP.showNotification('Template installed successfully!', 'success');
      } else {
        HP.showNotification(data.error || 'Failed to install template', 'error');
      }
    })
    .catch(() => HP.showNotification('Network error', 'error'));
  };

  window.pbPreviewContext = async function(initialTarget) {
    const modal = document.getElementById('pb-modal-container');
    if (!modal) return;

    const currentTarget = initialTarget || 'presenter';

    modal.innerHTML = `
      <div class="pb-modal-overlay" onclick="if(event.target === this) window.pbCloseModal()">
        <div class="pb-modal-box" style="max-width: 720px; width: 92%;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <h3 style="margin:0; font-size:16px; color:var(--text, #fff); display:flex; align-items:center; gap:8px;">
              <i class="fas fa-eye" style="color:#60a5fa;"></i> Injected Context Preview
            </h3>
            <button onclick="window.pbCloseModal()" style="background:none; border:none; color:var(--muted); font-size:16px; cursor:pointer;">&times;</button>
          </div>

          <!-- Target Selector Pill Buttons -->
          <div style="display:flex; align-items:center; gap:8px; margin-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:10px;">
            <button id="pb-prev-btn-presenter" class="pb-btn ${currentTarget === 'presenter' ? 'pb-btn-primary' : 'pb-btn-outline'}" style="padding:4px 12px; font-size:11px;" onclick="window.pbFetchPreviewContext('presenter')">
              <i class="fas fa-microphone"></i> Presenter Context
            </button>
            <button id="pb-prev-btn-chat" class="pb-btn ${currentTarget === 'chat' ? 'pb-btn-primary' : 'pb-btn-outline'}" style="padding:4px 12px; font-size:11px;" onclick="window.pbFetchPreviewContext('chat')">
              <i class="fas fa-robot"></i> Chat LLM Context
            </button>
            <button id="pb-prev-btn-all" class="pb-btn ${currentTarget === 'all' ? 'pb-btn-primary' : 'pb-btn-outline'}" style="padding:4px 12px; font-size:11px;" onclick="window.pbFetchPreviewContext('all')">
              <i class="fas fa-layer-group"></i> Combined (All)
            </button>
          </div>

          <div id="pb-preview-desc" style="font-size:12px; color:var(--muted); margin-bottom:10px;">
            Active playbook content compiled and injected into the AI prompt.
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

    window.pbFetchPreviewContext(currentTarget);
  };

  window.pbFetchPreviewContext = async function(target) {
    const bodyEl = document.getElementById('pb-preview-body');
    const tokEl = document.getElementById('pb-preview-tokens');
    const descEl = document.getElementById('pb-preview-desc');
    const btnPres = document.getElementById('pb-prev-btn-presenter');
    const btnChat = document.getElementById('pb-prev-btn-chat');
    const btnAll = document.getElementById('pb-prev-btn-all');

    if (btnPres) btnPres.className = `pb-btn ${target === 'presenter' ? 'pb-btn-primary' : 'pb-btn-outline'}`;
    if (btnChat) btnChat.className = `pb-btn ${target === 'chat' ? 'pb-btn-primary' : 'pb-btn-outline'}`;
    if (btnAll) btnAll.className = `pb-btn ${target === 'all' ? 'pb-btn-primary' : 'pb-btn-outline'}`;

    if (descEl) {
      if (target === 'chat') {
        descEl.innerHTML = 'Compiled material injected into the <strong>Chat Model</strong> system prompt (Urania, etc.), including roleplay briefs and chat-targeted tabs.';
      } else if (target === 'all') {
        descEl.innerHTML = 'Showing both the <strong>Presenter</strong> and <strong>Chat Model</strong> contexts compiled side-by-side.';
      } else {
        descEl.innerHTML = 'Compiled material injected into the <strong>Presenter AI</strong> observer/commentary prompt.';
      }
    }

    if (bodyEl) {
      bodyEl.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Compiling active context...';
    }

    try {
      const res = await fetch(`/api/ext/presenter/playbooks/context?target=${encodeURIComponent(target)}`);
      const data = await res.json();
      if (data.ok) {
        if (bodyEl) {
          bodyEl.textContent = data.context || '(No active playbook content configured for this target. Ensure playbook tabs are enabled with content.)';
        }
        if (tokEl) {
          tokEl.textContent = `Estimated Tokens: ~${data.approx_tokens || 0}`;
        }
      } else {
        if (bodyEl) bodyEl.textContent = 'Error: ' + (data.error || 'Failed to compile');
      }
    } catch (e) {
      if (bodyEl) bodyEl.textContent = 'Connection error.';
    }
  };
})(window.HecosPlaybooks);
