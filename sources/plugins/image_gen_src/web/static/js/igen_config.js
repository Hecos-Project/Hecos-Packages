/**
 * igen_config.js — Image Gen Panel: Collect, Apply & Save Config
 * collectIgenConfig, applyIgenConfig, saveIgenConfig, saveKeyToEnv.
 */

// ── Config Save ────────────────────────────────────────────────────────────────

window.saveIgenConfig = async function(silent = false) {
    const cfg = window.collectIgenConfig();
    const presetEl = document.getElementById('igen-preset');
    cfg.active_preset = presetEl ? presetEl.value : '';
    // Never clobber saved model on disk with an empty string if dropdown hasn't populated yet
    if (!cfg.model) {
        delete cfg.model;
    }
    if (typeof window.updateIgenLiveSummary === 'function') window.updateIgenLiveSummary();
    if (typeof window.updateIgenDirtyState === 'function') window.updateIgenDirtyState();

    const statusEl = document.getElementById('igen-save-status');
    if (!silent && statusEl) {
        statusEl.textContent = 'Saving...';
        statusEl.style.color = 'var(--muted)';
    }

    try {
        const res = await fetch('/hecos/api/plugins/image_gen/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_gen: cfg })
        });
        const data = await res.json();
        if (data.ok) {
            if (statusEl) {
                statusEl.textContent = '\u2713 Saved';
                statusEl.style.color = 'var(--ok, #2ecc71)';
                setTimeout(() => { statusEl.textContent = ''; }, 2000);
            }
        } else {
            console.error('[ImageGen] Save failed:', data.error);
            if (statusEl) { statusEl.textContent = 'Save error!'; statusEl.style.color = 'var(--error, #e74c3c)'; }
        }
    } catch (e) {
        console.error('[ImageGen] Save config error:', e);
    }
};

window.saveKeyToEnv = async function() {
    let keyInput = document.getElementById('igen-api-key');
    const provSel = document.getElementById('igen-provider');
    if (!provSel) return;

    if (provSel.value === 'horde') keyInput = document.getElementById('horde-api-key');
    if (!keyInput) return;

    const key = keyInput.value.trim();
    if (!key) { _igenAlert('Please enter a key to save globally.'); return; }

    _igenConfirm('Save this API key to the global .env file for ' + provSel.value + '?', async () => {
        try {
            const res = await fetch('/hecos/api/plugins/image_gen/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image_gen: {
                    _internal_save_to_env: true,
                    api_key: key,
                    provider: provSel.value,
                    api_key_comment: 'ImageGen Panel'
                }})
            });
            const data = await res.json();
            if (data.ok) { _igenAlert('Key saved globally to .env.', 'success'); keyInput.value = ''; }
            else { _igenAlert('Error saving key: ' + data.error); }
        } catch (e) { console.error(e); _igenAlert('Network error.'); }
    });
};

// ── Collect & Apply Config ─────────────────────────────────────────────────────

window.collectIgenConfig = function() {
    const get = (id, def) => { const el = document.getElementById(id); return el ? el.value : def; };
    const chk = (id, def) => { const el = document.getElementById(id); return el ? el.checked : def; };
    const numInt = (id, def) => {
        const v = parseInt(get(id, def), 10);
        return Number.isFinite(v) ? v : def;
    };
    const numFloat = (id, def) => {
        const v = parseFloat(get(id, def));
        return Number.isFinite(v) ? v : def;
    };

    let loras = [];
    const lorasEl = document.getElementById('igen-loras');
    if (window._selectedLoras instanceof Set && (window._selectedLoras.size > 0 || (lorasEl && lorasEl.options.length > 0))) {
        loras = Array.from(window._selectedLoras);
    } else if (lorasEl && lorasEl.selectedOptions) {
        loras = Array.from(lorasEl.selectedOptions).map(o => o.value);
    }

    const numOptFloat = (id) => {
        const raw = String(get(id, '') ?? '').trim();
        if (raw === '') return -1.0;
        const v = parseFloat(raw);
        return (Number.isFinite(v) && v >= 0) ? v : -1.0;
    };

    return {
        provider:                  get('igen-provider', 'pollinations'),
        hf_provider:               get('igen-hf-provider', 'hf-inference'),
        model:                     get('igen-model', 'flux'),
        aspect_ratio:              get('igen-aspect-ratio', '1:1'),
        width:                     numInt('igen-width', 1024),
        height:                    numInt('igen-height', 1024),
        seed:                      numInt('igen-seed', -1),
        sampler:                   get('igen-sampler', 'euler'),
        scheduler:                 get('igen-scheduler', 'simple'),
        guidance_scale:            numFloat('igen-guidance', 0.0),
        num_inference_steps:       numInt('igen-steps', 4),
        flux_guidance_scale:       numOptFloat('igen-flux-guidance'),
        sigma_shift:               numOptFloat('igen-sigma-shift'),
        enable_negative_prompt:    chk('igen-use-neg-prompt', false),
        negative_prompt:           get('igen-neg-prompt', ''),
        auto_enrich:               chk('igen-auto-enrich', false),
        enrich_keywords:           get('igen-enrich-keywords', ''),
        style:                     get('igen-style', 'none'),
        nologo:                    chk('igen-nologo', true),
        optimize_for_flux:         chk('igen-optimize-flux', false),
        flux_refiner_instructions: get('igen-flux-refiner-instructions', ''),
        show_metadata_in_chat:     chk('igen-show-metadata', false),
        routing_override:          get('igen-routing-override', ''),
        enabled:                   chk('igen-enabled', true),
        api_key:                   get('igen-api-key', ''),
        horde_api_key:             get('horde-api-key', ''),
        horde_nsfw:                chk('horde-nsfw', true),
        horde_worker_blacklist:    get('horde-worker-blacklist', ''),
        vae:                       get('igen-vae', ''),
        loras:                     loras,
        cloud_enabled:             chk('igen-cloud-enabled', false),
        local: {
            auto_start:            chk('igen-local-autostart', true),
            install_path:          (get('igen-local-install-path', '') || '').trim(),
        },
    };
};

