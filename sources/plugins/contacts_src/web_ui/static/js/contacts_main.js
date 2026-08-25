/* ──────────────────────────────────────────────
   Contacts Module - Main / Init
   Served at: /ext/contacts/static/js/contacts_main.js
   ────────────────────────────────────────────── */
(function () {
    'use strict';

    window.contactsUI = window.contactsUI || {};

    /* ══════════════════════════════════════════
       DELETE
       ══════════════════════════════════════════ */
    window.contactsUI.del = function(id, name) {
        window.contactsUI.showConfirm(`${window.contactsUI.t('chat_confirm_delete')} ${name}?`, async () => {
            try {
                const res = await fetch(`/api/contacts/${id}`, { method: 'DELETE' });
                const data = await res.json();
                if (!data.ok) throw new Error(data.error);
                window.contactsUI.load();
            } catch (e) {
                window.contactsUI.showAlert(`${window.contactsUI.t('ext_calendar_msg_error') || 'Error'}: ${e.message}`);
            }
        });
    };

    /* ══════════════════════════════════════════
       INIT
       ══════════════════════════════════════════ */
    window.contactsUI.init = function() {
        const inp = document.getElementById('contacts-search-input');
        if (inp) {
            inp.addEventListener('input', e => {
                clearTimeout(window.contactsUI._state.searchTimeout);
                window.contactsUI._state.searchTimeout = setTimeout(() => {
                    if (window.contactsUI.load) window.contactsUI.load(e.target.value.trim());
                }, 300);
            });
        }
        
        // Color Picker Init
        const nativePicker = document.getElementById('c-color-native');
        if (typeof window.ColorPicker !== 'undefined') {
            const pickerWrap = document.getElementById('c-color-picker');
            if (pickerWrap) {
                window.contactsUI._state.picker = new window.ColorPicker({
                    el: pickerWrap,
                    colors: ['#ef4444','#f97316','#f59e0b','#84cc16','#22c55e','#06b6d4','#3b82f6','#6366f1','#8b5cf6','#d946ef','#f43f5e','#94a3b8'],
                    defaultColor: '#6366f1'
                });
            }
        } else if (nativePicker) {
            nativePicker.style.display = 'block';
            nativePicker.style.width = '100%';
            nativePicker.style.height = '40px';
            nativePicker.style.cursor = 'pointer';
            nativePicker.style.border = 'none';
        }

        // Setup Escape key for modal
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                const lb = document.getElementById('contact-photo-lightbox');
                if (lb && lb.classList.contains('active')) {
                    lb.classList.remove('active');
                } else if (document.getElementById('contact-modal')?.classList.contains('open')) {
                    if (window.contactsUI.closeForm) window.contactsUI.closeForm();
                }
            }
        });
    };

    /* ══════════════════════════════════════════
       AUTO-START
       ══════════════════════════════════════════ */
    window.contactsUI.init();

    // Observe tab changes if contacts is in a tab
    const obs = new MutationObserver(m => {
        m.forEach(rec => {
            if (rec.target.id === 'tab-contacts' && rec.target.classList.contains('active')) {
                if (window.contactsUI.load) window.contactsUI.load();
            }
        });
    });
    const tb = document.getElementById('tab-contacts');
    if (tb) obs.observe(tb, { attributes: true, attributeFilter: ['class'] });

    // Initial load if already active
    if (tb && tb.classList.contains('active')) {
        if (window.contactsUI.load) window.contactsUI.load();
    }

})();
