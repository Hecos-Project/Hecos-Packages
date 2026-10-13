/**
 * Hecos Playbooks - Import & Export Operations
 * Handles single playbook ZIP export, full backup ZIP export, and ZIP backup restore.
 */
window.HecosPlaybooks = window.HecosPlaybooks || {};

(function(HP) {
  window.pbExportSinglePlaybook = function(pid) {
    window.location.href = `/api/ext/presenter/playbooks/${encodeURIComponent(pid)}/export`;
  };

  window.pbExportPlaybook = function() {
    window.location.href = `/api/ext/presenter/playbooks/export_all`;
  };

  window.pbImportPlaybook = function(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    HP.showNotification('Importing playbook...', 'info');

    fetch('/api/ext/presenter/playbooks/import', {
      method: 'POST',
      body: formData
    })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        window.pbReloadList();
        HP.showNotification('Playbook imported successfully!', 'success');
      } else {
        HP.showNotification(data.error || 'Failed to import playbook', 'error');
      }
    })
    .catch(() => HP.showNotification('Network error during import', 'error'))
    .finally(() => {
      event.target.value = '';
    });
  };
})(window.HecosPlaybooks);
