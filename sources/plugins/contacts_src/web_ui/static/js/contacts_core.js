/* ──────────────────────────────────────────────
   Contacts Module - Core
   Served at: /ext/contacts/static/js/contacts_core.js
   ────────────────────────────────────────────── */
(function () {
    'use strict';

    // Initialize global namespace
    window.contactsUI = window.contactsUI || {};
    window.contactsUI._state = {
        searchTimeout: null,
        picker: null,
        photoFile: null,
        photoCleared: false,
        galleryPendingFiles: []
    };

    /* ── i18n helper ── */
    window.contactsUI.t = function(k) {
        return (window.t ? window.t(k) : k);
    };

    /* ── Utilities ── */
    window.contactsUI._esc = function(s) {
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    };

    window.contactsUI._primaryField = function(fields, type) {
        if (!fields) return '';
        return (fields.find(f => f.field_type === type && f.is_primary) || fields.find(f => f.field_type === type) || {}).value || '';
    };

    /* ── Color helpers ── */
    window.contactsUI._getColor = function() {
        const state = window.contactsUI._state;
        if (state.picker) return state.picker.currentColor || '';
        const el = document.getElementById('c-color-native');
        return el ? (el.value === '#000000' ? '' : el.value) : '';
    };

    window.contactsUI._setColor = function(hex) {
        const state = window.contactsUI._state;
        if (state.picker) { 
            state.picker.currentColor = hex; 
            state.picker.render(); 
            return; 
        }
        const el = document.getElementById('c-color-native');
        if (el) el.value = hex || '#6366f1';
    };

    /* ── Modals ── */
    window.contactsUI.showConfirm = function(msg, onConfirm) {
        let overlay = document.getElementById('contacts-confirm-modal');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'contacts-confirm-modal';
            overlay.className = 'modal-overlay';
            overlay.style.zIndex = '9999';
            overlay.innerHTML = `
                <div class="card" style="max-width: 400px; text-align: center;">
                    <div class="card-title" style="justify-content: center; margin-bottom: 16px;">
                        <i class="fas fa-question-circle" style="font-size: 24px; color: var(--accent);"></i>
                    </div>
                    <p id="contacts-confirm-text" style="margin-bottom: 24px; font-size: 14px; color: var(--fg);"></p>
                    <div style="display: flex; gap: 10px; justify-content: center;">
                        <button class="btn btn-secondary" id="contacts-confirm-no">${window.contactsUI.t('ext_contacts_btn_cancel') || 'Cancel'}</button>
                        <button class="btn btn-primary" id="contacts-confirm-yes">${window.contactsUI.t('ext_contacts_btn_save') || 'Yes'}</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
        }
        document.getElementById('contacts-confirm-text').innerHTML = msg;
        overlay.classList.add('open');
        
        const btnNo = document.getElementById('contacts-confirm-no');
        const btnYes = document.getElementById('contacts-confirm-yes');
        
        btnNo.onclick = () => { overlay.classList.remove('open'); };
        btnYes.onclick = () => { overlay.classList.remove('open'); if (onConfirm) onConfirm(); };
    };

    window.contactsUI.showAlert = function(msg) {
        let overlay = document.getElementById('contacts-alert-modal');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'contacts-alert-modal';
            overlay.className = 'modal-overlay';
            overlay.style.zIndex = '9999';
            overlay.innerHTML = `
                <div class="card" style="max-width: 400px; text-align: center;">
                    <div class="card-title" style="justify-content: center; margin-bottom: 16px;">
                        <i class="fas fa-exclamation-triangle" style="font-size: 24px; color: var(--red, #ef4444);"></i>
                    </div>
                    <p id="contacts-alert-text" style="margin-bottom: 24px; font-size: 14px; color: var(--fg);"></p>
                    <div style="display: flex; justify-content: center;">
                        <button class="btn btn-primary" id="contacts-alert-ok">OK</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
        }
        document.getElementById('contacts-alert-text').innerHTML = msg;
        overlay.classList.add('open');
        document.getElementById('contacts-alert-ok').onclick = () => { overlay.classList.remove('open'); };
    };

})();
