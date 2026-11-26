/**
 * igen_presets.js - Image Gen Panel: Full Core-Style Preset Management
 * Matches Hecos Core preset lifecycle (Voice / Voice Forge / Global Preset Manager):
 * New, Update (with built-in overwrite protection), Rename, Duplicate, Reset,
 * Set/Clear Default, Delete, Export/Import JSON, Dirty Tracking, & Library Cards.
 */

(function () {
    'use strict';

    window._igenPresetsList = [];
    window._igenDefaultPreset = '';
    window._igenLoadedPresetName = '';
    window._igenLoadedPresetSnapshot = null;

    // ── Utilities ──────────────────────────────────────────────────────────────

    function _esc(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function _escJs(str) {
        return String(str == null ? '' : str)
            .replace(/\\/g, '\\\\')
            .replace(/'/g, "\\'")
            .replace(/\r/g, '\\r')
            .replace(/\n/g, '\\n');
    }

    function _findPresetMeta(name) {
        if (!name) return null;
        return (window._igenPresetsList || []).find(p => p.name === name) || null;
    }

    function _allExistingNamesLower() {
        return new Set((window._igenPresetsList || []).map(p => (p.name || '').trim().toLowerCase()));
    }

    function _nextCustomName(base) {
        const prefix = (base || 'custom').trim();
        const existing = _allExistingNamesLower();
        let idx = 1;
        while (existing.has((prefix + '_' + idx).toLowerCase())) {
            idx++;
        }
        return prefix + '_' + idx;
    }

    function _suggestCopyName(sourceName) {
        const clean = (sourceName || 'Preset').replace(/^[\p{Extended_Pictographic}\uFE0F\u200D\s]+/u, '').trim() || 'Preset';
        const existing = _allExistingNamesLower();
        let cand = clean + ' (Copy)';
        if (!existing.has(cand.toLowerCase())) return cand;
        let idx = 2;
        while (existing.has((clean + ' (Copy ' + idx + ')').toLowerCase())) {
            idx++;
        }
        return clean + ' (Copy ' + idx + ')';
    }

    // Keys compared for the "● Modified" dirty indicator
    const _COMPARE_KEYS = [
        'provider', 'model', 'hf_provider', 'aspect_ratio', 'width', 'height',
        'seed', 'sampler', 'scheduler', 'guidance_scale', 'num_inference_steps',
        'flux_guidance_scale', 'sigma_shift',
        'enable_negative_prompt', 'negative_prompt', 'auto_enrich',
        'enrich_keywords', 'style', 'nologo', 'optimize_for_flux',
        'flux_refiner_instructions', 'vae', 'loras',
        'horde_nsfw', 'routing_override'
    ];

    function _normalizeForCompare(cfg) {
        if (!cfg || typeof cfg !== 'object') return null;
        const out = {};
        _COMPARE_KEYS.forEach(k => {
            let v = cfg[k];
            if (k === 'loras') {
                v = Array.isArray(v) ? v.slice().sort() : [];
            } else if (k === 'guidance_scale' || k === 'flux_guidance_scale' || k === 'sigma_shift') {
                const defF = (k === 'guidance_scale') ? 0 : -1;
                v = Number.isFinite(parseFloat(v)) ? Math.round(parseFloat(v) * 100) / 100 : defF;
            } else if (k === 'width' || k === 'height' || k === 'seed' || k === 'num_inference_steps') {
                v = Number.isFinite(parseInt(v, 10)) ? parseInt(v, 10) : 0;
            } else if (typeof v === 'boolean') {
                v = !!v;
            } else {
                v = v == null ? '' : String(v);
            }
            out[k] = v;
        });
        return JSON.stringify(out);
    }

    // ── Load Presets Catalog ───────────────────────────────────────────────────

    window.loadIgenPresets = async function(restoreValue) {
        try {
            const r = await fetch('/hecos/api/plugins/image_gen/presets', { cache: 'no-store' });
            const d = await r.json();
            if (!d.ok) return;

            const list = d.presets || [];
            window._igenPresetsList = list;
            window._igenDefaultPreset = d.default_preset || '';

            const sel = document.getElementById('igen-preset');
            if (!sel) return;

            const targetValue = restoreValue !== undefined ? restoreValue : sel.value;
            sel.innerHTML = '<option value="">— Select a preset —</option>';

            const userGroup  = document.createElement('optgroup');
            userGroup.label  = '👤 My Custom Presets';
            const localGroup = document.createElement('optgroup');
            localGroup.label = '💻 Local Presets (Built-in)';
            const cloudGroup = document.createElement('optgroup');
            cloudGroup.label = '☁️ Cloud Presets (Built-in)';

            let customCount = 0;
            let builtinCount = 0;

            list.forEach(p => {
                const opt = document.createElement('option');
                let text = p.name;
                if (p.is_default) text += ' ⭐ [Default]';
                opt.value = p.name;
                opt.textContent = text;
                opt.dataset.builtin = String(!!p.builtin);
                opt.dataset.isDefault = String(!!p.is_default);

                if (!p.builtin) {
                    customCount++;
                    userGroup.appendChild(opt);
                } else if (p.is_local) {
                    builtinCount++;
                    localGroup.appendChild(opt);
                } else {
                    builtinCount++;
                    cloudGroup.appendChild(opt);
                }
            });

            // Show user's Custom Presets FIRST, then Local, then Cloud
            if (userGroup.children.length > 0)  sel.appendChild(userGroup);
            if (localGroup.children.length > 0) sel.appendChild(localGroup);
            if (cloudGroup.children.length > 0) sel.appendChild(cloudGroup);

            if (targetValue && list.some(p => p.name === targetValue)) {
                sel.value = targetValue;
            } else {
                sel.value = '';
            }

            // Update count badges
            const totalBadge = document.getElementById('igen-preset-count-badge');
            if (totalBadge) {
                totalBadge.textContent = customCount + ' custom · ' + builtinCount + ' built-in';
            }
            const customBadge = document.getElementById('igen-custom-count-badge');
            if (customBadge) customBadge.textContent = String(customCount);
            const builtinBadge = document.getElementById('igen-builtin-count-badge');
            if (builtinBadge) builtinBadge.textContent = String(builtinCount);

            window.checkIgenPresetUI();
            window.renderIgenPresetLibrary();
            window.updateIgenLiveSummary();
            window.updateIgenDirtyState();
        } catch (err) {
            console.warn('[igen] loadIgenPresets error:', err);
        }
    };

    window.captureIgenPresetBaseline = async function(presetName) {
        window._igenLoadedPresetName = presetName || '';
        if (!presetName) {
            window._igenLoadedPresetSnapshot = null;
            window.updateIgenDirtyState();
            return;
        }
        try {
            const r = await fetch('/hecos/api/plugins/image_gen/presets/load/' + encodeURIComponent(presetName), { cache: 'no-store' });
            const d = await r.json();
            if (d.ok && d.config) {
                // Compare against live collected state merged with preset values
                const base = Object.assign({}, window.collectIgenConfig(), d.config);
                window._igenLoadedPresetSnapshot = _normalizeForCompare(base);
            } else {
                window._igenLoadedPresetSnapshot = _normalizeForCompare(window.collectIgenConfig());
            }
        } catch (_) {
            window._igenLoadedPresetSnapshot = _normalizeForCompare(window.collectIgenConfig());
        }
        window.updateIgenDirtyState();
    };

    // ── Apply / Load Preset ────────────────────────────────────────────────────

    window.loadIgenPreset = async function(explicitName) {
        const sel = document.getElementById('igen-preset');
        const name = (explicitName !== undefined) ? explicitName : (sel ? sel.value : '');
        if (sel && explicitName !== undefined) sel.value = explicitName;

        if (!name) {
            window._igenLoadedPresetName = '';
            window._igenLoadedPresetSnapshot = null;
            window.checkIgenPresetUI();
            window.renderIgenPresetLibrary();
            window.updateIgenDirtyState();
            if (typeof window._igenDebounceSave === 'function') window._igenDebounceSave();
            return;
        }

        try {
            const r = await fetch('/hecos/api/plugins/image_gen/presets/load/' + encodeURIComponent(name), { cache: 'no-store' });
            const d = await r.json();
            if (!d.ok) {
                _igenAlert('Error loading preset: ' + (d.error || 'Unknown error'));
                return;
            }

            window._igenDisableAutoSave = true;
            try {
                window.applyIgenConfig(d.config, { fromPreset: true });
                if (typeof window.onProviderChanged === 'function') {
                    await window.onProviderChanged(false, 0);
                }
            } finally {
                window._igenDisableAutoSave = false;
            }

            if (sel) sel.value = name;
            window._igenLoadedPresetName = name;
            window._igenLoadedPresetSnapshot = _normalizeForCompare(window.collectIgenConfig());

            window.checkIgenPresetUI();
            window.renderIgenPresetLibrary();
            window.updateIgenLiveSummary();
            window.updateIgenDirtyState();

            if (typeof window.saveIgenConfig === 'function') {
                await window.saveIgenConfig(true);
            }
            _igenAlert("Preset '" + name + "' loaded.", 'info');
        } catch (err) {
            window._igenDisableAutoSave = false;
            console.error('[igen] preset load error', err);
            _igenAlert('Failed to load preset: ' + err.message);
        }
    };

    // ── Save New Custom Preset (+ New) ─────────────────────────────────────────

    async function _saveCustomPreset(name, overwrite) {
        const config = window.collectIgenConfig();
        if (!config.model) {
            return {
                ok: false,
                error: 'No model selected. Select a model first (or click Refresh once SwarmUI is ready) before saving the preset.'
            };
        }
        const r = await fetch('/hecos/api/plugins/image_gen/presets/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                config: config,
                overwrite: !!overwrite,
                set_active: true
            })
        });
        const d = await r.json();
        if (d.ok) {
            const savedName = d.name || name;
            await window.loadIgenPresets(savedName);
            window._igenLoadedPresetName = savedName;
            window._igenLoadedPresetSnapshot = _normalizeForCompare(window.collectIgenConfig());
            window.checkIgenPresetUI();
            window.renderIgenPresetLibrary();
            window.updateIgenDirtyState();
            if (typeof window.saveIgenConfig === 'function') {
                await window.saveIgenConfig(true);
            }
            return { ok: true, name: savedName };
        }
        return { ok: false, error: d.error || 'Save failed' };
    }

    window.saveIgenPreset = function() {
        const defName = _nextCustomName('custom');
        _igenPrompt('Enter a name for the new Image Gen preset (saves full configuration):', async (name) => {
            const res = await _saveCustomPreset(name, false);
            if (res.ok) {
                _igenAlert("Preset '" + res.name + "' saved!", 'success');
            } else {
                _igenAlert(res.error, 'error');
            }
        }, defName);
    };

    // ── Update Selected Preset (with built-in overwrite protection) ────────────

    window.updateIgenPreset = async function() {
        const sel = document.getElementById('igen-preset');
        const name = sel ? sel.value : '';
        const meta = _findPresetMeta(name);

        // Protect built-in or empty selection: prompt to save as a new custom preset (core Voice/VF standard)
        if (!name || !meta || meta.builtin) {
            const defName = name ? _suggestCopyName(name) : _nextCustomName('custom');
            const promptMsg = name
                ? ("Built-in preset '" + name + "' cannot be overwritten.\nEnter a name to save your current settings as a new custom preset:")
                : 'No custom preset selected.\nEnter a name to save your current settings as a new custom preset:';
            _igenPrompt(promptMsg, async (customName) => {
                const res = await _saveCustomPreset(customName, false);
                if (res.ok) {
                    _igenAlert("Saved as new custom preset '" + res.name + "'!", 'success');
                } else {
                    _igenAlert(res.error, 'error');
                }
            }, defName);
            return;
        }

        const res = await _saveCustomPreset(name, true);
        if (res.ok) {
            const btn = document.getElementById('igen-preset-update-btn');
            if (btn) {
                const orig = btn.innerHTML;
                btn.innerHTML = '<i class="fas fa-check"></i> Saved!';
                setTimeout(() => { btn.innerHTML = orig; }, 1400);
            }
            _igenAlert("Preset '" + res.name + "' updated!", 'success');
        } else {
            _igenAlert('Update failed: ' + res.error, 'error');
        }
    };

    // ── Rename Custom Preset ───────────────────────────────────────────────────

    window.renameIgenPreset = function(explicitOldName) {
        const sel = document.getElementById('igen-preset');
        const oldName = (explicitOldName !== undefined) ? explicitOldName : (sel ? sel.value : '');
        if (!oldName) {
            _igenAlert('Select a custom preset to rename first.', 'warning');
            return;
        }
        const meta = _findPresetMeta(oldName);
        if (!meta || meta.builtin) {
            _igenAlert('Built-in presets cannot be renamed. Use Duplicate or New to create an editable custom copy.', 'warning');
            return;
        }

        _igenPrompt("Rename preset '" + oldName + "' to:", async (newName) => {
            if (!newName || newName === oldName) return;
            try {
                const r = await fetch('/hecos/api/plugins/image_gen/presets/rename', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ old_name: oldName, new_name: newName })
                });
                const d = await r.json();
                if (d.ok) {
                    const finalName = d.new_name || newName;
                    const wasActive = (sel && sel.value === oldName);
                    await window.loadIgenPresets(wasActive ? finalName : (sel ? sel.value : ''));
                    if (wasActive) {
                        window._igenLoadedPresetName = finalName;
                        if (typeof window.saveIgenConfig === 'function') await window.saveIgenConfig(true);
                    }
                    _igenAlert("Preset renamed to '" + finalName + "'!", 'success');
                } else {
                    _igenAlert(d.error || 'Rename failed.', 'error');
                }
            } catch (err) {
                _igenAlert('Rename error: ' + err.message, 'error');
            }
        }, oldName);
    };

    // ── Duplicate Any Preset (Built-in or Custom) ──────────────────────────────

    window.duplicateIgenPreset = function(explicitSourceName) {
        const sel = document.getElementById('igen-preset');
        const sourceName = (explicitSourceName !== undefined) ? explicitSourceName : (sel ? sel.value : '');
        if (!sourceName) {
            _igenAlert('Select a preset to duplicate first.', 'warning');
            return;
        }

        const suggested = _suggestCopyName(sourceName);
        _igenPrompt("Duplicate '" + sourceName + "' as new custom preset:", async (newName) => {
            if (!newName) return;
            try {
                const r = await fetch('/hecos/api/plugins/image_gen/presets/duplicate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source_name: sourceName, new_name: newName })
                });
                const d = await r.json();
                if (d.ok) {
                    const createdName = d.name || newName;
                    await window.loadIgenPresets(createdName);
                    await window.loadIgenPreset(createdName);
                    _igenAlert("Duplicated as custom preset '" + createdName + "'!", 'success');
                } else {
                    _igenAlert(d.error || 'Duplicate failed.', 'error');
                }
            } catch (err) {
                _igenAlert('Duplicate error: ' + err.message, 'error');
            }
        }, suggested);
    };

    // ── Reset Parameters (Reload Selected Preset or Reset to Defaults) ─────────

    window.resetIgenPreset = function() {
        const sel = document.getElementById('igen-preset');
        const name = sel ? sel.value : '';

        if (name) {
            _igenConfirm("Reload saved parameters of preset '" + name + "' and discard unsaved tweaks?", async () => {
                await window.loadIgenPreset(name);
                _igenAlert("Parameters reloaded from '" + name + "'.", 'info');
            });
            return;
        }

        _igenConfirm('Reset Image Gen parameters to default values?', async () => {
            try {
                const r = await fetch('/hecos/api/plugins/image_gen/presets/defaults', { cache: 'no-store' });
                const d = await r.json();
                if (!d.ok || !d.config) {
                    _igenAlert('Failed to load defaults.', 'error');
                    return;
                }
                window._igenDisableAutoSave = true;
                try {
                    window.applyIgenConfig(d.config, { fromPreset: true });
                    if (typeof window.onProviderChanged === 'function') {
                        await window.onProviderChanged(false, 0);
                    }
                } finally {
                    window._igenDisableAutoSave = false;
                }
                if (sel) sel.value = '';
                window._igenLoadedPresetName = '';
                window._igenLoadedPresetSnapshot = null;
                window.checkIgenPresetUI();
                window.renderIgenPresetLibrary();
                window.updateIgenLiveSummary();
                window.updateIgenDirtyState();
                if (typeof window.saveIgenConfig === 'function') await window.saveIgenConfig(true);
                _igenAlert('Image Gen parameters reset to defaults.', 'info');
            } catch (err) {
                window._igenDisableAutoSave = false;
                _igenAlert('Reset error: ' + err.message, 'error');
            }
        });
    };

    // ── Delete Custom Preset ───────────────────────────────────────────────────

    window.deleteIgenPreset = function(explicitName) {
        const sel = document.getElementById('igen-preset');
        const name = (explicitName !== undefined) ? explicitName : (sel ? sel.value : '');
        if (!name) {
            _igenAlert('No preset selected to delete.', 'warning');
            return;
        }
        const meta = _findPresetMeta(name);
        if (!meta || meta.builtin) {
            _igenAlert('Built-in presets cannot be deleted.', 'warning');
            return;
        }

        _igenConfirm("Are you sure you want to permanently delete preset '" + name + "'?", async () => {
            try {
                const r = await fetch('/hecos/api/plugins/image_gen/presets/delete/' + encodeURIComponent(name), {
                    method: 'DELETE'
                });
                const d = await r.json();
                if (d.ok) {
                    const wasActive = (sel && sel.value === name);
                    if (wasActive) {
                        window._igenLoadedPresetName = '';
                        window._igenLoadedPresetSnapshot = null;
                    }
                    await window.loadIgenPresets(wasActive ? '' : (sel ? sel.value : ''));
                    if (wasActive && typeof window.saveIgenConfig === 'function') {
                        await window.saveIgenConfig(true);
                    }
                    _igenAlert("Preset '" + name + "' deleted.", 'info');
                } else {
                    _igenAlert('Delete failed: ' + (d.error || 'Unknown error'), 'error');
                }
            } catch (err) {
                _igenAlert('Delete error: ' + err.message, 'error');
            }
        });
    };

    // ── Set / Clear Default Preset (⭐) ────────────────────────────────────────

    window.setIgenDefaultPreset = async function(targetName) {
        const sel = document.getElementById('igen-preset');
        const currentSelected = sel ? sel.value : '';
        const nameToSet = (targetName !== undefined) ? String(targetName) : currentSelected;

        try {
            const r = await fetch('/hecos/api/plugins/image_gen/presets/set-default', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: nameToSet })
            });
            const d = await r.json();
            if (d.ok) {
                await window.loadIgenPresets(currentSelected);
                if (nameToSet) {
                    _igenAlert("⭐ '" + nameToSet + "' set as startup default!", 'success');
                } else {
                    _igenAlert('Startup default preset cleared.', 'info');
                }
            } else {
                _igenAlert('Failed to set default: ' + (d.error || 'Unknown error'), 'error');
            }
        } catch (e) {
            console.error(e);
            _igenAlert('Network error.', 'error');
        }
    };

    window.toggleIgenDefaultPreset = async function(explicitName) {
        const sel = document.getElementById('igen-preset');
        const name = (explicitName !== undefined) ? explicitName : (sel ? sel.value : '');
        if (!name) {
            _igenAlert('Select a preset first to set it as startup default.', 'warning');
            return;
        }
        const meta = _findPresetMeta(name);
        if (meta && meta.is_default) {
            await window.setIgenDefaultPreset('');
        } else {
            await window.setIgenDefaultPreset(name);
        }
    };

    // ── Export / Import JSON ───────────────────────────────────────────────────

    window.exportIgenPreset = async function(explicitName) {
        const sel = document.getElementById('igen-preset');
        const name = (explicitName !== undefined) ? explicitName : (sel ? sel.value : '');
        if (!name) {
            _igenAlert('Select a preset to export first.', 'warning');
            return;
        }
        try {
            const r = await fetch('/hecos/api/plugins/image_gen/presets/export/' + encodeURIComponent(name), { cache: 'no-store' });
            const d = await r.json();
            if (!d.ok || !d.preset) {
                _igenAlert('Export failed: ' + (d.error || 'Unknown error'), 'error');
                return;
            }
            const blob = new Blob([JSON.stringify(d.preset, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            const safeFile = name.replace(/[^a-z0-9_\-]+/gi, '_').replace(/^_+|_+$/g, '') || 'image_gen_preset';
            a.href = url;
            a.download = safeFile + '.igen_preset.json';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            _igenAlert("Exported '" + name + "'.", 'success');
        } catch (err) {
            _igenAlert('Export error: ' + err.message, 'error');
        }
    };

    window.importIgenPreset = function(event) {
        const file = event && event.target && event.target.files ? event.target.files[0] : null;
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async function(e) {
            try {
                const parsed = JSON.parse(e.target.result);
                const fallbackName = file.name.replace(/\.igen_preset\.json$/i, '').replace(/\.json$/i, '') || 'Imported Preset';
                const payload = (parsed && parsed.config)
                    ? { name: parsed.name || fallbackName, description: parsed.description || '', config: parsed.config }
                    : { name: fallbackName, description: '', config: parsed };

                const r = await fetch('/hecos/api/plugins/image_gen/presets/import', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ preset: payload, auto_rename: true })
                });
                const d = await r.json();
                if (d.ok && d.name) {
                    await window.loadIgenPresets(d.name);
                    await window.loadIgenPreset(d.name);
                    _igenAlert("Imported preset '" + d.name + "'!", 'success');
                } else {
                    _igenAlert('Import failed: ' + (d.error || 'Invalid preset file'), 'error');
                }
            } catch (err) {
                _igenAlert('Invalid JSON preset file: ' + err.message, 'error');
            } finally {
                if (event && event.target) event.target.value = '';
            }
        };
        reader.readAsText(file);
    };

    // ── Toolbar State & Dirty Indicator ────────────────────────────────────────

    window.checkIgenPresetUI = function() {
        const sel        = document.getElementById('igen-preset');
        const typeBadge  = document.getElementById('igen-preset-type-badge');
        const updateBtn  = document.getElementById('igen-preset-update-btn');
        const renameBtn  = document.getElementById('igen-preset-rename-btn');
        const dupBtn     = document.getElementById('igen-preset-duplicate-btn');
        const deleteBtn  = document.getElementById('igen-preset-delete-btn');
        const defaultBtn = document.getElementById('igen-preset-default-btn');
        const exportBtn  = document.getElementById('igen-preset-export-btn');
        if (!sel) return;

        const name      = sel.value || '';
        const meta      = _findPresetMeta(name);
        const isEmpty   = !name || !meta;
        const isBuiltin = meta ? !!meta.builtin : false;
        const isDefault = meta ? !!meta.is_default : false;

        if (typeBadge) {
            typeBadge.className = 'igen-preset-pill ' + (isEmpty ? 'igen-pill-neutral' : (isBuiltin ? 'igen-pill-builtin' : 'igen-pill-custom'));
            typeBadge.textContent = isEmpty ? 'No Preset' : (isBuiltin ? 'Built-in' : 'Custom');
        }

        // All buttons remain VISIBLE (Hecos core standard); non-applicable ones get subtle muted styling & clear tooltips
        if (updateBtn) {
            updateBtn.title = isEmpty
                ? 'Save current settings as a new custom preset'
                : (isBuiltin
                    ? "Built-in preset is read-only — click to save current settings as a new custom preset"
                    : "Overwrite custom preset '" + name + "' with current settings");
        }
        if (renameBtn) {
            renameBtn.classList.toggle('igen-btn-muted', isEmpty || isBuiltin);
            renameBtn.title = (isEmpty || isBuiltin)
                ? 'Only custom presets can be renamed (use Duplicate to make a custom copy)'
                : "Rename custom preset '" + name + "'";
        }
        if (dupBtn) {
            dupBtn.classList.toggle('igen-btn-muted', isEmpty);
        }
        if (deleteBtn) {
            deleteBtn.classList.toggle('igen-btn-muted', isEmpty || isBuiltin);
            deleteBtn.title = (isEmpty || isBuiltin)
                ? 'Built-in presets cannot be deleted'
                : "Delete custom preset '" + name + "'";
        }
        if (exportBtn) {
            exportBtn.classList.toggle('igen-btn-muted', isEmpty);
        }

        if (defaultBtn) {
            defaultBtn.classList.toggle('igen-btn-muted', isEmpty);
            defaultBtn.classList.toggle('igen-btn-star-active', !isEmpty && isDefault);
            if (!isEmpty && isDefault) {
                defaultBtn.innerHTML = '<i class="fas fa-star"></i> Default';
                defaultBtn.title = "Active startup default — click to clear";
            } else {
                defaultBtn.innerHTML = '<i class="far fa-star"></i> Default';
                defaultBtn.title = isEmpty
                    ? 'Select a preset first to set as startup default'
                    : "Load '" + name + "' automatically on startup";
            }
        }
    };

    window.updateIgenDirtyState = function() {
        const badge = document.getElementById('igen-preset-dirty-badge');
        if (!badge) return;
        const sel = document.getElementById('igen-preset');
        const active = sel ? sel.value : '';
        if (!active || !window._igenLoadedPresetSnapshot || window._igenLoadedPresetName !== active) {
            badge.style.display = 'none';
            return;
        }
        const nowSnap = _normalizeForCompare(window.collectIgenConfig());
        badge.style.display = (nowSnap && nowSnap !== window._igenLoadedPresetSnapshot) ? 'inline-flex' : 'none';
    };

    // ── Presets Library Tab Renderer ───────────────────────────────────────────

    window.renderIgenPresetLibrary = function() {
        const customBox  = document.getElementById('igen-custom-presets-list');
        const builtinBox = document.getElementById('igen-builtin-presets-list');
        if (!customBox && !builtinBox) return;

        const sel = document.getElementById('igen-preset');
        const activeName = sel ? sel.value : '';
        const list = window._igenPresetsList || [];
        const customList  = list.filter(p => !p.builtin);
        const builtinList = list.filter(p => p.builtin);

        const renderRow = (p) => {
            const isActive = (p.name === activeName);
            const jsName = _escJs(p.name);
            const provLabel = p.provider === 'swarmui' ? 'SwarmUI' : (p.provider || '—');
            const metaParts = [
                provLabel,
                p.model || '—',
                (p.num_inference_steps != null ? p.num_inference_steps + ' steps' : ''),
                (p.guidance_scale != null ? 'CFG ' + Number(p.guidance_scale).toFixed(1) : ''),
                p.aspect_ratio || ''
            ].filter(Boolean);
            if (p.loras_count > 0) metaParts.push(p.loras_count + ' LoRA');

            let actionsHtml = '';
            actionsHtml += `<button type="button" class="igen-lib-icon-btn ${p.is_default ? 'star-active' : ''}" onclick="toggleIgenDefaultPreset('${jsName}')" title="${p.is_default ? 'Clear startup default' : 'Set as startup default'}"><i class="${p.is_default ? 'fas' : 'far'} fa-star"></i></button>`;
            actionsHtml += `<button type="button" class="igen-lib-icon-btn" onclick="duplicateIgenPreset('${jsName}')" title="Duplicate as custom preset"><i class="fas fa-copy"></i></button>`;
            if (!p.builtin) {
                actionsHtml += `<button type="button" class="igen-lib-icon-btn" onclick="renameIgenPreset('${jsName}')" title="Rename preset"><i class="fas fa-edit"></i></button>`;
            }
            actionsHtml += `<button type="button" class="igen-lib-icon-btn" onclick="exportIgenPreset('${jsName}')" title="Export preset JSON"><i class="fas fa-file-export"></i></button>`;
            if (!p.builtin) {
                actionsHtml += `<button type="button" class="igen-lib-icon-btn danger" onclick="deleteIgenPreset('${jsName}')" title="Delete preset"><i class="fas fa-trash"></i></button>`;
            }

            return `<div class="igen-lib-item ${isActive ? 'igen-lib-active' : ''}">` +
                `<div class="igen-lib-info" onclick="loadIgenPreset('${jsName}')" title="Click to load '${_esc(p.name)}'">` +
                    `<div class="igen-lib-name">` +
                        `<span>${_esc(p.name)}</span>` +
                        (p.is_default ? `<span class="igen-preset-pill igen-pill-dirty" style="font-size:9.5px;"><i class="fas fa-star"></i> Default</span>` : '') +
                        (isActive ? `<span class="igen-preset-pill igen-pill-custom" style="font-size:9.5px;">Active</span>` : '') +
                    `</div>` +
                    `<div class="igen-lib-meta">${_esc(metaParts.join(' · '))}</div>` +
                `</div>` +
                `<div class="igen-lib-actions">${actionsHtml}</div>` +
            `</div>`;
        };

        if (customBox) {
            customBox.innerHTML = customList.length
                ? customList.map(renderRow).join('')
                : '<div class="igen-lib-empty">No custom presets yet. Click <strong>+ New</strong> above to save your current configuration, or <strong>Duplicate</strong> any built-in preset below.</div>';
        }
        if (builtinBox) {
            builtinBox.innerHTML = builtinList.length
                ? builtinList.map(renderRow).join('')
                : '<div class="igen-lib-empty">No built-in presets available.</div>';
        }
    };

    // ── Live Summary ───────────────────────────────────────────────────────────

    window.updateIgenLiveSummary = function() {
        const summEl = document.getElementById('igen-live-summary');
        if (!summEl) return;

        const c = window.collectIgenConfig ? window.collectIgenConfig() : null;
        if (!c) return;

        let html = '';
        const row = (label, val) => {
            if (!val) return;
            html += `<div style="display:flex; justify-content:space-between; gap:12px; margin-bottom:2px;">` +
                `<span style="color:var(--muted);">${_esc(label)}:</span>` +
                `<span style="font-weight:500; text-align:right; word-break:break-word;">${_esc(val)}</span>` +
            `</div>`;
        };

        row('Provider', c.provider === 'swarmui' ? 'SwarmUI (Local)' : c.provider);
        row('Model', c.model);

        if (c.provider === 'swarmui') {
            row('VAE', c.vae || 'Default');
            if (c.loras && c.loras.length) row('LoRAs', c.loras.length + ' active (' + c.loras.slice(0, 2).join(', ') + (c.loras.length > 2 ? '…' : '') + ')');
            row('Sampler / Scheduler', (c.sampler || 'euler') + ' / ' + (c.scheduler || 'simple'));
        }

        const neg = c.enable_negative_prompt ? 'ON' : 'OFF';
        const enrich = c.auto_enrich ? 'ON' : 'OFF';
        const upsamp = c.optimize_for_flux ? 'ON' : 'OFF';
        const cfgVal = Number.isFinite(c.guidance_scale) ? c.guidance_scale.toFixed(1) : '0.0';
        let stepsCfgStr = `${c.num_inference_steps}  |  CFG ${cfgVal}`;
        if (c.provider === 'swarmui' && Number.isFinite(c.flux_guidance_scale) && c.flux_guidance_scale >= 0) {
            stepsCfgStr += `  |  FluxG ${c.flux_guidance_scale.toFixed(1)}`;
        }
        if (c.provider === 'swarmui' && Number.isFinite(c.sigma_shift) && c.sigma_shift >= 0) {
            stepsCfgStr += `  |  Shift ${c.sigma_shift.toFixed(2)}`;
        }

        row('Steps / Guidance', stepsCfgStr);
        row('Size', `${c.width}×${c.height} (${c.aspect_ratio})`);
        row('Style', c.style && c.style !== 'none' ? c.style : 'None');
        row('Prompt Pipeline', `Flux Upsampler: ${upsamp}  |  Neg: ${neg}  |  Enrich: ${enrich}`);

        summEl.innerHTML = html;
    };

    // Hook into any config change inside #tab-igen to update live summary & dirty dot
    function _scheduleSummaryAndDirty() {
        clearTimeout(window._summDebounce);
        window._summDebounce = setTimeout(() => {
            window.updateIgenLiveSummary();
            window.updateIgenDirtyState();
        }, 150);
    }

    document.addEventListener('change', (e) => {
        if (e.target && e.target.closest && e.target.closest('#tab-igen') && e.target.id !== 'igen-preset') {
            _scheduleSummaryAndDirty();
        }
    });
    document.addEventListener('input', (e) => {
        if (e.target && e.target.closest && e.target.closest('#tab-igen') && e.target.id !== 'igen-preset') {
            _scheduleSummaryAndDirty();
        }
    });
    document.addEventListener('click', (e) => {
        if (e.target && e.target.closest && e.target.closest('#igen-loras-list')) {
            _scheduleSummaryAndDirty();
        }
    });

})();
