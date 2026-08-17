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

    
})();
