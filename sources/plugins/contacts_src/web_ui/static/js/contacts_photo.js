/* ──────────────────────────────────────────────
   Contacts Module - Photo & Gallery Handling
   Served at: /ext/contacts/static/js/contacts_photo.js
   ────────────────────────────────────────────── */
(function () {
    'use strict';

    window.contactsUI = window.contactsUI || {};

    /* ══════════════════════════════════════════
       PHOTO HANDLING
       ══════════════════════════════════════════ */
    window.contactsUI.previewPhoto = function(input) {
        const file = input.files[0];
        if (!file) return;
        window.contactsUI._state.photoFile    = file;
        window.contactsUI._state.photoCleared = false;
        const reader  = new FileReader();
        reader.onload = e => window.contactsUI._setAvatarPreview(e.target.result);
        reader.readAsDataURL(file);
        const clearBtn = document.getElementById('c-photo-clear');
        if (clearBtn) clearBtn.style.display = 'inline-flex';
    };

    window.contactsUI.clearPhoto = function() {
        window.contactsUI._state.photoFile    = null;
        window.contactsUI._state.photoCleared = true;
        window.contactsUI._resetAvatarPreview();
        const input = document.getElementById('c-photo-input');
        if (input) input.value  = '';
        const clearBtn = document.getElementById('c-photo-clear');
        if (clearBtn) clearBtn.style.display = 'none';
    };

    window.contactsUI._setAvatarPreview = function(src) {
        const wrap = document.getElementById('c-photo-preview');
        if (!wrap) return;
        wrap.innerHTML = `
            <img src="${src}" alt="photo">
            <div class="avatar-zoom-icon"><i class="fas fa-search-plus"></i></div>
        `;
        wrap.style.cursor = 'pointer';
        wrap.onclick = () => window.contactsUI.zoomPhoto(src);
    };

    window.contactsUI._resetAvatarPreview = function() {
        const wrap = document.getElementById('c-photo-preview');
        if (!wrap) return;
        wrap.innerHTML = '<i class="fas fa-user contact-avatar-icon"></i>';
        wrap.style.cursor = 'default';
        wrap.onclick = null;
    };

    window.contactsUI.zoomPhoto = function(src) {
        if (!src) return;
        let lb = document.getElementById('contact-photo-lightbox');
        if (!lb) {
            lb = document.createElement('div');
            lb.id = 'contact-photo-lightbox';
            lb.onclick = () => lb.classList.remove('active');
            document.body.appendChild(lb);
        }
        lb.innerHTML = `<img src="${src}">`;
        // Force reflow and show
        void lb.offsetWidth;
        lb.classList.add('active');
    };

    /* ══════════════════════════════════════════
       GALLERY HANDLING
       ══════════════════════════════════════════ */
    window.contactsUI.addGalleryPhotos = function(input) {
        if (!input.files || input.files.length === 0) return;
        const state = window.contactsUI._state;
        const startIndex = state.galleryPendingFiles.length;
        for (let i = 0; i < input.files.length; i++) {
            state.galleryPendingFiles.push(input.files[i]);
            window.contactsUI._renderPendingGalleryPhoto(input.files[i], startIndex + i);
        }
        input.value = ''; // Reset input to allow selecting same files again
    };

    window.contactsUI.removePendingGalleryPhoto = function(index, el) {
        window.contactsUI._state.galleryPendingFiles[index] = null; // We set to null to preserve indices of others
        if (el && el.parentElement) el.parentElement.remove();
    };

    window.contactsUI.deleteExistingGalleryPhoto = function(contactId, fieldId, el) {
        window.contactsUI.showConfirm(window.contactsUI.t('chat_confirm_delete') || 'Are you sure?', async () => {
            try {
                const res = await fetch(`/api/contacts/${contactId}/gallery/${fieldId}`, { method: 'DELETE' });
                const data = await res.json();
                if (!data.ok) throw new Error(data.error);
                if (el && el.parentElement) el.parentElement.remove();
            } catch (e) {
                window.contactsUI.showAlert(`${window.contactsUI.t('ext_calendar_msg_error') || 'Error'}: ${e.message}`);
            }
        });
    };

    window.contactsUI._renderExistingGalleryPhoto = function(contactId, fieldId, filename) {
        const wrap = document.createElement('div');
        wrap.style.position = 'relative';
        wrap.style.width = '64px';
        wrap.style.height = '64px';
        wrap.style.borderRadius = '8px';
        wrap.style.overflow = 'hidden';
        wrap.style.border = '1px solid var(--border-color)';
        const src = `/api/contacts/${contactId}/gallery/${filename}`;

        wrap.innerHTML = `
            <img src="${src}" style="width:100%; height:100%; object-fit:cover; cursor:pointer;" onclick="window.contactsUI.zoomPhoto('${src}')">
            <button class="btn btn-sm btn-danger" style="position:absolute; top:2px; right:2px; padding:2px 4px; font-size:10px; border-radius:4px; opacity:0.8;" onclick="window.contactsUI.deleteExistingGalleryPhoto('${contactId}', '${fieldId}', this)">
                <i class="fas fa-times"></i>
            </button>
        `;
        const c = document.getElementById('c-gallery-container');
        if (c) c.appendChild(wrap);
    };

    window.contactsUI._renderPendingGalleryPhoto = function(file, index) {
        const wrap = document.createElement('div');
        wrap.style.position = 'relative';
        wrap.style.width = '64px';
        wrap.style.height = '64px';
        wrap.style.borderRadius = '8px';
        wrap.style.overflow = 'hidden';
        wrap.style.border = '1px dashed var(--muted)';

        const reader = new FileReader();
        reader.onload = e => {
            const src = e.target.result;
            wrap.innerHTML = `
                <img src="${src}" style="width:100%; height:100%; object-fit:cover; cursor:pointer;" onclick="window.contactsUI.zoomPhoto('${src}')">
                <button class="btn btn-sm btn-danger" style="position:absolute; top:2px; right:2px; padding:2px 4px; font-size:10px; border-radius:4px; opacity:0.8;" onclick="window.contactsUI.removePendingGalleryPhoto(${index}, this)">
                    <i class="fas fa-times"></i>
                </button>
            `;
            const c = document.getElementById('c-gallery-container');
            if (c) c.appendChild(wrap);
        };
        reader.readAsDataURL(file);
    };

})();
