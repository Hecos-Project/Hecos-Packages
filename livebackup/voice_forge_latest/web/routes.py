"""
Voice Forge - Web API Routes
Autonomous REST endpoints for the Voice Forge Studio UI in Hecos.
Registers via init_plugin_routes during HPM module scanning.
"""

import os
import sys
import time
import uuid
import traceback
from pathlib import Path
from flask import request, jsonify, send_file

def init_plugin_routes(app, cfg_mgr, root_dir, logger, get_sm=None):
    plugin_path = Path(__file__).resolve().parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))

    from hecos.core.progress import progress
    from core.recipe import VoiceRecipe
    from core.multilang_corpus import get_corpus_languages, get_all_samples_for_language, get_default_text_for_language
    from core.sources_synthetic import generate_fish_seed
    from core.sources_audio import load_audio_file, save_audio_file
    from core.pipeline import forge_pipeline
    from library.storage import (
        PREVIEWS_DIR, BAKED_DIR, clean_old_previews
    )
    from library.presets_manager import (
        get_all_presets_meta, get_recipe_by_id, bake_voice_profile,
        save_custom_recipe, rename_custom_recipe, delete_custom_recipe, is_builtin_preset
    )

    def _log(level: str, msg: str) -> None:
        if logger is not None:
            try:
                getattr(logger, level, logger.info)("VOICE_FORGE", msg)
                return
            except TypeError:
                getattr(logger, level, logger.info)(f"[VOICE_FORGE] {msg}")
                return
        try:
            from hecos.core.logging import logger as _hl
            getattr(_hl, level, _hl.info)("VOICE_FORGE", msg)
        except Exception:
            print(f"[VOICE_FORGE] [{level.upper()}] {msg}")

    def _make_progress_cb(task_ctx):
        last_phase = {"key": None}
        def _cb(phase_key: str, fraction: float, message: str) -> None:
            if phase_key != last_phase["key"]:
                last_phase["key"] = phase_key
                task_ctx.phase(phase_key, message=message)
            task_ctx.advance(
                percent=max(0.0, min(100.0, float(fraction) * 100.0)),
                message=message,
                log=message,
            )
        return _cb

    # Handlers
    def get_languages_api():
        try:
            langs = get_corpus_languages()
            return jsonify({"ok": True, "languages": langs})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    def get_corpus_api():
        try:
            lang = request.args.get("lang", "it")
            samples = get_all_samples_for_language(lang)
            default_text = get_default_text_for_language(lang)
            return jsonify({
                "ok": True,
                "language": lang,
                "default_text": default_text,
                "samples": samples
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    def get_presets_api():
        try:
            presets = get_all_presets_meta()
            return jsonify({"ok": True, "presets": presets})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    def get_recipe_api(recipe_id):
        try:
            prefer_custom = request.args.get("source") == "custom"
            recipe = get_recipe_by_id(recipe_id, prefer_custom=prefer_custom)
            if not recipe:
                return jsonify({"ok": False, "error": f"Recipe '{recipe_id}' not found"}), 404
            return jsonify({"ok": True, "recipe": recipe.model_dump()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    def save_recipe_api():
        try:
            payload = dict(request.get_json(force=True) or {})
            save_as_new = bool(payload.pop("save_as_new", False))
            recipe = VoiceRecipe(**payload)
            saved_recipe, file_path = save_custom_recipe(recipe, save_as_new=save_as_new)
            _log("info", f"[save_recipe_api] Saved custom recipe '{saved_recipe.name}' (id={saved_recipe.id})")
            return jsonify({
                "ok": True,
                "id": saved_recipe.id,
                "recipe": saved_recipe.model_dump(),
                "path": str(file_path)
            })
        except Exception as e:
            _log("error", f"[save_recipe_api] Error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 400

    def rename_recipe_api(recipe_id):
        try:
            payload = request.get_json(force=True) or {}
            new_name = (payload.get("name") or "").strip()
            if not new_name:
                return jsonify({"ok": False, "error": "New preset name is required"}), 400
            updated = rename_custom_recipe(recipe_id, new_name)
            if not updated:
                if is_builtin_preset(recipe_id):
                    return jsonify({"ok": False, "error": "Built-in presets cannot be renamed"}), 400
                return jsonify({"ok": False, "error": f"Custom preset '{recipe_id}' not found"}), 404
            _log("info", f"[rename_recipe_api] Renamed id={recipe_id} -> '{updated.name}'")
            return jsonify({"ok": True, "recipe": updated.model_dump()})
        except Exception as e:
            _log("error", f"[rename_recipe_api] Error renaming '{recipe_id}': {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    def delete_recipe_api(recipe_id):
        try:
            success = delete_custom_recipe(recipe_id)
            if not success:
                msg = "Built-in presets cannot be deleted" if is_builtin_preset(recipe_id) else f"Custom preset '{recipe_id}' not found"
                return jsonify({"ok": False, "error": msg}), 404
            _log("info", f"[delete_recipe_api] Deleted custom recipe id={recipe_id}")
            return jsonify({"ok": True, "id": recipe_id})
        except Exception as e:
            _log("error", f"[delete_recipe_api] Error deleting '{recipe_id}': {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    def generate_seed_api():
        try:
            data = request.get_json(force=True) or {}
            text = data.get("text", "").strip() or get_default_text_for_language("it")
            seed = int(data.get("seed", 42))
            _log("info", f"[generate_seed_api] seed={seed}, text_len={len(text)}")
            audio, fs = generate_fish_seed(text, seed=seed)
            preview_id = f"seed_{uuid.uuid4().hex[:8]}"
            preview_wav = PREVIEWS_DIR / f"{preview_id}.wav"
            save_audio_file(audio, str(preview_wav), fs=fs)
            _log("info", f"[generate_seed_api] Generated preview_id={preview_id} (fs={fs}Hz)")
            return jsonify({
                "ok": True,
                "preview_id": preview_id,
                "audio_url": f"/hecos/api/plugins/voice_forge/preview/{preview_id}/audio"
            })
        except Exception as e:
            _log("error", f"[generate_seed_api] Error: {e}\n{traceback.format_exc()}")
            return jsonify({"ok": False, "error": str(e)}), 500

    def preview_voice_api():
        t0 = time.monotonic()
        try:
            payload = request.get_json(force=True) or {}
            task_id = payload.pop("task_id", None) or f"vf_preview_{uuid.uuid4().hex[:8]}"
            recipe = VoiceRecipe(**payload)
            _log(
                "info",
                f"[preview_voice_api] Start task_id={task_id}, recipe='{recipe.name}' "
                f"(id={recipe.id}, source={recipe.source_type}, lang={recipe.language})"
            )
            clean_old_previews(max_age_seconds=1800)

            phases = [
                ("source", 0.55, "Source Seed Synthesis"),
                ("analyze", 0.15, "WORLD Decomposition"),
                ("sculpt", 0.10, "Vocal Tract Sculpting"),
                ("synth", 0.10, "Resynthesis & Acoustic EQ"),
                ("metrics", 0.10, "Voice DNA & Spectrogram"),
            ]

            with progress.task(
                task_id,
                f"Voice Preview: {recipe.name}",
                source="VOICE_FORGE",
                phases=phases,
                cancellable=False,
            ) as t:
                progress_cb = _make_progress_cb(t)

                # Process full pipeline
                final_audio, fs = forge_pipeline.process(recipe, progress_cb=progress_cb)

                # Save preview audio file
                t.phase("metrics", message="Saving WAV & computing Voice DNA metrics...")
                t.advance(percent=25.0, message="Saving preview WAV...", log="Saving temporary preview audio")
                preview_id = f"prev_{uuid.uuid4().hex[:8]}"
                preview_path = PREVIEWS_DIR / f"{preview_id}.wav"
                save_audio_file(final_audio, str(preview_path), fs=fs)

                # Analyze for UI feedback
                from analysis.acoustic_features import extract_f0_stats, estimate_formants, calculate_spectral_centroid, calculate_hnr
                from analysis.spectro_data import generate_spectrogram_data
                from analysis.voice_dna import compute_voice_dna

                t.advance(percent=60.0, message="Extracting F0, formants & Voice DNA...", log="Running acoustic analysis")
                f0, timeaxis, sp, ap = forge_pipeline.vocoder.analyze(final_audio, fs=fs, use_cache=True)
                f0_stats = extract_f0_stats(f0)
                formants = estimate_formants(sp, fs=fs)
                centroid = calculate_spectral_centroid(final_audio, fs=fs)
                hnr = calculate_hnr(ap)
                dna = compute_voice_dna(f0_stats, formants, centroid, hnr, recipe.model_dump())
                spectro = generate_spectrogram_data(final_audio, fs=fs, f0=f0, sp=sp)
                t.advance(percent=100.0, message="Preview audio & Voice DNA ready", log=f"Preview '{preview_id}' complete")

            elapsed = time.monotonic() - t0
            _log("info", f"[preview_voice_api] Done in {elapsed:.2f}s (preview_id={preview_id}, task_id={task_id})")
            return jsonify({
                "ok": True,
                "task_id": task_id,
                "preview_id": preview_id,
                "audio_url": f"/hecos/api/plugins/voice_forge/preview/{preview_id}/audio",
                "f0_stats": f0_stats,
                "formants": formants,
                "spectral_centroid_hz": centroid,
                "hnr_db": hnr,
                "voice_dna": dna,
                "spectrogram": spectro
            })
        except Exception as e:
            _log("error", f"[preview_voice_api] Error: {e}\n{traceback.format_exc()}")
            return jsonify({"ok": False, "error": str(e)}), 500

    def get_preview_audio_api(preview_id):
        clean_id = os.path.basename(preview_id)
        file_path = PREVIEWS_DIR / f"{clean_id}.wav"
        if not file_path.is_file():
            _log("warning", f"[get_preview_audio_api] Not found: {file_path}")
            return jsonify({"ok": False, "error": "Preview audio not found"}), 404
        return send_file(str(file_path), mimetype="audio/wav")

    def get_baked_audio_api(recipe_id):
        clean_id = os.path.basename(recipe_id)
        file_path = BAKED_DIR / clean_id / "reference.wav"
        if not file_path.is_file():
            _log("warning", f"[get_baked_audio_api] Not found: {file_path}")
            return jsonify({"ok": False, "error": "Baked reference audio not found"}), 404
        return send_file(str(file_path), mimetype="audio/wav")

    def bake_voice_api():
        t0 = time.monotonic()
        try:
            payload = request.get_json(force=True) or {}
            task_id = payload.get("task_id") or f"vf_bake_{uuid.uuid4().hex[:8]}"
            register_yaml = bool(payload.get("register_in_audio_yaml", True))
            recipe_data = dict(payload.get("recipe", payload))
            recipe_data.pop("task_id", None)
            recipe_data.pop("register_in_audio_yaml", None)
            recipe = VoiceRecipe(**recipe_data)
            _log(
                "info",
                f"[bake_voice_api] Start task_id={task_id}, recipe='{recipe.name}' "
                f"(id={recipe.id}, register={register_yaml})"
            )

            phases = [
                ("source", 0.45, "Source Seed Synthesis"),
                ("analyze", 0.10, "WORLD Decomposition"),
                ("sculpt", 0.10, "Vocal Tract Sculpting"),
                ("synth", 0.10, "Resynthesis & Acoustic EQ"),
                ("register", 0.25, "Export & Fish Speech Registration"),
            ]

            with progress.task(
                task_id,
                f"Bake Voice: {recipe.name}",
                source="VOICE_FORGE",
                phases=phases,
                cancellable=False,
            ) as t:
                progress_cb = _make_progress_cb(t)
                meta = bake_voice_profile(
                    recipe,
                    register_to_audio_config=register_yaml,
                    progress_cb=progress_cb,
                )

            elapsed = time.monotonic() - t0
            _log("info", f"[bake_voice_api] Done in {elapsed:.2f}s (id={recipe.id}, task_id={task_id})")
            return jsonify({
                "ok": True,
                "task_id": task_id,
                "meta": meta,
                "audio_url": f"/hecos/api/plugins/voice_forge/baked/{recipe.id}/audio"
            })
        except Exception as e:
            _log("error", f"[bake_voice_api] Error: {e}\n{traceback.format_exc()}")
            return jsonify({"ok": False, "error": str(e)}), 500

    def upload_source_api():
        try:
            if "audio_file" not in request.files:
                return jsonify({"ok": False, "error": "No audio file provided"}), 400
            file = request.files["audio_file"]
            if not file.filename:
                return jsonify({"ok": False, "error": "Empty filename"}), 400

            sources_dir = plugin_path / "data" / "sources"
            sources_dir.mkdir(parents=True, exist_ok=True)
            filename = f"upload_{uuid.uuid4().hex[:8]}_{os.path.basename(file.filename)}"
            dest = sources_dir / filename
            file.save(str(dest))

            audio, sr = load_audio_file(str(dest), target_sr=44100, trim=True)
            save_audio_file(audio, str(dest), fs=sr)

            duration = len(audio) / sr
            _log("info", f"[upload_source_api] Uploaded '{filename}' (duration={duration:.2f}s, sr={sr}Hz)")
            return jsonify({
                "ok": True,
                "file_path": str(dest),
                "filename": filename,
                "duration_seconds": round(duration, 2),
                "sample_rate": sr
            })
        except Exception as e:
            _log("error", f"[upload_source_api] Error: {e}\n{traceback.format_exc()}")
            return jsonify({"ok": False, "error": str(e)}), 500

    # Register endpoints with multiple prefix aliases for maximum reach
    prefixes = ["/hecos/api/plugins/voice_forge", "/api/voice_forge", "/hpm_plugin/voice_forge/api"]
    for i, pfx in enumerate(prefixes):
        tag = f"vf_{i}"
        app.add_url_rule(f"{pfx}/languages", f"{tag}_languages", get_languages_api, methods=["GET"])
        app.add_url_rule(f"{pfx}/corpus", f"{tag}_corpus", get_corpus_api, methods=["GET"])
        app.add_url_rule(f"{pfx}/presets", f"{tag}_presets", get_presets_api, methods=["GET"])
        app.add_url_rule(f"{pfx}/recipe/<recipe_id>", f"{tag}_recipe_get", get_recipe_api, methods=["GET"])
        app.add_url_rule(f"{pfx}/recipe", f"{tag}_recipe_post", save_recipe_api, methods=["POST"])
        app.add_url_rule(f"{pfx}/recipe/<recipe_id>/rename", f"{tag}_recipe_rename", rename_recipe_api, methods=["POST"])
        app.add_url_rule(f"{pfx}/recipe/<recipe_id>", f"{tag}_recipe_delete", delete_recipe_api, methods=["DELETE"])
        app.add_url_rule(f"{pfx}/generate_seed", f"{tag}_gen_seed", generate_seed_api, methods=["POST"])
        app.add_url_rule(f"{pfx}/preview", f"{tag}_preview", preview_voice_api, methods=["POST"])
        app.add_url_rule(f"{pfx}/preview/<preview_id>/audio", f"{tag}_preview_audio", get_preview_audio_api, methods=["GET"])
        app.add_url_rule(f"{pfx}/baked/<recipe_id>/audio", f"{tag}_baked_audio", get_baked_audio_api, methods=["GET"])
        app.add_url_rule(f"{pfx}/bake", f"{tag}_bake", bake_voice_api, methods=["POST"])
        app.add_url_rule(f"{pfx}/upload_source", f"{tag}_upload", upload_source_api, methods=["POST"])

    if logger:
        logger.info("[VoiceForge] REST API endpoints successfully registered under multiple prefixes.")
