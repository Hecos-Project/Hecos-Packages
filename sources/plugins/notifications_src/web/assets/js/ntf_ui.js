(function() {
    'use strict';

    // ── Render ────────────────────────────────────────────────────────────────
        window.renderPanel = function() {
            // Master switch
            const sw = document.getElementById('notifications-master-switch');
            if (sw) sw.checked = window.ntfConfig.enabled;

            // Add buttons
            window.renderAddButtons();

            // Destinations
            window.renderDestinations();

            // Rules
            window.renderRules();

            // History
            if (typeof window.ntfLoadHistory === 'function') {
                window.ntfLoadHistory();
            }
            // Live log
            window._ntfStartLogStream();
        }

        window.renderAddButtons = function() {
            const container = document.getElementById('ntf-add-buttons');
            if (!container) return;
            container.innerHTML = '';

            // Add Contact Import Button
            const importBtn = document.createElement('button');
            importBtn.className = 'btn btn-secondary';
            importBtn.style.cssText = 'padding:4px 10px; font-size:12px; margin-right: 6px;';
            importBtn.innerHTML = `<i class="fas fa-users"></i> Import from Contacts`;
            importBtn.onclick = () => window.ntfOpenContactsModal();
            container.appendChild(importBtn);

            if (window.ntfAvailablePlugins.length === 0) {
                return;
            }

            window.ntfAvailablePlugins.forEach(plug => {
                const btn = document.createElement('button');
                btn.className = 'btn btn-secondary';
                btn.style.cssText = 'padding:4px 10px; font-size:12px;';
                btn.innerHTML = `<i class="${plug.icon}"></i> + ${plug.label}`;
                btn.onclick = () => window.ntfAddDestination(plug);
                container.appendChild(btn);
            });
        }

        window.renderDestinations = function() {
            const container = document.getElementById('ntf-destinations-list');
            if (!container) return;

            const keys = Object.keys(window.ntfConfig.destinations);
            if (keys.length === 0) {
                container.innerHTML = '<div style="font-size:12px; color:var(--muted); font-style:italic; padding:8px 0;">No destinations configured. Add a contact using the buttons above.</div>';
                return;
            }

            container.innerHTML = '';
            keys.forEach(key => {
                const uri = window.ntfConfig.destinations[key];
                const plug = window.guessPluginFromUri(uri);
                const row = document.createElement('div');
                row.style.cssText = 'display:flex; gap:10px; align-items:center; margin-bottom:10px;';

                const iconHtml = uri.startsWith('CONTACT:') ? '<i class="fas fa-user-circle" style="color:var(--accent); width:24px; text-align:center; font-size:14px;"></i>' : (plug ? `<i class="${plug.icon}" style="color:var(--accent); width:24px; text-align:center; font-size:14px;"></i>` : '<i class="fas fa-bell" style="width:24px; text-align:center; font-size:14px;"></i>');
                const hintText = uri.startsWith('CONTACT:') ? 'CONTACT:uuid' : (plug ? plug.hint : 'MAIL:email@example.com');

                row.innerHTML = `
                    ${iconHtml}
                    <div style="flex:0 0 150px;">
                        <input type="text" value="${key}" placeholder="Contact ID (e.g. admin)"
                            class="config-input" style="width:100%; font-size:12px;"
                            onblur="window.ntfRenameKey('${key}', this.value)">
                    </div>
                    <div style="flex:1;">
                        <input type="text" value="${uri}" placeholder="${hintText}"
                            class="config-input" style="width:100%; font-size:12px;"
                            data-dest-key="${key}"
                            onblur="window.ntfUpdateUri('${key}', this.value)">
                    </div>
                    <button class="btn btn-secondary" title="Remove" style="padding:6px 10px; flex-shrink:0; border-radius:6px;"
                        onclick="window.ntfRemoveDest('${key}')"><i class="fas fa-trash"></i></button>
                `;
                container.appendChild(row);
            });
        }

        window.guessPluginFromUri = function(uri) {
            if (!uri) return null;
            const upper = uri.toUpperCase();
            return window.ntfAvailablePlugins.find(p => upper.startsWith(p.tag + ':')) || null;
        }


        window.renderRules = function() {
            const table = document.getElementById('ntf-rules-table');
            const select = document.getElementById('ntf-add-rule-select');
            if (!table || !select) return;

            table.innerHTML = '';
            select.innerHTML = '<option value="">-- Select an Event to Add --</option>';
        
            const destKeys = Object.keys(window.ntfConfig.destinations);
            let activeRulesCount = 0;

            window.ntfEventDefs.forEach(evt => {
                const selectedKeys = window.ntfConfig.rules[evt.id] || [];
                const selectedTpl = window.ntfConfig.event_templates[evt.id] || "";
            
                // Check if rule is active (has destinations or a template, or is forcefully added)
                // For now, if it has any configuration, it's active.
                const isActive = selectedKeys.length > 0 || selectedTpl !== "";
            
                // Allow forceful showing via a temporary Set if needed, 
                // but we can just use the state variable.
                if (!isActive && !window._ntfActiveEvents?.has(evt.id)) {
                    // Add to dropdown
                    select.innerHTML += `<option value="${evt.id}">${evt.label}</option>`;
                    return;
                }
            
                activeRulesCount++;

                const tr = document.createElement('tr');
                tr.style.borderBottom = '1px solid var(--border)';

                let selectCell;


                if (destKeys.length === 0) {
                    selectCell = `<span style="font-size:11px; color:var(--muted);">Add a destination first</span>`;
                } else {
                    let opts = destKeys.map(k => {
                        const sel = selectedKeys.includes(k) ? 'selected' : '';
                        const plug = window.guessPluginFromUri(window.ntfConfig.destinations[k]);
                        const icon = plug ? plug.tag : '?';
                        return `<option value="${k}" ${sel}>[${icon}] ${k}</option>`;
                    }).join('');
                    selectCell = `<div style="display:flex; flex-direction:column; gap:6px;">
                        <select multiple class="config-input" style="width:100%; min-height:60px; padding:4px;"
                        onchange="window.ntfUpdateRule('${evt.id}', this)">${opts}</select>`;
                    
                    // Template Selector
                    let tplOpts = `<option value="">-- Nessun Template (Plain Text) --</option>`;
                    window.ntfAvailableTemplates.forEach(tpl => {
                        const sel = (tpl.id === selectedTpl) ? 'selected' : '';
                        tplOpts += `<option value="${tpl.id}" ${sel}>${tpl.name}</option>`;
                    });
                    selectCell += `<select class="config-input" style="width:100%; padding:4px;" onchange="window.ntfUpdateTemplate('${evt.id}', this.value)">${tplOpts}</select></div>`;

                }


                tr.innerHTML = `
                    <td style="padding:10px 8px; font-weight:600;">${evt.label}</td>
                    <td style="padding:10px 8px; color:var(--muted); font-size:12px;">${evt.desc}</td>
                    <td style="padding:10px 8px;">${selectCell}</td>
                    <td style="padding:10px 8px; text-align:right;">
                        <button class="btn btn-sm btn-secondary" onclick="window.ntfRemoveRule('${evt.id}')" title="Remove Rule"><i class="fas fa-trash" style="color:var(--error);"></i></button>
                    </td>
                `;
                table.appendChild(tr);
            });
        
            if (activeRulesCount === 0) {
                table.innerHTML = '<tr><td colspan="4" style="padding:15px 8px; color:var(--muted); font-style:italic; font-size:12px; text-align:center;">No event rules configured. Add one from the menu above.</td></tr>';
            }
        }

    
    // ── Actions ───────────────────────────────────────────────────────────────

        window._ntfActiveEvents = new Set();
    
        window.ntfAddRule = function() {
            const select = document.getElementById('ntf-add-rule-select');
            const evtId = select.value;
            if (!evtId) return;
        
            window._ntfActiveEvents.add(evtId);
            window.renderRules();
        };
    
        window.ntfRemoveRule = async function(evtId) {
            if (await window.ntfConfirm(`Are you sure you want to remove the rule for '${evtId}'?`)) {
                window._ntfActiveEvents.delete(evtId);
                window.ntfConfig.rules[evtId] = [];
                window.ntfConfig.event_templates[evtId] = "";
                window.renderRules();
                window.ntfSaveQuiet();
            }
        };


        window.ntfUpdateTemplate = function(evtId, tplId) {
            window.ntfConfig.event_templates[evtId] = tplId;
            window.ntfSaveQuiet();
        };

    
    window.ntfAddDestination = function(plug) {
            const key = (plug.tag.toLowerCase()) + '_' + Date.now().toString().slice(-4);
            const prefix = plug.platform
                ? `${plug.tag}:${plug.platform}:`
                : `${plug.tag}:`;
            window.ntfConfig.destinations[key] = prefix;
            window.renderDestinations();
            window.renderRules();
            window.ntfSaveQuiet();
        };

        window.ntfRenameKey = function(oldKey, newKey) {
            newKey = newKey.trim();
            if (!newKey || oldKey === newKey) return;
            if (window.ntfConfig.destinations[newKey] !== undefined) {
                window.ntfToast('Contact ID already exists!', true);
                window.renderDestinations();
                return;
            }
            window.ntfConfig.destinations[newKey] = window.ntfConfig.destinations[oldKey];
            delete window.ntfConfig.destinations[oldKey];
            // Update rules
            for (const evtId in window.ntfConfig.rules) {
                window.ntfConfig.rules[evtId] = (window.ntfConfig.rules[evtId] || []).map(k => k === oldKey ? newKey : k);
            }
            window.renderDestinations();
            window.renderRules();
            window.ntfSaveQuiet();
        };

        window.ntfUpdateUri = function(key, newUri) {
            window.ntfConfig.destinations[key] = newUri;
            window.renderDestinations();
            window.renderRules();
            window.ntfSaveQuiet();
        };

        window.ntfRemoveDest = async function(key) {
            const ok = await window.ntfConfirm(`Remove destination "${key}"?`, 'Remove');
            if (!ok) return;
            delete window.ntfConfig.destinations[key];
            for (const evtId in window.ntfConfig.rules) {
                window.ntfConfig.rules[evtId] = (window.ntfConfig.rules[evtId] || []).filter(k => k !== key);
            }
            window.renderDestinations();
            window.renderRules();
            window.ntfSaveQuiet();
        };

        window.ntfUpdateRule = function(evtId, selectElem) {
            window.ntfConfig.rules[evtId] = Array.from(selectElem.selectedOptions).map(o => o.value);
            window.ntfSaveQuiet();
        };

    
})();
