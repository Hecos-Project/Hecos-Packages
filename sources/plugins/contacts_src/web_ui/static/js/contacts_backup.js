/* ──────────────────────────────────────────────
   Contacts Module - Backup & Restore
   Served at: /ext/contacts/static/js/contacts_backup.js
   ────────────────────────────────────────────── */
(function () {
    'use strict';

    window.contactsUI = window.contactsUI || {};

    /* ══════════════════════════════════════════
       BACKUP & RESTORE
       ══════════════════════════════════════════ */
    window.contactsUI.backupFull = async function() {
        try {
            if (window.showToast) window.showToast('Preparing contacts backup...', 'info');
            const res = await fetch('/api/contacts/backup');
            if (!res.ok) throw new Error('Backup request failed');
            const data = await res.json();
            if (!data.ok) throw new Error(data.error || 'Backup failed');

            const payload = {
                type: 'hecos_contacts_backup',
                exported_at: new Date().toISOString(),
                contacts: data.contacts
            };

            const filename = `hecos_contacts_backup_${new Date().toISOString().split('T')[0]}.json`;
            const content  = JSON.stringify(payload, null, 2);

            window.contactsUI._downloadJson(filename, content);
            if (window.showToast) window.showToast(`Backup of ${data.count} contacts completed`, 'success');
        } catch(err) {
            console.error('[CONTACTS] Backup error:', err);
            if (window.showToast) window.showToast(err.message, 'error');
            else window.contactsUI.showAlert('Backup error: ' + err.message);
        }
    };

    window.contactsUI.exportSingle = async function() {
        const id = document.getElementById('c-id').value;
        if (!id) return;
        try {
            const res = await fetch(`/api/contacts/${id}`);
            const data = await res.json();
            if (!data.ok || !data.contact) throw new Error('Failed to load contact data');

            const payload = {
                type: 'hecos_contacts_backup',
                exported_at: new Date().toISOString(),
                contacts: [data.contact]
            };

            let name = (data.contact.display_name || 'Contact').replace(/\s+/g, '_');
            const filename = `hecos_contact_${name}.json`;
            const content  = JSON.stringify(payload, null, 2);

            window.contactsUI._downloadJson(filename, content);
            if (window.showToast) window.showToast('Contact exported successfully', 'success');
        } catch(err) {
            console.error('[CONTACTS] Export error:', err);
            window.contactsUI.showAlert('Export error: ' + err.message);
        }
    };

    window.contactsUI._downloadJson = async function(filename, content) {
        if (window.showSaveFilePicker) {
            try {
                const fh = await window.showSaveFilePicker({
                    suggestedName: filename,
                    types: [{ description: 'JSON', accept: { 'application/json': ['.json'] } }]
                });
                const w = await fh.createWritable();
                await w.write(content);
                await w.close();
            } catch(e) {
                if (e.name === 'AbortError') return;
                throw e;
            }
        } else {
            const blob = new Blob([content], { type: 'application/json' });
            const url  = URL.createObjectURL(blob);
            const a    = document.createElement('a');
            a.href = url; a.download = filename;
            document.body.appendChild(a); a.click();
            document.body.removeChild(a); URL.revokeObjectURL(url);
        }
    };

    window.contactsUI.restoreFile = async function(e) {
        const file = e.target.files[0];
        if (!file) return;
        // reset input
        e.target.value = '';

        try {
            if (window.showToast) window.showToast('Uploading contacts...', 'info');

            const formData = new FormData();
            formData.append('file', file);

            const res = await fetch('/api/contacts/import?mode=duplicate', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) throw new Error('Import request failed');
            const data = await res.json();
            if (!data.ok) throw new Error(data.error || 'Import failed');

            if (window.showToast) window.showToast(`Imported ${data.imported || 0} contacts successfully`, 'success');
            if (window.contactsUI.load) window.contactsUI.load(); // refresh grid
        } catch(err) {
            console.error('[CONTACTS] Import error:', err);
            if (window.showToast) window.showToast(err.message, 'error');
            else window.contactsUI.showAlert('Import error: ' + err.message);
        }
    };

})();
