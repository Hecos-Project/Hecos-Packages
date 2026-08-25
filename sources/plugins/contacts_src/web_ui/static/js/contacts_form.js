/* ──────────────────────────────────────────────
   Contacts Module - Form Handling
   Served at: /ext/contacts/static/js/contacts_form.js
   ────────────────────────────────────────────── */
(function () {
    'use strict';

    window.contactsUI = window.contactsUI || {};

    window.contactsUI.openNew = function() {
        document.getElementById('contact-modal-title').innerText = window.contactsUI.t('ext_contacts_modal_title');
        window.contactsUI._resetForm();
        const ex = document.getElementById('btn-contact-export');
        if (ex) ex.style.display = 'none';
        window.contactsUI._showModal();
    };

    window.contactsUI.openEdit = function(c) {
        document.getElementById('contact-modal-title').innerText = window.contactsUI.t('ext_contacts_modal_edit');
        window.contactsUI._populateForm(c);
        const ex = document.getElementById('btn-contact-export');
        if (ex) ex.style.display = 'inline-block';
        window.contactsUI._showModal();
    };

    window.contactsUI.closeForm = function() {
        document.getElementById('contact-modal').classList.remove('open');
        window.contactsUI._state.photoFile = null;
        window.contactsUI._state.photoCleared = false;
    };

    window.contactsUI._showModal = function() {
        document.getElementById('contact-modal').classList.add('open');
    };

    window.contactsUI._resetForm = function() {
        ['c-id','c-name','c-lastname','c-display',
         'c-company','c-role','c-birthday','c-tags','c-notes'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        window.contactsUI._setColor('');
        if (window.contactsUI._resetAvatarPreview) window.contactsUI._resetAvatarPreview();
        
        const photoInput = document.getElementById('c-photo-input');
        if (photoInput) photoInput.value = '';
        const photoClear = document.getElementById('c-photo-clear');
        if (photoClear) photoClear.style.display = 'none';
        
        window.contactsUI._state.photoFile = null;
        window.contactsUI._state.photoCleared = false;
        window.contactsUI._state.galleryPendingFiles = [];

        const glC = document.getElementById('c-gallery-container');
        if (glC) glC.innerHTML = '';
        const phC = document.getElementById('c-phones-container');
        if (phC) phC.innerHTML = '';
        const emC = document.getElementById('c-emails-container');
        if (emC) emC.innerHTML = '';
        const cuC = document.getElementById('c-customs-container');
        if (cuC) cuC.innerHTML = '';
        const adC = document.getElementById('c-addresses-container');
        if (adC) adC.innerHTML = '';
        
        window.contactsUI.addPhoneField('', 'Mobile');
        window.contactsUI.addEmailField('', 'Email');
        window.contactsUI.addAddressField('', 'Main');
    };

    window.contactsUI._populateForm = function(c) {
        document.getElementById('c-id').value       = c.id;
        document.getElementById('c-name').value     = c.first_name  || '';
        document.getElementById('c-lastname').value = c.last_name   || '';
        document.getElementById('c-display').value  = c.display_name|| '';
        document.getElementById('c-company').value  = c.company     || '';
        document.getElementById('c-role').value     = c.role        || '';
        document.getElementById('c-birthday').value = (c.birthday   || '').substring(0, 10);
        document.getElementById('c-tags').value     = c.tags        || '';
        document.getElementById('c-notes').value    = c.notes       || '';
        window.contactsUI._setColor(c.label_color || '');
        
        // Photo
        if (c.photo_url) {
            if (window.contactsUI._setAvatarPreview) window.contactsUI._setAvatarPreview(c.photo_url);
            const photoClear = document.getElementById('c-photo-clear');
            if (photoClear) photoClear.style.display = 'inline-flex';
        } else {
            if (window.contactsUI._resetAvatarPreview) window.contactsUI._resetAvatarPreview();
            const photoClear = document.getElementById('c-photo-clear');
            if (photoClear) photoClear.style.display = 'none';
        }
        window.contactsUI._state.photoFile = null;
        window.contactsUI._state.photoCleared = false;

        const phC = document.getElementById('c-phones-container');
        if (phC) phC.innerHTML = '';
        const phFields = (c.fields || []).filter(f => f.field_type === 'phone');
        phFields.forEach(f => window.contactsUI.addPhoneField(f.value, f.label));
        if (phFields.length === 0) window.contactsUI.addPhoneField('', 'Mobile');

        const emC = document.getElementById('c-emails-container');
        if (emC) emC.innerHTML = '';
        const emFields = (c.fields || []).filter(f => f.field_type === 'email');
        emFields.forEach(f => window.contactsUI.addEmailField(f.value, f.label));
        if (emFields.length === 0) window.contactsUI.addEmailField('', 'Email');

        const adC = document.getElementById('c-addresses-container');
        if (adC) adC.innerHTML = '';
        const adFields = (c.fields || []).filter(f => f.field_type === 'address');
        adFields.forEach(f => window.contactsUI.addAddressField(f.value, f.label));
        if (adFields.length === 0) window.contactsUI.addAddressField('', 'Main');

        const cuC = document.getElementById('c-customs-container');
        if (cuC) cuC.innerHTML = '';
        const cuFields = (c.fields || []).filter(f => !['phone', 'email', 'address', 'photo'].includes(f.field_type));
        cuFields.forEach(f => window.contactsUI.addCustomField(f.field_type, f.label, f.value));

        const glC = document.getElementById('c-gallery-container');
        if (glC) glC.innerHTML = '';
        window.contactsUI._state.galleryPendingFiles = [];
        const galFields = (c.fields || []).filter(f => f.field_type === 'photo');
        galFields.forEach(f => {
            if (window.contactsUI._renderExistingGalleryPhoto) {
                window.contactsUI._renderExistingGalleryPhoto(c.id, f.id, f.value);
            }
        });
    };

    window.contactsUI.addPhoneField = function(value = '', label = 'Mobile') {
        const _esc = window.contactsUI._esc;
        const wrap = document.createElement('div');
        wrap.className = 'multi-field-item';
        wrap.style.display = 'flex';
        wrap.style.gap = '6px';
        wrap.innerHTML = `
            <input type="text" class="form-control ph-lbl" style="width:35%; font-size:12px;" placeholder="${window.contactsUI.t('ext_contacts_label')||'Label'}..." value="${_esc(label)}">
            <input type="tel" class="form-control ph-val" style="flex:1;" placeholder="+39 333..." value="${_esc(value)}">
            <button class="btn btn-secondary contact-delete-multi" style="padding:0; width:36px; height:36px; display:flex; align-items:center; justify-content:center; color:var(--muted); flex-shrink:0;" onclick="this.parentElement.remove()" title="Remove">
                <i class="fas fa-times"></i>
            </button>
        `;
        const c = document.getElementById('c-phones-container');
        if (c) c.appendChild(wrap);
    };

    window.contactsUI.addEmailField = function(value = '', label = 'Email') {
        const _esc = window.contactsUI._esc;
        const wrap = document.createElement('div');
        wrap.className = 'multi-field-item';
        wrap.style.display = 'flex';
        wrap.style.gap = '6px';
        wrap.innerHTML = `
            <input type="text" class="form-control em-lbl" style="width:35%; font-size:12px;" placeholder="${window.contactsUI.t('ext_contacts_label')||'Label'}..." value="${_esc(label)}">
            <input type="email" class="form-control em-val" style="flex:1;" placeholder="nome@email.com" value="${_esc(value)}">
            <button class="btn btn-secondary contact-delete-multi" style="padding:0; width:36px; height:36px; display:flex; align-items:center; justify-content:center; color:var(--muted); flex-shrink:0;" onclick="this.parentElement.remove()" title="Remove">
                <i class="fas fa-times"></i>
            </button>
        `;
        const c = document.getElementById('c-emails-container');
        if (c) c.appendChild(wrap);
    };

    window.contactsUI.addAddressField = function(value = '', label = 'Main') {
        const _esc = window.contactsUI._esc;
        const wrap = document.createElement('div');
        wrap.className = 'multi-field-item';
        wrap.style.display = 'flex';
        wrap.style.gap = '6px';
        wrap.innerHTML = `
            <input type="text" class="form-control ad-lbl" style="width:35%; font-size:12px;" placeholder="${window.contactsUI.t('ext_contacts_label')||'Label'}..." value="${_esc(label)}">
            <input type="text" class="form-control ad-val" style="flex:1;" placeholder="Via Roma 1, Milano..." value="${_esc(value)}">
            <button class="btn btn-secondary contact-delete-multi" style="padding:0; width:36px; height:36px; display:flex; align-items:center; justify-content:center; color:var(--muted); flex-shrink:0;" onclick="this.parentElement.remove()" title="Remove">
                <i class="fas fa-times"></i>
            </button>
        `;
        const c = document.getElementById('c-addresses-container');
        if (c) c.appendChild(wrap);
    };

    window.contactsUI.addCustomField = function(fieldType = 'telegram_id', label = '', value = '') {
        const _esc = window.contactsUI._esc;
        const wrap = document.createElement('div');
        wrap.className = 'multi-field-item';
        wrap.style.display = 'flex';
        wrap.style.gap = '6px';
        const selectOptions = `
            <option value="telegram_id" ${fieldType==='telegram_id'?'selected':''}>Telegram ID</option>
            <option value="skype" ${fieldType==='skype'?'selected':''}>Skype</option>
            <option value="discord" ${fieldType==='discord'?'selected':''}>Discord</option>
            <option value="ip_port" ${fieldType==='ip_port'?'selected':''}>IP / Port</option>
            <option value="custom" ${fieldType==='custom'?'selected':''}>Custom...</option>
        `;
        wrap.innerHTML = `
            <select class="form-control cu-type" style="width:100px; font-size:12px; padding:0 8px;">
                ${selectOptions}
            </select>
            <input type="text" class="form-control cu-lbl" style="width:25%; font-size:12px;" placeholder="${window.contactsUI.t('ext_contacts_label')||'Label'}" value="${_esc(label)}">
            <input type="text" class="form-control cu-val" style="flex:1;" placeholder="${window.contactsUI.t('ext_contacts_value')||'Value'}" value="${_esc(value)}">
            <button class="btn btn-secondary contact-delete-multi" style="padding:0; width:36px; height:36px; display:flex; align-items:center; justify-content:center; color:var(--muted); flex-shrink:0;" onclick="this.parentElement.remove()" title="Remove">
                <i class="fas fa-times"></i>
            </button>
        `;
        const c = document.getElementById('c-customs-container');
        if (c) c.appendChild(wrap);
    };

    window.contactsUI.save = async function() {
        const id    = document.getElementById('c-id').value;
        const color = window.contactsUI._getColor();

        const payload = {
            first_name:   document.getElementById('c-name').value.trim(),
            last_name:    document.getElementById('c-lastname').value.trim(),
            display_name: document.getElementById('c-display').value.trim(),
            company:      document.getElementById('c-company').value.trim(),
            role:         document.getElementById('c-role').value.trim(),
            birthday:     document.getElementById('c-birthday').value,
            tags:         document.getElementById('c-tags').value.trim(),
            notes:        document.getElementById('c-notes').value.trim(),
            label_color:  color
        };
        if (!payload.first_name) {
            if (!id) {
                // If it's a new contact and they didn't even type a name, just close without saving
                window.contactsUI.closeForm();
                return;
            } else {
                window.contactsUI.showAlert(window.contactsUI.t('ext_contacts_name') + ' *'); 
                return;
            }
        }

        const phones = [];
        document.querySelectorAll('#c-phones-container .multi-field-item').forEach((el, index) => {
            const lbl = el.querySelector('.ph-lbl').value.trim() || 'Mobile';
            const val = el.querySelector('.ph-val').value.trim();
            if (val) phones.push({ value: val, label: lbl, is_primary: index === 0 });
        });
        if (phones.length) payload.phones = phones;

        const emails = [];
        document.querySelectorAll('#c-emails-container .multi-field-item').forEach((el, index) => {
            const lbl = el.querySelector('.em-lbl').value.trim() || 'Email';
            const val = el.querySelector('.em-val').value.trim();
            if (val) emails.push({ value: val, label: lbl, is_primary: index === 0 });
        });
        if (emails.length) payload.emails = emails;

        const customs = [];
        document.querySelectorAll('#c-customs-container .multi-field-item').forEach((el, index) => {
            const fieldType = el.querySelector('.cu-type').value.trim() || 'custom';
            const label     = el.querySelector('.cu-lbl').value.trim();
            const val       = el.querySelector('.cu-val').value.trim();
            if (val) customs.push({ field_type: fieldType, value: val, label: label, is_primary: index === 0 });
        });
        if (customs.length) payload.customs = customs;

        const addresses = [];
        document.querySelectorAll('#c-addresses-container .multi-field-item').forEach((el, index) => {
            const lbl = el.querySelector('.ad-lbl').value.trim() || 'Main';
            const val = el.querySelector('.ad-val').value.trim();
            if (val) addresses.push({ value: val, label: lbl, is_primary: index === 0 });
        });
        if (addresses.length) payload.addresses = addresses;

        if (window.contactsUI._state.photoCleared) payload.photo_path = null;

        try {
            const url    = id ? `/api/contacts/${id}` : '/api/contacts';
            const method = id ? 'PUT' : 'POST';
            const res    = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
            const data   = await res.json();
            if (!data.ok) throw new Error(data.error);

            const contactId = data.contact?.id || id;

            // Upload photo if pending
            if (window.contactsUI._state.photoFile && contactId) {
                const fd = new FormData();
                fd.append('photo', window.contactsUI._state.photoFile);
                await fetch(`/api/contacts/${contactId}/photo`, { method: 'POST', body: fd });
            }

            // Upload gallery photos if pending
            const pendingFiles = window.contactsUI._state.galleryPendingFiles || [];
            if (pendingFiles.length > 0 && contactId) {
                for (const file of pendingFiles) {
                    if (!file) continue;
                    const fd = new FormData();
                    fd.append('photo', file);
                    await fetch(`/api/contacts/${contactId}/gallery`, { method: 'POST', body: fd });
                }
                window.contactsUI._state.galleryPendingFiles = [];
            }

            window.contactsUI.closeForm();
            window.contactsUI.load();
        } catch (e) {
            window.contactsUI.showAlert(`${window.contactsUI.t('ext_calendar_msg_error') || 'Error'}: ${e.message}`);
        }
    };

})();
