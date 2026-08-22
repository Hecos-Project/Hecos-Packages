(function() {
    'use strict';

    // ── Inline modal (no external dependency) ────────────────────────────────
        window._ntfModalResolve = null;
        window.ntfConfirm = function(msg, confirmLabel) {
            return new Promise(resolve => {
                document.getElementById('ntf-confirm-text').textContent = msg;
                if (confirmLabel) document.getElementById('ntf-confirm-ok').textContent = confirmLabel;
                const modal = document.getElementById('ntf-confirm-modal');
                modal.style.display = 'flex';
                window._ntfModalResolve = (result) => {
                    modal.style.display = 'none';
                    resolve(result);
                };
            });
        }

        window.ntfToast = function(msg, isError) {
            if (window.showToast) {
                window.showToast(msg, isError ? 'error' : 'success');
            } else {
                console.log('[NTF]', msg);
            }
        }

        window.setSaveStatus = function(msg, isOk) {
            const el = document.getElementById('ntf-save-status');
            if (el) {
                el.textContent = msg;
                el.style.color = isOk ? 'var(--accent)' : '#ff6b6b';
            }
        }

    
    window.ntfAllContacts = [];
        window.ntfOpenContactsModal = async function() {
            document.getElementById('ntf-contacts-modal').style.display = 'flex';
            document.getElementById('ntf-contacts-search').value = '';
            const list = document.getElementById('ntf-contacts-list');
            list.innerHTML = '<div style="font-size:12px; color:var(--muted); font-style:italic;">Loading...</div>';
            try {
                const res = await fetch('/api/contacts?limit=500');
                const data = await res.json();
                if (data.ok) {
                    window.ntfAllContacts = data.contacts;
                    window.ntfRenderContacts(window.ntfAllContacts);
                }
            } catch(e) {
                list.innerHTML = '<div style="color:#ffaa44; font-size:12px;">Failed to load contacts.</div>';
            }
        };

        window.ntfSearchContacts = function(q) {
            if (!q) return window.ntfRenderContacts(window.ntfAllContacts);
            q = q.toLowerCase();
            const filtered = window.ntfAllContacts.filter(c => (c.display_name || '').toLowerCase().includes(q) || (c.first_name || '').toLowerCase().includes(q));
            window.ntfRenderContacts(filtered);
        };

        window.ntfRenderContacts = function(contacts) {
            const list = document.getElementById('ntf-contacts-list');
            list.innerHTML = '';
            if (contacts.length === 0) {
                list.innerHTML = '<div style="font-size:12px; color:var(--muted); font-style:italic;">No contacts found.</div>';
                return;
            }
            contacts.forEach(c => {
                const div = document.createElement('div');
                div.style.cssText = 'padding:10px; background:var(--glass); border:1px solid var(--border); border-radius:8px; display:flex; justify-content:space-between; align-items:center; cursor:pointer; transition:0.2s;';
                div.onmouseover = () => div.style.borderColor = 'var(--accent)';
                div.onmouseout = () => div.style.borderColor = 'var(--border)';
                div.onclick = () => {
                    document.getElementById('ntf-contacts-modal').style.display = 'none';
                    window.ntfAddContactDestination(c);
                };
            
                const name = c.display_name || (c.first_name + ' ' + (c.last_name || '')).trim();
                div.innerHTML = `
                    <div style="font-weight:600; font-size:13px;"><i class="fas fa-user" style="color:var(--muted); margin-right:8px;"></i> ${name}</div>
                    <button class="btn btn-sm btn-secondary">Select</button>
                `;
                list.appendChild(div);
            });
        }

        window.ntfAddContactDestination = function(c) {
            const nameClean = (c.first_name || 'Contact').toLowerCase().replace(/[^a-z0-9]/g, '');
            const key = nameClean + '_' + Date.now().toString().slice(-4);
            window.ntfConfig.destinations[key] = "CONTACT:" + c.id;
            window.renderDestinations();
            window.renderRules();
            window.ntfSaveQuiet();
        }

    
    // ── Test ──────────────────────────────────────────────────────────────────
        window.ntfTest = async function() {
            // Populate template dropdown in test modal
            const sel = document.getElementById('ntf-test-template-select');
            if (sel && window.ntfAvailableTemplates.length) {
                // Keep the first empty option, then add templates
                sel.innerHTML = '<option value="">-- No Template (Plain Text) --</option>';
                window.ntfAvailableTemplates.forEach(tpl => {
                    sel.innerHTML += `<option value="${tpl.id}">${tpl.name}</option>`;
                });
            }
            const modal = document.getElementById('ntf-test-modal');
            if (modal) modal.style.display = 'flex';
        };

        window.ntfSendTest = async function() {
            const modal = document.getElementById('ntf-test-modal');
            const templateId = document.getElementById('ntf-test-template-select')?.value || '';
            if (modal) modal.style.display = 'none';
            try {
                const res = await fetch('/hecos/api/plugins/notifications/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ template_id: templateId })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    window.ntfToast('Test notification dispatched!');
                    setTimeout(() => window.ntfLoadHistory(), 1000);
                } else {
                    window.ntfToast('Error: ' + (data.message || 'Unknown error'), true);
                }
            } catch(e) {
                window.ntfToast('Network error during test.', true);
            }
        };

    
    // -- Universal Composer -----------------------------------------------------
    window._ntfComposerMode = null; // 'adhoc' or 'event'
    window._ntfComposerEventId = null;

    window.ntfOpenAdHocComposer = function() {
        window._ntfComposerMode = 'adhoc';
        window._ntfComposerEventId = null;
        
        document.getElementById('ntf-compose-title').innerHTML = '<i class="fas fa-paper-plane"></i> Send Ad-Hoc Notification';
        document.getElementById('ntf-compose-destinations-section').style.display = 'block';
        document.getElementById('ntf-compose-btn-send').style.display = 'inline-block';
        document.getElementById('ntf-compose-btn-bind').style.display = 'none';
        // Show event-only section (we now use it for ad-hoc overrides too)
        const senderSection = document.getElementById('ntf-compose-sender-section');
        if (senderSection) senderSection.style.display = 'block';
        
        _ntfInitComposerState();
    };

    window.ntfOpenEventComposer = function(evtId) {
        window._ntfComposerMode = 'event';
        window._ntfComposerEventId = evtId;
        
        document.getElementById('ntf-compose-title').innerHTML = '<i class="fas fa-edit"></i> Configure Event: <span style="color:var(--accent);">' + evtId + '</span>';
        document.getElementById('ntf-compose-destinations-section').style.display = 'none';
        document.getElementById('ntf-compose-btn-send').style.display = 'none';
        document.getElementById('ntf-compose-btn-bind').style.display = 'inline-block';
        // Show sender override for event mode
        const senderSection = document.getElementById('ntf-compose-sender-section');
        if (senderSection) senderSection.style.display = 'block';
        
        _ntfInitComposerState(evtId);
    };

    function _ntfInitComposerState(evtId = null) {
        const modal = document.getElementById('ntf-compose-modal');
        if (!modal) return;
        
        // Populate templates
        const tplSelect = document.getElementById('ntf-compose-template');
        tplSelect.innerHTML = '<option value="">-- No Template (Plain Text) --</option>';
        window.ntfAvailableTemplates.forEach(tpl => {
            tplSelect.innerHTML += `<option value="${tpl.id}">${tpl.name} (${tpl.channel || 'all'})</option>`;
        });
        
        // Populate sender accounts as checkboxes
        const senderList = document.getElementById('ntf-compose-sender-list');
        if (senderList) {
            senderList.innerHTML = '';
            if (!window.ntfMailAccounts || window.ntfMailAccounts.length === 0) {
                senderList.innerHTML = '<div style="font-size:12px; color:var(--muted); font-style:italic;">No mail accounts found.</div>';
            } else {
                window.ntfMailAccounts.forEach(acc => {
                    const label = document.createElement('label');
                    label.style.cssText = 'display:flex; align-items:center; gap:8px; font-size:13px; cursor:pointer; padding:3px 0;';
                    const activeBadge = acc.is_active ? ' <span style="font-size:10px; background:var(--accent); color:#fff; border-radius:3px; padding:1px 5px; margin-left:4px;">active</span>' : '';
                    label.innerHTML = `
                        <input type="checkbox" class="ntf-sender-acc-cb" value="${acc.id}">
                        <span><strong>${acc.name || acc.id}</strong>${activeBadge} <span style="color:var(--muted); font-size:11px;">&lt;${acc.email}&gt;</span></span>
                    `;
                    senderList.appendChild(label);
                });
            }
        }

        if (evtId) {
            // Pre-fill existing event data
            const tplData = window.ntfConfig.event_templates[evtId];
            if (tplData) {
                const tplId = typeof tplData === 'string' ? tplData : tplData.template_id;
                // Load saved sender_accounts (new format) or legacy sender_account
                let savedAccounts = [];
                if (typeof tplData === 'object') {
                    if (Array.isArray(tplData.sender_accounts)) savedAccounts = tplData.sender_accounts;
                    else if (tplData.sender_account) savedAccounts = [tplData.sender_account];
                }
                tplSelect.value = tplId || '';
                // Pre-check saved accounts in the checkbox list
                if (senderList) {
                    senderList.querySelectorAll('.ntf-sender-acc-cb').forEach(cb => {
                        cb.checked = savedAccounts.includes(cb.value);
                    });
                }
                window.ntfComposeTemplateChanged(tplId || '');
                // Pre-fill variables after DOM generation
                setTimeout(() => {
                    if (typeof tplData === 'object' && tplData.variables) {
                        for (let k in tplData.variables) {
                            const el = document.getElementById('ntf-compose-var-' + k);
                            if (el) el.value = tplData.variables[k];
                        }
                    }
                }, 50);
            } else {
                tplSelect.value = '';
                window.ntfComposeTemplateChanged('');
            }
        } else {
            // Populate destinations for adhoc
            const destSelect = document.getElementById('ntf-compose-dests');
            if (destSelect) {
                destSelect.innerHTML = '';
                const destKeys = Object.keys(window.ntfConfig.destinations || {});
                if (destKeys.length === 0) {
                    destSelect.innerHTML = '<div style="font-size:12px; color:var(--muted); font-style:italic; padding:6px;">No destinations configured.</div>';
                } else {
                    destKeys.forEach(k => {
                        const uri = window.ntfConfig.destinations[k];
                        const plug = window.guessPluginFromUri ? window.guessPluginFromUri(uri) : null;
                        const icon = plug ? plug.tag : uri.split(':')[0];
                        destSelect.innerHTML += `
                            <label style="display:flex; align-items:center; gap:6px; font-size:13px; cursor:pointer; padding: 2px 4px;">
                                <input type="checkbox" value="${uri}" class="ntf-adhoc-dest-cb">
                                [${icon}] ${k}
                            </label>
                        `;
                    });
                }
            }
            tplSelect.value = '';
            window.ntfComposeTemplateChanged('');
        }
        
        modal.style.display = 'flex';
    }

    window.ntfComposeTemplateChanged = function(templateId) {
        const container = document.getElementById('ntf-compose-variables-container');
        container.innerHTML = '';
        
        let variables = ['subject', 'message']; // Always default to these two
        
        if (templateId) {
            const tpl = window.ntfAvailableTemplates.find(t => t.id === templateId);
            if (tpl && tpl.variables && tpl.variables.length > 0) {
                tpl.variables.forEach(v => {
                    if (!variables.includes(v)) variables.push(v);
                });
            } else if (tpl) {
                // Fallback regex extraction if variables array is missing
                const extract = (str) => {
                    if (!str) return;
                    const matches = str.match(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g);
                    if (matches) {
                        matches.forEach(m => {
                            const v = m.replace(/[\{\}\s]/g, '');
                            if (!variables.includes(v)) variables.push(v);
                        });
                    }
                };
                extract(tpl.subject || '');
                extract(tpl.body_html || '');
                extract(tpl.body_text || '');
            }
        }
        
        variables.forEach(v => {
            const isArea = v === 'message' || v === 'body' || v === 'body_text';
            const inputHtml = isArea 
                ? `<textarea id="ntf-compose-var-${v}" class="config-input" style="width:100%; min-height:80px;" placeholder="Value for {{ ${v} }}"></textarea>`
                : `<input type="text" id="ntf-compose-var-${v}" class="config-input" style="width:100%;" placeholder="Value for {{ ${v} }}">`;
                
            container.innerHTML += `
                <div>
                    <label style="font-size:12px; color:var(--muted); display:block; margin-bottom:5px; text-transform:capitalize;">${v.replace(/_/g, ' ')} <code style="color:var(--accent); background:rgba(0,0,0,0.2); padding:2px 4px; border-radius:4px;">{{ ${v} }}</code></label>
                    ${inputHtml}
                </div>
            `;
        });
        
        // Store the detected variables for later gathering
        window._ntfComposeActiveVars = variables;
    };

    window.ntfBindCompose = function() {
        const ev = window._ntfComposerEventId;
        const tplSelect = document.getElementById('ntf-compose-template');
        if (!ev) return;
        
        const variables = {};
        const container = document.getElementById('ntf-compose-variables-container');
        const inputs = container.querySelectorAll('.config-input');
        inputs.forEach(i => {
            const key = i.id.replace('ntf-compose-var-', '');
            variables[key] = i.value;
        });

        // Collect checked sender accounts from the checkbox list
        const checkedAccounts = Array.from(document.querySelectorAll('.ntf-sender-acc-cb:checked')).map(cb => cb.value);

        if (!window.ntfConfig.event_templates) window.ntfConfig.event_templates = {};
        window.ntfConfig.event_templates[ev] = {
            template_id: tplSelect.value || "",
            sender_accounts: checkedAccounts,  // array (empty = use global default)
            variables: variables
        };
        
        document.getElementById('ntf-compose-modal').style.display = 'none';
        window.ntfSaveQuiet();
        window.ntfToast('Event template binding saved!');
        if (window.renderRules) window.renderRules();
    };

    window.ntfSendCompose = async function() {
        const destSelect = document.getElementById('ntf-compose-dests');
        const tplSelect = document.getElementById('ntf-compose-template');
        
        const selectedDests = Array.from(destSelect.querySelectorAll('.ntf-adhoc-dest-cb:checked')).map(cb => cb.value);
        if (selectedDests.length === 0) {
            window.ntfToast('Please select at least one destination for Ad-Hoc sending.', true);
            return;
        }
        
        const templateId = tplSelect.value;
        const variables = {};
        
        let subject = "Hecos Notification";
        let message = "";
        
        if (window._ntfComposeActiveVars) {
            window._ntfComposeActiveVars.forEach(v => {
                const el = document.getElementById('ntf-compose-var-' + v);
                if (el) {
                    variables[v] = el.value;
                    if (v === 'subject' && el.value) subject = el.value;
                    if (v === 'message' && el.value) message = el.value;
                }
            });
        }
        
        document.getElementById('ntf-compose-modal').style.display = 'none';
        
        // Collect selected sender accounts for Ad-Hoc override
        const checkedAccounts = Array.from(document.querySelectorAll('.ntf-sender-acc-cb:checked')).map(cb => cb.value);

        try {
            const res = await fetch('/hecos/api/plugins/notifications/dispatch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    subject: subject,
                    message: message,
                    template_id: templateId,
                    variables: variables,
                    destinations: selectedDests,
                    sender_accounts: checkedAccounts
                })
            });

            
            if (!res.ok) {
                const errText = await res.text();
                throw new Error(`Server returned ${res.status}: ${errText}`);
            }
            
            const data = await res.json();
            if (data.status === 'success') {
                window.ntfToast('Custom Notification dispatched successfully!');
                setTimeout(() => { if(window.ntfLoadHistory) window.ntfLoadHistory(); }, 1000);
            } else {
                window.ntfToast('Error: ' + (data.message || 'Unknown error'), true);
            }
        } catch(e) {
            window.ntfToast('Dispatch Error: ' + e.message, true);
        }
    };
})();

// Cache Buster: 08/17/2026 07:43:56
