/**
 * Central Hub Source Editor, Previewer & One-Shot Importer
 * Extracted from search_sources.js for modularity.
 */
window.SearchSourcesImporter = (function () {
  function create(ctx) {
    let _editingSourceId = '';

    function _meta() {
      return ctx.tabMeta[ctx.getActiveTab()] || ctx.tabMeta.searxng;
    }

    function readForm() {
      const meta = _meta();
      return {
        id: _editingSourceId || undefined,
        name: (document.getElementById('src-form-name')?.value || '').trim(),
        location: (document.getElementById('src-form-location')?.value || '').trim(),
        format: document.getElementById('src-form-format')?.value || meta.defaultFormat || 'auto',
        target_pool: document.getElementById('src-form-pool')?.value || meta.defaultPool || 'auto',
        interval_hours: parseInt(document.getElementById('src-form-interval')?.value || '12', 10) || 12,
        auto_update: document.getElementById('src-form-autoupdate')?.checked !== false,
        use_tor: document.getElementById('src-form-usetor')?.checked === true,
        enabled: true,
      };
    }

    function clearForm() {
      _editingSourceId = '';
      ['src-form-name', 'src-form-location'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      const meta = _meta();
      const fmt = document.getElementById('src-form-format');
      if (fmt) fmt.value = meta.defaultFormat || 'auto';
      const pool = document.getElementById('src-form-pool');
      if (pool) pool.value = meta.defaultPool || 'auto';
      const iv = document.getElementById('src-form-interval');
      if (iv) iv.value = '12';
      const au = document.getElementById('src-form-autoupdate');
      if (au) au.checked = true;
      const ut = document.getElementById('src-form-usetor');
      if (ut) ut.checked = (ctx.getActiveTab() === 'dark');
      const cancelBtn = document.getElementById('src-form-cancel-btn');
      if (cancelBtn) cancelBtn.style.display = 'none';
      const saveBtnLabel = document.getElementById('src-form-save-label');
      if (saveBtnLabel) saveBtnLabel.textContent = 'Add & Sync Source';
    }

    function edit(sourceId) {
      const src = ctx.getSources().find(s => s.id === sourceId);
      if (!src) return;
      const tab = ctx.tabForItem(src);
      _editingSourceId = src.id;
      if (typeof window.switchNetSearchEndpointTab === 'function') {
        window.switchNetSearchEndpointTab(tab);
      }
      ctx.configureEditorForTab(tab, src.target_pool || ctx.tabMeta[tab].defaultPool);

      document.getElementById('src-form-name').value = src.name || '';
      document.getElementById('src-form-location').value = src.location || '';
      document.getElementById('src-form-format').value = src.format || 'auto';
      document.getElementById('src-form-pool').value = src.target_pool || 'auto';
      document.getElementById('src-form-interval').value = String(src.interval_hours || 12);
      document.getElementById('src-form-autoupdate').checked = src.auto_update !== false;
      document.getElementById('src-form-usetor').checked = src.use_tor === true;

      const titleEl = document.getElementById('src-editor-title');
      if (titleEl) {
        titleEl.innerHTML = `<i class="fas fa-pen" style="color:var(--accent-cyan, #06b6d4); margin-right:5px;"></i> Edit Source: ${ctx.esc(src.name || src.id)}`;
      }
      const cancelBtn = document.getElementById('src-form-cancel-btn');
      if (cancelBtn) cancelBtn.style.display = 'inline-flex';
      const saveBtnLabel = document.getElementById('src-form-save-label');
      if (saveBtnLabel) saveBtnLabel.textContent = 'Update & Sync Source';

      const panel = document.getElementById('src-editor-panel');
      if (panel) {
        panel.style.display = 'block';
        panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      document.getElementById('src-form-location')?.focus();
    }

    function showPreview(res) {
      const box = document.getElementById('src-preview-box');
      if (!box) return;
      if (!res || !res.ok) {
        box.style.display = 'block';
        box.innerHTML = `<span style="color:#f87171;"><i class="fas fa-exclamation-circle"></i> Preview error: ${ctx.esc(res?.error || 'Unknown')}</span>`;
        return;
      }
      const st = res.stats || {};
      const sample = Array.isArray(st.preview) ? st.preview.slice(0, 8) : [];
      const sampleHtml = sample.map(it =>
        `<div style="font-family:monospace; font-size:10px; color:var(--text);">[${ctx.esc(it.pool)}] ${ctx.esc(it.name)} -> ${ctx.esc(it.url)}</div>`
      ).join('');
      box.style.display = 'block';
      box.innerHTML = `
        <div style="font-size:11px; margin-bottom:4px;">
          <strong>Format:</strong> ${ctx.esc((res.detected_format || 'auto').toUpperCase())} &nbsp;|&nbsp;
          <strong>Parsed:</strong> ${st.parsed || 0} &nbsp;|&nbsp;
          <strong style="color:#34d399;">New unique: +${st.added || 0}</strong> &nbsp;|&nbsp;
          <strong style="color:#fbbf24;">Duplicates skipped: ${st.skipped_duplicates || 0}</strong>
        </div>
        ${sampleHtml}
      `;
    }

    async function previewUrl() {
      const data = readForm();
      if (!data.location) {
        ctx.notify('Enter a URL, GitHub raw link, OpenSearch URL, or local file path first.', 'warning');
        return;
      }
      const box = document.getElementById('src-preview-box');
      if (box) {
        box.style.display = 'block';
        box.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Fetching and checking duplicates...';
      }
      try {
        const res = await fetch('/api/hsearch/sources/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        }).then(r => r.json());
        showPreview(res);
      } catch (e) {
        showPreview({ ok: false, error: e.message });
      }
    }

    async function saveFromForm() {
      const data = readForm();
      if (!data.location) {
        ctx.notify('Enter a URL or local file path for the source.', 'warning');
        return;
      }
      ctx.notify('Saving and syncing source...', 'info');
      try {
        const res = await fetch('/api/hsearch/sources', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...data, sync_now: true, force: true })
        }).then(r => r.json());
        if (res.ok) {
          const sync = res.sync || {};
          if (sync.ok === false) {
            ctx.notify(`Source saved, sync warning: ${sync.error || sync.status}`, 'warning');
          } else {
            const st = sync.stats || {};
            ctx.notify(`Source synced: +${st.added || 0} new, ${st.skipped_duplicates || 0} duplicates skipped.`, 'success');
          }
          ctx.closeEditor();
          await ctx.load();
          if (typeof window.reloadNetSearchEndpoints === 'function') window.reloadNetSearchEndpoints();
        } else {
          ctx.notify('Error saving source: ' + (res.error || 'Unknown'), 'error');
        }
      } catch (e) {
        ctx.notify('Save error: ' + e.message, 'error');
      }
    }

    function updateImportFileLabel() {
      const fileInput = document.getElementById('src-import-file');
      const lbl = document.getElementById('src-import-file-label');
      if (!lbl) return;
      const f = fileInput?.files?.[0];
      lbl.textContent = f ? f.name : 'No file selected';
      lbl.style.color = f ? 'var(--text)' : 'var(--muted)';
    }

    async function importRawOrFile(dryRun = false) {
      const fileInput = document.getElementById('src-import-file');
      const textInput = document.getElementById('src-import-text');
      const fmt = document.getElementById('src-import-format')?.value || 'auto';
      const meta = _meta();
      const pool = document.getElementById('src-import-pool')?.value || meta.defaultPool || 'auto';
      const file = fileInput?.files?.[0];
      const text = (textInput?.value || '').trim();

      if (!file && !text) {
        ctx.notify('Select a file (.m3u, .json, .csv, .yaml, .sqlite, .xml, .txt) or paste list content first.', 'warning');
        return;
      }

      const endpoint = dryRun ? '/api/hsearch/sources/preview' : '/api/hsearch/sources/import';
      try {
        let res;
        if (file) {
          const fd = new FormData();
          fd.append('file', file);
          fd.append('format', fmt);
          fd.append('target_pool', pool);
          fd.append('name', file.name);
          if (dryRun) fd.append('dry_run', 'true');
          res = await fetch(endpoint, { method: 'POST', body: fd }).then(r => r.json());
        } else {
          res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: text, format: fmt, target_pool: pool, dry_run: !!dryRun })
          }).then(r => r.json());
        }

        if (dryRun) {
          showPreview(res);
        } else if (res.ok) {
          const st = res.stats || {};
          ctx.notify(`Imported (${(res.detected_format || 'auto').toUpperCase()}): +${st.added || 0} new, ${st.skipped_duplicates || 0} duplicates skipped.`, 'success');
          if (fileInput) { fileInput.value = ''; updateImportFileLabel(); }
          if (textInput) textInput.value = '';
          ctx.closeEditor();
          await ctx.load();
          if (typeof window.reloadNetSearchEndpoints === 'function') window.reloadNetSearchEndpoints();
        } else {
          ctx.notify('Import failed: ' + (res.error || 'Unknown'), 'error');
        }
      } catch (e) {
        ctx.notify('Import error: ' + e.message, 'error');
      }
    }

    return {
      isEditing: () => Boolean(_editingSourceId),
      isEditingId: (id) => _editingSourceId === id,
      clearForm,
      edit,
      previewUrl,
      saveFromForm,
      updateImportFileLabel,
      importRawOrFile,
    };
  }

  return { create };
})();
