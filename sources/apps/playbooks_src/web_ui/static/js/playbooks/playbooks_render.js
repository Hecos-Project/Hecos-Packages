/**
 * Hecos Playbooks - Rendering Engine
 * Renders Level 1 navigation pills, card header, Level 2 tabs, and content editor.
 */
window.HecosPlaybooks = window.HecosPlaybooks || {};

(function(HP) {
  HP.getTargetInfo = function(target) {
    switch (target) {
      case 'chat':
        return {
          title: 'Chat LLM Only (Roleplay)',
          short: 'Chat LLM Only',
          desc: 'Injected ONLY into the Chat Model prompt (e.g. Urania) to adopt a specific persona, stance, or character. The Presenter does not receive this.',
          icon: 'fa-robot',
          color: '#38bdf8'
        };
      case 'both':
        return {
          title: 'Both (Presenter + Chat)',
          short: 'Presenter + Chat',
          desc: 'Injected into BOTH Presenter and Chat Model. Shared knowledge base, rules, dogmas, or general domain material.',
          icon: 'fa-layer-group',
          color: '#34d399'
        };
      case 'system':
        return {
          title: 'Reference Only (No AI)',
          short: 'Reference Only',
          desc: 'NOT injected into any AI model. Stored in the playbook as reference notes, personal draft, or documentation.',
          icon: 'fa-info-circle',
          color: '#94a3b8'
        };
      default: // presenter
        return {
          title: 'Presenter Only (Coach)',
          short: 'Presenter Only',
          desc: 'Injected ONLY into the Presenter sidebar as coaching directives and real-time guidance. The Chat model does not receive this.',
          icon: 'fa-microphone',
          color: '#c084fc'
        };
    }
  };

  HP.render = function(playbooks) {
    playbooks = playbooks || HP.data;
    const container = document.getElementById('playbooks-list');
    const selectorBar = document.getElementById('pb-selector-bar');
    const tabsContainer = document.getElementById('pb-selector-tabs');
    if (!container) return;

    HP.updateStats();

    if (!playbooks || playbooks.length === 0) {
      if (selectorBar) selectorBar.style.display = 'none';
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

    // Ensure selected playbook is valid
    if (!HP.selectedPlaybookId || !playbooks.some(p => p.meta && p.meta.id === HP.selectedPlaybookId)) {
      HP.selectedPlaybookId = playbooks[0].meta ? playbooks[0].meta.id : null;
    }

    // Render Playbook Selector Bar (Level 1 Tabs)
    if (selectorBar) selectorBar.style.display = 'flex';
    if (tabsContainer) {
      tabsContainer.innerHTML = playbooks.map(pb => {
        const meta = pb.meta || {};
        const pid = meta.id;
        const isActive = (pid === HP.selectedPlaybookId);
        const isHpm = (meta.source === 'hpm');
        const isEn = !!meta.enabled;
        const tabCount = (pb.tabs || []).length;
        return `
          <div class="pb-nav-tab ${isActive ? 'active' : ''}" onclick="window.pbSelectPlaybook('${HP.escapeHtml(pid)}')" title="${HP.escapeHtml(meta.name || 'Untitled')} (${tabCount} tabs)">
            <span class="pb-tab-status-dot ${isEn ? 'enabled' : 'disabled'}" title="${isEn ? 'Enabled in Prompt' : 'Disabled'}"></span>
            <i class="fas ${HP.escapeHtml(meta.icon || 'fa-book-open')} pb-tab-icon"></i>
            <span class="pb-tab-title">${HP.escapeHtml(meta.name || 'Untitled Playbook')}</span>
            <span class="pb-tab-badge-mini ${isHpm ? 'hpm' : 'local'}">${isHpm ? 'HPM' : 'Local'}</span>
          </div>
        `;
      }).join('');
    }
    HP.initTabsResizer();

    // Find and render ONLY the selected active playbook
    const pb = playbooks.find(p => p.meta && p.meta.id === HP.selectedPlaybookId) || playbooks[0];
    const meta = pb.meta || {};
    const tabs = pb.tabs || [];
    const pid = meta.id;
    const isHpm = (meta.source === 'hpm');
    const chatRole = pb.chat_role || {};
    const pbMode = meta.mode || pb.mode || 'training';

    if (!HP.activeTabMap[pid] && tabs.length > 0) {
      HP.activeTabMap[pid] = tabs[0].id;
    }
    const curTabId = HP.activeTabMap[pid];
    const curTab = tabs.find(t => t.id === curTabId) || tabs[0] || null;

    let playbookChars = 0;
    tabs.forEach(t => { if (t.enabled) playbookChars += (t.content || '').length; });
    const pbTokens = Math.round(playbookChars / 4);

    container.innerHTML = `
      <div class="pb-card pb-single-view" id="pb-card-${HP.escapeHtml(pid)}">
        <!-- Card Header -->
        <div class="pb-card-header">
          <div class="pb-card-title-group" style="cursor: default;">
            <div style="width:38px; height:38px; border-radius:10px; background:linear-gradient(135deg, rgba(59,130,246,0.2), rgba(139,92,246,0.15)); border:1px solid rgba(59,130,246,0.3); display:flex; align-items:center; justify-content:center; color:#60a5fa; font-size:16px;">
              <i class="fas ${HP.escapeHtml(meta.icon || 'fa-book-open')}"></i>
            </div>
            <div>
              <div style="font-weight:700; font-size:15px; color:var(--text, #fff); display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                ${HP.escapeHtml(meta.name || 'Untitled Playbook')}
                ${isHpm ? '<span class="pb-badge pb-badge-purple">HPM Package</span>' : '<span class="pb-badge pb-badge-blue">Local</span>'}
                <span class="pb-badge pb-badge-amber" style="text-transform: capitalize;"><i class="fas fa-sliders-h"></i> ${HP.escapeHtml(pbMode)}</span>
                ${chatRole && chatRole.enabled ? `<span class="pb-badge pb-badge-blue" title="${HP.escapeHtml(chatRole.brief || '')}"><i class="fas fa-robot"></i> Chat Role Active</span>` : ''}
                <span class="pb-badge pb-badge-green">${tabs.length} tabs</span>
                <span style="font-size:11px; font-weight:500; color:var(--muted);">~${pbTokens} tokens</span>
              </div>
              ${meta.description ? `<div style="font-size:12px; color:var(--muted); margin-top:2px;">${HP.escapeHtml(meta.description)}</div>` : ''}
            </div>
          </div>

          <div style="display:flex; align-items:center; gap:10px;">
            <!-- Master Toggle Switch -->
            <label class="switch" title="Enable / Disable this Playbook in AI commentary prompt" style="margin:0;">
              <input type="checkbox" ${meta.enabled ? 'checked' : ''} onchange="window.pbToggleEnabled('${HP.escapeHtml(pid)}', this.checked)">
              <span class="slider"></span>
            </label>

            <!-- Edit metadata -->
            <button class="pb-btn pb-btn-outline" style="padding:6px 10px;" onclick="window.pbOpenEditModal('${HP.escapeHtml(pid)}')" title="Edit Playbook Details">
              <i class="fas fa-pen"></i>
            </button>

            <!-- Export single Playbook -->
            <button class="pb-btn pb-btn-outline" style="padding:6px 10px;" onclick="window.pbExportSinglePlaybook('${HP.escapeHtml(pid)}')" title="Export this Playbook as ZIP">
              <i class="fas fa-file-export"></i>
            </button>

            <!-- Delete (local only) -->
            ${!isHpm ? `
              <button class="pb-btn pb-btn-outline" style="padding:6px 10px; color:#f87171; border-color:rgba(239,68,68,0.2);" onclick="window.pbDeletePlaybook('${HP.escapeHtml(pid)}')" title="Delete Playbook">
                <i class="fas fa-trash"></i>
              </button>
            ` : ''}
          </div>
        </div>

        <!-- Card Body (Tabs & Editor) -->
        <div class="pb-card-body">
          <!-- Tabs Navigation Bar (Level 2) -->
          <div class="pb-tabs-nav">
            ${tabs.map(t => {
              const tgt = t.target || 'presenter';
              let tgtBadge = '';
              if (tgt === 'chat') {
                tgtBadge = '<span class="pb-target-badge chat" title="Target: Chat Model"><i class="fas fa-robot"></i> Chat</span>';
              } else if (tgt === 'both') {
                tgtBadge = '<span class="pb-target-badge both" title="Target: Presenter & Chat"><i class="fas fa-layer-group"></i> Both</span>';
              } else if (tgt === 'system') {
                tgtBadge = '<span class="pb-target-badge system" title="Target: Reference Only"><i class="fas fa-info-circle"></i> Ref</span>';
              } else {
                tgtBadge = '<span class="pb-target-badge presenter" title="Target: Presenter Only"><i class="fas fa-microphone"></i> Presenter</span>';
              }
              return `
                <button class="pb-tab-pill ${t.id === curTabId ? 'active' : ''}" onclick="window.pbSelectTab('${HP.escapeHtml(pid)}', '${HP.escapeHtml(t.id)}')">
                  <i class="fas ${t.enabled ? 'fa-check-circle' : 'fa-circle'}" style="font-size:10px; color:${t.enabled ? '#34d399' : 'var(--muted)'};"></i>
                  ${HP.escapeHtml(t.name || 'Tab')}
                  ${tgtBadge}
                </button>
              `;
            }).join('')}

            ${!isHpm ? `
              <button class="pb-tab-pill" style="border-style:dashed; color:#60a5fa;" onclick="window.pbAddTab('${HP.escapeHtml(pid)}')">
                <i class="fas fa-plus"></i> Add Tab
              </button>
            ` : ''}
          </div>

          <!-- Tab Editor Content -->
          ${curTab ? `
            <div class="pb-editor-area">
              <div class="pb-editor-toolbar">
                <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
                  <strong style="color:var(--text, #fff); font-size:13px;">${HP.escapeHtml(curTab.name)}</strong>
                  <label style="display:inline-flex; align-items:center; gap:5px; font-size:11px; cursor:pointer; color:var(--muted); margin:0;">
                    <input type="checkbox" ${curTab.enabled ? 'checked' : ''} onchange="window.pbToggleTabEnabled('${HP.escapeHtml(pid)}', '${HP.escapeHtml(curTab.id)}', this.checked)">
                    Inject into Prompt
                  </label>

                  <!-- Target Selector Dropdown with Explanatory Tooltips -->
                  <div style="display:inline-flex; align-items:center; gap:6px;">
                    <span style="font-size:11px; color:var(--muted); font-weight:600;">Target:</span>
                    <select
                      id="pb-target-select-${HP.escapeHtml(pid)}-${HP.escapeHtml(curTab.id)}"
                      class="pb-target-select"
                      onchange="window.pbChangeTabTarget('${HP.escapeHtml(pid)}', '${HP.escapeHtml(curTab.id)}', this.value)"
                      title="Choose which AI component receives this tab: Presenter, Chat LLM, Both, or Reference Only"
                    >
                      <option value="presenter" ${(curTab.target || 'presenter') === 'presenter' ? 'selected' : ''} title="Presenter Only: Directives for the sidebar coach. The Chat Model will NOT see this tab.">
                        🎙️ Presenter Only (Coach AI)
                      </option>
                      <option value="chat" ${curTab.target === 'chat' ? 'selected' : ''} title="Chat LLM Only: Persona and roleplay instructions for conversational AI. The Presenter will NOT see this tab.">
                        🤖 Chat LLM Only (Roleplay Persona)
                      </option>
                      <option value="both" ${curTab.target === 'both' ? 'selected' : ''} title="Both: Shared knowledge base injected into both Presenter and Chat Model.">
                        ⚡ Both (Presenter + Chat)
                      </option>
                      <option value="system" ${curTab.target === 'system' ? 'selected' : ''} title="Reference Only: Stored in playbook for human reference, NOT injected into any AI prompt.">
                        ℹ️ Reference Only (No AI)
                      </option>
                    </select>

                    <!-- Interactive Tooltip Hover Card -->
                    <div class="pb-tooltip-container">
                      <span class="pb-tooltip-trigger" title="Detailed explanation of target destinations">
                        <i class="fas fa-question-circle"></i>
                      </span>
                      <div class="pb-tooltip-box">
                        <div style="font-weight:700; color:#60a5fa; margin-bottom:8px; font-size:12px; display:flex; align-items:center; gap:6px;">
                          <i class="fas fa-bullseye"></i> Tab Target Destination Guide:
                        </div>
                        <div style="margin-bottom:7px; line-height:1.4;">
                          <strong style="color:#c084fc;">🎙️ Presenter Only:</strong> Sent only to the sidebar coach. Ideal for coaching tips, sales advice, grammar corrections, or psychological profiling. The chat model is completely unaware of it.
                        </div>
                        <div style="margin-bottom:7px; line-height:1.4;">
                          <strong style="color:#38bdf8;">🤖 Chat LLM Only:</strong> Sent only to the chat model (e.g. Urania). Ideal for assigning a character, role, or stance (e.g., skeptical buyer, student, curious citizen). The coach does not read it.
                        </div>
                        <div style="margin-bottom:7px; line-height:1.4;">
                          <strong style="color:#34d399;">⚡ Both:</strong> Shared domain knowledge sent to both the Coach and the Chat model. Ideal for dogmas, rules, prices, or reference manuals.
                        </div>
                        <div style="line-height:1.4;">
                          <strong style="color:#94a3b8;">ℹ️ Reference Only:</strong> Notes and draft content stored in the editor that are <u>never</u> injected into any AI prompts.
                        </div>
                      </div>
                    </div>

                    <!-- Live Dynamic Explanation Hint -->
                    <span id="pb-target-hint-${HP.escapeHtml(pid)}-${HP.escapeHtml(curTab.id)}" class="pb-target-hint-pill" title="${HP.escapeHtml(HP.getTargetInfo(curTab.target || 'presenter').desc)}">
                      <span style="color:${HP.getTargetInfo(curTab.target || 'presenter').color}; font-weight:600;">
                        <i class="fas ${HP.getTargetInfo(curTab.target || 'presenter').icon}"></i> ${HP.getTargetInfo(curTab.target || 'presenter').short}
                      </span>
                    </span>
                  </div>
                </div>

                <div style="display:flex; align-items:center; gap:8px;">
                  ${!isHpm ? `
                    <button class="pb-btn pb-btn-outline" style="padding:3px 8px; font-size:11px;" onclick="window.pbRenameTab('${HP.escapeHtml(pid)}', '${HP.escapeHtml(curTab.id)}', '${HP.escapeHtml(curTab.name)}')">
                      <i class="fas fa-pen"></i> Rename
                    </button>
                    <button class="pb-btn pb-btn-outline" style="padding:3px 8px; font-size:11px; color:#f87171;" onclick="window.pbDeleteTab('${HP.escapeHtml(pid)}', '${HP.escapeHtml(curTab.id)}')">
                      <i class="fas fa-trash"></i>
                    </button>
                  ` : ''}
                </div>
              </div>

              <textarea
                id="pb-textarea-${HP.escapeHtml(pid)}-${HP.escapeHtml(curTab.id)}"
                class="pb-textarea"
                placeholder="Enter instructions, reference material, roleplay scripts, or behavioral guidelines..."
                oninput="window.pbOnTextareaInput('${HP.escapeHtml(pid)}', '${HP.escapeHtml(curTab.id)}', this.value)"
              >${HP.escapeHtml(curTab.content || '')}</textarea>

              <div class="pb-editor-footer">
                <div style="display:flex; align-items:center; gap:12px;">
                  <span id="pb-status-${HP.escapeHtml(pid)}-${HP.escapeHtml(curTab.id)}" style="color:#34d399;">
                    <i class="fas fa-check"></i> Saved
                  </span>
                  <span>Characters: <strong id="pb-chars-${HP.escapeHtml(pid)}-${HP.escapeHtml(curTab.id)}">${(curTab.content || '').length}</strong></span>
                  <span>Approx. Tokens: <strong id="pb-tokens-${HP.escapeHtml(pid)}-${HP.escapeHtml(curTab.id)}">~${Math.round((curTab.content || '').length / 4)}</strong></span>
                </div>

                <div>
                  <button class="pb-btn pb-btn-primary" style="padding:4px 10px; font-size:11px;" onclick="window.pbSaveTabContentNow('${HP.escapeHtml(pid)}', '${HP.escapeHtml(curTab.id)}')">
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
  };

  /**
   * Resizer drag handle & horizontal scroll logic for Level 1 Playbooks tab bar
   */
  HP.initTabsResizer = function() {
    const resizer = document.getElementById('pb-selector-resizer');
    const tabsContainer = document.getElementById('pb-selector-tabs');
    const selectorBar = document.getElementById('pb-selector-bar');
    if (!resizer || !tabsContainer || !selectorBar) return;

    // Apply saved height preference from localStorage
    const savedHeight = localStorage.getItem('hecos_pb_tabs_height');
    const parsedH = savedHeight ? parseInt(savedHeight, 10) : 0;
    if (parsedH && parsedH > 60) {
      tabsContainer.classList.add('multiline');
      tabsContainer.style.height = parsedH + 'px';
      tabsContainer.style.maxHeight = 'none';
    } else {
      tabsContainer.classList.remove('multiline');
      tabsContainer.style.height = '';
      tabsContainer.style.maxHeight = '';
    }

    // Enable horizontal mouse wheel scrolling in single-row mode
    if (!tabsContainer._wheelInitialized) {
      tabsContainer._wheelInitialized = true;
      tabsContainer.addEventListener('wheel', function(e) {
        if (!tabsContainer.classList.contains('multiline') && e.deltaY !== 0) {
          e.preventDefault();
          tabsContainer.scrollLeft += e.deltaY;
        }
      }, { passive: false });
    }

    if (resizer._resizerInitialized) return;
    resizer._resizerInitialized = true;

    let startY = 0;
    let startHeight = 0;

    const onMouseMove = function(e) {
      const deltaY = e.clientY - startY;
      const targetH = startHeight + deltaY;

      if (targetH > 60) {
        // Multi-line expanded mode
        tabsContainer.classList.add('multiline');
        const clamped = Math.min(500, targetH);
        tabsContainer.style.height = clamped + 'px';
        tabsContainer.style.maxHeight = 'none';
      } else {
        // Single-row collapsed mode
        tabsContainer.classList.remove('multiline');
        tabsContainer.style.height = '';
        tabsContainer.style.maxHeight = '';
      }
    };

    const onMouseUp = function(e) {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      resizer.classList.remove('dragging');
      selectorBar.classList.remove('resizing');

      // Persist user preference
      if (tabsContainer.classList.contains('multiline') && tabsContainer.offsetHeight > 60) {
        localStorage.setItem('hecos_pb_tabs_height', tabsContainer.offsetHeight.toString());
      } else {
        localStorage.removeItem('hecos_pb_tabs_height');
      }
    };

    resizer.addEventListener('mousedown', function(e) {
      e.preventDefault();
      startY = e.clientY;
      startHeight = tabsContainer.offsetHeight;
      resizer.classList.add('dragging');
      selectorBar.classList.add('resizing');
      document.body.style.cursor = 'ns-resize';
      document.body.style.userSelect = 'none';
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });

    // Double-click to reset back to natural single-row auto height
    resizer.addEventListener('dblclick', function(e) {
      e.preventDefault();
      tabsContainer.classList.remove('multiline');
      tabsContainer.style.height = '';
      tabsContainer.style.maxHeight = '';
      localStorage.removeItem('hecos_pb_tabs_height');
    });
  };
})(window.HecosPlaybooks);