window.applyIgenConfig = function(cfg, opts) {
    cfg = cfg || {};
    opts = opts || {};
    const fromPreset = !!opts.fromPreset;

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    const chk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };

    // Determine cloud toggle state first so cloud provider options aren't disabled when applying a cloud preset
    let cloudEnabled = cfg.cloud_enabled;
    if (fromPreset && cloudEnabled === undefined) {
        const prov = cfg.provider || 'swarmui';
        if (prov !== 'swarmui') {
            cloudEnabled = true;
        } else {
            const curChk = document.getElementById('igen-cloud-enabled');
            cloudEnabled = curChk ? curChk.checked : false;
        }
    }
    if (cloudEnabled !== undefined) {
        chk('igen-cloud-enabled', cloudEnabled);
        chk('igen-cloud-enabled-mirror', cloudEnabled);
    }

    const pEl = document.getElementById('igen-provider');
    const provVal = cfg.provider || 'swarmui';
    if (pEl) {
        pEl.setAttribute('data-initial-val', provVal);
        // Temporarily un-disable target option if cloudEnabled is now true
        if (cloudEnabled) {
            Array.from(pEl.options).forEach(o => { o.disabled = false; });
            Array.from(pEl.querySelectorAll('optgroup')).forEach(g => { g.disabled = false; });
        }
        pEl.value = provVal;
    }

    set('igen-hf-provider', cfg.hf_provider || 'hf-inference');

    const mEl = document.getElementById('igen-model');
    const defaultModel = (provVal === 'pollinations') ? 'flux' : '';
    const targetModel = cfg.model || defaultModel;
    if (mEl) {
        if (targetModel) {
            mEl.setAttribute('data-initial-val', targetModel);
            // Ensure option exists immediately so collectIgenConfig never sees ""
            const hasOpt = Array.from(mEl.options).some(o => o.value === targetModel);
            if (!hasOpt) {
                const o = document.createElement('option');
                o.value = targetModel;
                o.textContent = targetModel;
                mEl.appendChild(o);
            }
            mEl.value = targetModel;
        }
    }

    set('igen-aspect-ratio', cfg.aspect_ratio || '1:1');
    set('igen-width',        cfg.width        ?? 1024);
    set('igen-height',       cfg.height       ?? 1024);
    set('igen-seed',         cfg.seed         ?? -1);
    set('igen-sampler',      cfg.sampler      || 'euler');
    set('igen-scheduler',    cfg.scheduler    || 'simple');

    // Never wipe existing API keys when loading a preset that omits them
    if (!fromPreset || cfg.api_key !== undefined) {
        set('igen-api-key', cfg.api_key || '');
    }
    if (!fromPreset || cfg.horde_api_key !== undefined) {
        set('horde-api-key', cfg.horde_api_key || '');
    }
    if (!fromPreset || cfg.horde_nsfw !== undefined) {
        chk('horde-nsfw', cfg.horde_nsfw !== undefined ? cfg.horde_nsfw : true);
    }
    if (!fromPreset || cfg.horde_worker_blacklist !== undefined) {
        set('horde-worker-blacklist', cfg.horde_worker_blacklist || '');
    }

    // VAE: store pending initial value so onProviderChanged restores it after async fetch
    const vaeVal = cfg.vae || '';
    const vEl = document.getElementById('igen-vae');
    if (vEl) {
        vEl.setAttribute('data-initial-val', vaeVal);
        vEl.value = vaeVal;
    }

    // Local backend settings: keep user's install_path & auto_start untouched when loading a preset
    if (!fromPreset && cfg.local) {
        const localCfg = cfg.local || {};
        chk('igen-local-autostart', localCfg.auto_start !== undefined ? localCfg.auto_start : true);
        set('igen-local-install-path', localCfg.install_path || '');
    }

    // LoRAs: always sync Set + pending list + hidden select (clears old LoRAs when preset has none)
    const loraList = Array.isArray(cfg.loras) ? cfg.loras.slice() : [];
    window._igenPendingLoras = loraList.slice();
    window._selectedLoras = new Set(loraList);
    const lorasEl = document.getElementById('igen-loras');
    if (lorasEl) {
        Array.from(lorasEl.options).forEach(o => {
            o.selected = window._selectedLoras.has(o.value);
        });
    }
    if (typeof window.renderLoRAList === 'function') {
        window.renderLoRAList(document.getElementById('igen-lora-search')?.value);
    }

    const guidance = cfg.guidance_scale ?? 0.0;
    set('igen-guidance', guidance);
    const gValEl = document.getElementById('igen-guidance-val');
    if (gValEl) gValEl.textContent = parseFloat(guidance).toFixed(1);

    const steps = cfg.num_inference_steps || 4;
    set('igen-steps', steps);
    const sValEl = document.getElementById('igen-steps-val');
    if (sValEl) sValEl.textContent = steps;

    const fgRaw = cfg.flux_guidance_scale;
    set('igen-flux-guidance', (fgRaw !== undefined && fgRaw !== null && Number(fgRaw) >= 0) ? String(fgRaw) : '');
    const ssRaw = cfg.sigma_shift;
    set('igen-sigma-shift', (ssRaw !== undefined && ssRaw !== null && Number(ssRaw) >= 0) ? String(ssRaw) : '');

    chk('igen-use-neg-prompt',  cfg.enable_negative_prompt);
    set('igen-neg-prompt',      cfg.negative_prompt     || '');
    chk('igen-auto-enrich',     cfg.auto_enrich);
    set('igen-enrich-keywords', cfg.enrich_keywords     || '');
    set('igen-style',           cfg.style               || 'none');
    chk('igen-nologo',          cfg.nologo              ?? true);
    const optFlux = !!cfg.optimize_for_flux;
    chk('igen-optimize-flux',   optFlux);
    const refBox = document.getElementById('igen-flux-refiner-box');
    if (refBox) refBox.style.display = optFlux ? 'block' : 'none';
    if (!fromPreset || cfg.flux_refiner_instructions !== undefined) {
        set('igen-flux-refiner-instructions', cfg.flux_refiner_instructions || '');
    }
    if (!fromPreset || cfg.show_metadata_in_chat !== undefined) {
        chk('igen-show-metadata', cfg.show_metadata_in_chat ?? true);
    }
    if (!fromPreset || cfg.routing_override !== undefined) {
        set('igen-routing-override', cfg.routing_override || '');
    }
    if (!fromPreset || cfg.enabled !== undefined) {
        chk('igen-enabled', cfg.enabled ?? true);
    }

    if (typeof window.onAspectRatioChanged === 'function') window.onAspectRatioChanged(false);
    if (typeof window._applyCloudToggleState === 'function') window._applyCloudToggleState();
    if (typeof window.updateIgenLiveSummary === 'function') window.updateIgenLiveSummary();
};

