"""
web/routes.py
Autonomous routes for document_reader package.
Handles config persistence for the web UI and registers the plugin's API endpoints.
"""
from flask import request, jsonify, send_from_directory, Blueprint
import os
import json

def init_plugin_routes(app, cfg_mgr, root_dir, logger, get_sm=None):
    plugin_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_file = os.path.join(plugin_path, "docreader_config.json")

    def get_config():
        default_cfg = {
            "enabled": True,
            "voice_source": "hecos",        # 'hecos' | 'browser'
            "hecos_preset": "current",      # 'current' | specific soul_id
            "default_voice": "",
            "default_rate": 1.0,
            "default_pitch": 1.0,
            "default_volume": 1.0,
            "highlight_color": "#a78bfa",
            "word_highlight": True,
            "auto_open": False,
            "font_size": 1.1
        }
        if os.path.exists(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_cfg.update(data)
                    return default_cfg
            except Exception as e:
                logger.error(f"[DocReader] Error reading config: {e}")
        return default_cfg

    def save_config(data):
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"[DocReader] Error writing config: {e}")
            return False

    # ── Config API ────────────────────────────────────────────────────────────
    @app.route("/hecos/api/plugins/document_reader/config", methods=["GET"])
    @app.route("/api/document_reader/config", methods=["GET"])
    def get_docreader_config_api():
        return jsonify(get_config())

    @app.route("/hecos/api/plugins/document_reader/config", methods=["POST"])
    @app.route("/api/document_reader/config", methods=["POST"])
    def post_docreader_config_api():
        try:
            incoming = request.get_json(force=True)
            if not isinstance(incoming, dict):
                return jsonify({"ok": False, "error": "Invalid payload"}), 400
            
            current_config = get_config()
            current_config.update(incoming)
            
            if save_config(current_config):
                return jsonify({"ok": True, "config": current_config})
            return jsonify({"ok": False, "error": "Save failed"}), 500
        except Exception as exc:
            logger.error(f"[DocReader] POST config error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    # ── Hecos Presets List API ────────────────────────────────────────────────
    @app.route("/hecos/api/plugins/document_reader/presets", methods=["GET"])
    @app.route("/api/document_reader/presets", methods=["GET"])
    def get_docreader_presets_api():
        try:
            from hecos.core.global_presets import list_souls, get_active_soul_id, get_soul
            active_id = get_active_soul_id("global") or "urania_9800_gp"
            active_name = "Current Active Voice"
            if active_id:
                s = get_soul(active_id)
                if s and s.meta and s.meta.name:
                    active_name = s.meta.name

            souls = list_souls()
            items = []
            for s in souls:
                engine = (s.voice.tts_engine if s.voice and s.voice.tts_engine else "local").upper()
                voice = s.voice.tts_voice if s.voice and s.voice.tts_voice else ""
                items.append({
                    "id": s.meta.id,
                    "name": s.meta.name,
                    "engine": engine,
                    "voice": voice
                })
            items.sort(key=lambda x: x["name"].lower())

            return jsonify({
                "ok": True,
                "active_preset_id": active_id,
                "active_preset_name": active_name,
                "presets": items
            })
        except Exception as exc:
            logger.error(f"[DocReader] GET presets error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    # ── Hecos Neural TTS Synthesis API ─────────────────────────────────────────
    @app.route("/hecos/api/plugins/document_reader/tts", methods=["POST"])
    @app.route("/api/document_reader/tts", methods=["POST"])
    def post_docreader_tts_api():
        try:
            data = request.get_json(force=True) or {}
            text = (data.get("text") or "").strip()
            if not text:
                return jsonify({"ok": False, "error": "Empty text"}), 400

            preset_id = (data.get("preset_id") or "current").strip()
            speed = float(data.get("speed") or data.get("rate") or 1.0)

            from hecos.core.audio.device_manager import get_audio_config
            from hecos.core.global_presets import get_soul, get_active_soul_id
            from hecos.modules.web_ui.routes_chat_tts import generate_voice_file

            voice_cfg = get_audio_config()
            session_overrides = {}

            target_soul = None
            if preset_id == "current":
                active_id = get_active_soul_id("global")
                if active_id:
                    target_soul = get_soul(active_id)
            else:
                target_soul = get_soul(preset_id)

            if target_soul and target_soul.voice:
                session_overrides = target_soul.voice.model_dump(exclude_unset=True)
            else:
                ai_cfg = cfg_mgr.config.get("ai", {}) if (cfg_mgr and hasattr(cfg_mgr, "config")) else {}
                session_overrides = {
                    "tts_engine": ai_cfg.get("tts_engine"),
                    "tts_voice": ai_cfg.get("tts_voice")
                }
                voice_overrides = ai_cfg.get("voice_overrides", {})
                session_overrides.update(voice_overrides)

            # Speed override if non-default
            if speed and speed != 1.0:
                engine = (session_overrides.get("tts_engine") or voice_cfg.get("active_engine", "")).lower()
                if "kokoro" in engine:
                    session_overrides["kokoro_speed"] = speed
                elif "xtts" in engine:
                    session_overrides["xtts_speed"] = speed

            voice_cfg["session_overrides"] = session_overrides

            path, audio_id = generate_voice_file(text, voice_cfg)
            if not audio_id:
                return jsonify({"ok": False, "error": "TTS synthesis returned no audio"}), 500

            return jsonify({
                "ok": True,
                "audio_id": audio_id,
                "audio_url": f"/api/audio?id={audio_id}"
            })
        except Exception as exc:
            logger.error(f"[DocReader] TTS error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    # ── Static File Server for plugin ─────────────────────────────────────────
    @app.route("/hecos/api/plugins/document_reader/static/<path:filename>")
    def get_docreader_static(filename):
        static_folder = os.path.join(plugin_path, "web", "static")
        return send_from_directory(static_folder, filename)

    # ── Chat Auto-Injection (Fallback for zero-core setups) ────────────────────
    _CHAT_MARKER = b'HECOS_ROOM_CHAT_V2_ACTIVE'
    _INJECT_SCRIPTS = (
        '\n<!-- Hecos Document Reader Plugin -->'
        '\n<link rel="stylesheet" href="/static/css/document_reader.css?t=20261024_v2">'
        '\n<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>'
        '\n<script src="/static/js/document_reader.js?t=20261024_v2"></script>'
        '\n<script src="/static/js/document_reader_chat.js?t=20261024_v2"></script>'
        '\n<script>'
        '\n  window.openDocReader = function(path) {'
        '\n    if (window.DocReader && typeof window.DocReader.open === "function") {'
        '\n      window.DocReader.open(path);'
        '\n    }'
        '\n  };'
        '\n</script>'
        '\n<!-- /Document Reader -->'
    ).encode('utf-8')

    @app.after_request
    def _docreader_inject_hook(response):
        try:
            cfg = get_config()
            if not cfg.get("enabled", True):
                return response
            ct = response.content_type or ''
            if 'text/html' not in ct:
                return response
            data = response.get_data()
            if _CHAT_MARKER in data and b'document_reader.js' not in data:
                close_body = b'</body>'
                if close_body in data:
                    data = data.replace(close_body, _INJECT_SCRIPTS + b'\n' + close_body, 1)
                    response.set_data(data)
                    if response.content_length:
                        response.content_length = len(data)
        except Exception as e:
            logger.debug(f"[DocReader] Injection skipped: {e}")
        return response

    logger.info("[DocReader] Autonomous routes and hooks registered successfully.")

register_routes = init_plugin_routes
