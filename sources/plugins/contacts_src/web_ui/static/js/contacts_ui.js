/* ──────────────────────────────────────────────
   Contacts Module - UI Rendering
   Served at: /ext/contacts/static/js/contacts_ui.js
   ────────────────────────────────────────────── */
(function () {
    'use strict';

    window.contactsUI = window.contactsUI || {};

    /* ══════════════════════════════════════════
       HTML Templates
       ══════════════════════════════════════════ */
    window.contactsUI._spinnerHtml = function() {
        return `<div class="contacts-empty-state"><i class="fas fa-spinner fa-spin"></i><p>${window.contactsUI.t('ext_contacts_loading')}</p></div>`;
    };

    window.contactsUI._emptyStateHtml = function() {
        return `<div class="contacts-empty-state">
            <i class="fas fa-address-book"></i>
            <h3>${window.contactsUI.t('ext_contacts_empty_title')}</h3>
            <p>${window.contactsUI.t('ext_contacts_empty_sub')}</p>
        </div>`;
    };

    window.contactsUI._searchEmptyHtml = function() {
        return `<div class="contacts-empty-state">
            <i class="fas fa-search" style="font-size:36px; opacity:0.4;"></i>
            <p style="margin-top:12px;">${window.contactsUI.t('ext_contacts_search_empty')}</p>
        </div>`;
    };

    /* ══════════════════════════════════════════
       LOAD & RENDER
       ══════════════════════════════════════════ */
    window.contactsUI.load = async function(query = '') {
        const grid = document.getElementById('contacts-grid');
        if (!grid) return;
        grid.innerHTML = window.contactsUI._spinnerHtml();

        try {
            const res  = await fetch(`/api/contacts?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            if (!data.ok) throw new Error(data.error);

            if (!data.contacts.length) {
                grid.innerHTML = query ? window.contactsUI._searchEmptyHtml() : window.contactsUI._emptyStateHtml();
                return;
            }
            grid.innerHTML = '';
            data.contacts.forEach(c => grid.appendChild(window.contactsUI._buildCard(c)));
        } catch (e) {
            grid.innerHTML = `<div style="color:var(--red);padding:20px;">${window.contactsUI.t('ext_calendar_msg_error')}: ${e.message}</div>`;
        }
    };

    window.contactsUI._buildCard = function(c) {
        const _esc = window.contactsUI._esc;
        const dname    = c.display_name || `${c.first_name} ${c.last_name || ''}`.trim();
        const ribbon   = c.label_color  || 'var(--accent)';
        const phone    = window.contactsUI._primaryField(c.fields, 'phone');
        const email    = window.contactsUI._primaryField(c.fields, 'email');
        const initials = dname.split(' ').slice(0, 2).map(s => s[0] || '').join('');

        // Avatar
        let avatarHtml;
        if (c.photo_url) {
            avatarHtml = `<div class="contact-card-avatar" onclick="event.stopPropagation(); window.contactsUI.zoomPhoto('${c.photo_url}')" title="Zoom">
                <img src="${c.photo_url}" alt="${_esc(dname)}" loading="lazy">
                <div class="avatar-zoom-icon"><i class="fas fa-search-plus"></i></div>
            </div>`;
        } else {
            avatarHtml = `<div class="contact-card-avatar-placeholder">${_esc(initials)}</div>`;
        }

        // Tags
        const tagHtml = c.tags
            ? c.tags.split(',').map(t => `<span class="contact-badge">${_esc(t.trim())}</span>`).join('')
            : '';

        const el = document.createElement('div');
        el.className = 'contact-card';
        el.innerHTML = `
            <div class="contact-card-ribbon" style="background:${ribbon};"></div>
            ${avatarHtml}
            <h4 class="contact-card-name">${_esc(dname)}</h4>
            ${c.company ? `<div class="contact-card-company" style="color:${ribbon};">${_esc(c.company)}</div>` : ''}
            <div class="contact-card-info">
                ${phone ? `<div class="contact-card-info-row"><i class="fas fa-phone"></i><span>${_esc(phone)}</span></div>` : ''}
                ${email ? `<div class="contact-card-info-row"><i class="fas fa-envelope"></i><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(email)}</span></div>` : ''}
            </div>
            ${tagHtml ? `<div class="contact-card-tags">${tagHtml}</div>` : ''}
            <button class="contact-delete-btn" title="${window.contactsUI.t('chat_btn_delete')}"
                    onclick="event.stopPropagation(); window.contactsUI.del('${c.id}', '${_esc(dname).replace(/'/g,"\\'")}')">
                <i class="fas fa-trash"></i>
            </button>
        `;
        el.onclick = () => window.contactsUI.openEdit(c);
        return el;
    };

})();