window.loadIgenPhotorealRefinerTemplate = function() {
    const el = document.getElementById('igen-flux-refiner-instructions');
    if (!el) return;
    el.value =
        'Rewrite the user image request into a concise, vivid English photography caption (60-110 words) for Flux. ' +
        'Describe natural candid framing, camera & lens (e.g. 35mm or 85mm f/2.0), directional real-world lighting, natural skin texture with subtle pores and fine imperfections, fabric/environment texture, and realistic depth of field. ' +
        'STRICTLY avoid CGI buzzwords (hyper-realistic, 8k, masterpiece, flawless skin, synthetic skin, ultra-detailed) and omit model/code numbers from character names. ' +
        'Output ONLY the final English prompt with no preamble or quotes.';
    if (typeof window._igenDebounceSave === 'function') window._igenDebounceSave();
    if (typeof window.showToast === 'function') window.showToast('Loaded photoreal Flux upsampler template.', 'info');
};

window.loadIgenPhotorealRoutingTemplate = function() {
    const el = document.getElementById('igen-routing-override');
    if (!el) return;
    el.value =
        'When calling IMAGE_GEN__generate_image or /img, always leave provider and model empty so the user preset is used. ' +
        'Write descriptive English photography prompts in natural prose: specify camera/lens (e.g. candid 35mm film photo or 85mm f/2 portrait), authentic directional lighting, natural candid pose, real environment depth, and natural human skin texture with subtle pores and light imperfections. ' +
        'NEVER use CGI/3D buzzwords ("hyper-realistic", "photorealistic", "flawless skin", "smooth synthetic skin", "8k", "masterpiece") and never write numeric IDs (like "9800") inside the visual prompt.';
    if (typeof window.saveIgenConfig === 'function') window.saveIgenConfig();
    if (typeof window.showToast === 'function') window.showToast('Loaded Photoreal Flux guide into Directives / Override.', 'info');
};
