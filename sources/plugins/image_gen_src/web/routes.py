"""
Autonomous routes for image_gen package.
Handles config persistence, models fetching, presets, and HuggingFace API proxy.
Mapped via 'api_routes_file' in hpkg_manifest.toml.
"""
from flask import request, jsonify

def init_plugin_routes(app, cfg_mgr, root_dir, logger, get_sm=None):
    # Absolute imports to avoid parent package errors in dynamic loaders
    import sys
    import os
    plugin_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if plugin_path not in sys.path:
        sys.path.insert(0, plugin_path)
    from igen_config.config_manager import get_config, save_config

    def _get_env_key(name: str) -> str:
        """Read a key from env, supporting both KEY and KEY_1, KEY_2, ... format."""
        # Try plain first
        v = os.environ.get(name, "").strip()
        if v:
            return v
        # Try numbered variants
        for i in range(1, 10):
            v = os.environ.get(f"{name}_{i}", "").strip()
            if v:
                return v
        return ""

    # --- 1. Config Persistence ---

    @app.route("/hecos/api/plugins/image_gen/config", methods=["GET"])
    def get_image_gen_config_api():
        c = get_config()
        routing_file = os.path.join(plugin_path, "routing_override.yaml")
        if os.path.exists(routing_file):
            try:
                import yaml
                with open(routing_file, "r", encoding="utf-8") as f:
                    y_data = yaml.safe_load(f)
                    if y_data and isinstance(y_data, dict):
                        c.setdefault("image_gen", {})["routing_override"] = y_data.get("instruction", "").strip()
            except Exception:
                pass
        return jsonify(c)

    @app.route("/hecos/api/plugins/image_gen/config", methods=["POST"])
    def post_image_gen_config_api():
        try:
            incoming = request.get_json(force=True)
            if not isinstance(incoming, dict):
                return jsonify({"ok": False, "error": "Invalid payload"}), 400

            cfg = get_config()
            igen_incoming = incoming.get("image_gen", {})

            # Key Manager Integration if save_to_env is requested
            save_to_env = igen_incoming.pop("_internal_save_to_env", False)
            if save_to_env:
                try:
                    api_key = igen_incoming.get("api_key", "").strip()
                    provider = igen_incoming.get("provider", "huggingface").strip().lower()
                    comment = igen_incoming.get("api_key_comment", "").strip()
                    if api_key:
                        from hecos.core.keys.key_manager import get_key_manager
                        get_key_manager().add_key(provider, api_key, comment, save_to_env=True)
                except Exception as e:
                    logger.error(f"[ImageGen] Error saving key to .env: {e}")

            # Autonomous Routing Override
            routing_override = igen_incoming.pop("routing_override", None)
            if routing_override is not None:
                routing_file = os.path.join(plugin_path, "routing_override.yaml")
                try:
                    import yaml
                    with open(routing_file, "w", encoding="utf-8") as f:
                        yaml.safe_dump({"enabled": True, "instruction": routing_override}, f)
                except Exception as e:
                    logger.error(f"[ImageGen] Failed to write routing override: {e}")

            # Merge
            existing = cfg.get("image_gen", {})
            existing.update(igen_incoming)
            cfg["image_gen"] = existing

            if save_config(cfg):
                return jsonify({"ok": True})
            return jsonify({"ok": False, "error": "Save failed"}), 500

        except Exception as exc:
            logger.error(f"[ImageGen] POST config error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/hecos/api/plugins/image_gen/key_status", methods=["GET"])
    def get_key_status():
        provider = request.args.get("provider", "").strip().lower()
        if not provider:
            return jsonify({"ok": False, "error": "Provider not specified"})
            
        source = "Not found"
        try:
            from hecos.core.keys.key_manager import get_key_manager
            km = get_key_manager()
            pool_name = "gemini" if provider == "gemini_native" else provider
            pool = km._pools.get(pool_name, [])
            if pool:
                valid_keys = [k for k in pool if k.status != "invalid"]
                if valid_keys:
                    src = valid_keys[0].source
                    if src == "env":
                        source = ".env file"
                    elif src == "db":
                        source = "Key Manager"
                    else:
                        source = src
                else:
                    source = "All keys invalid"
        except ImportError:
            pass
            
        return jsonify({"ok": True, "source": source})

    # --- 2. Dynamic Models Fetching ---

    @app.route("/hecos/api/plugins/image_gen/models", methods=["GET"])
    def get_image_gen_models():
        provider = request.args.get("provider", "pollinations")
        try:
            from plugin.providers import get_models_for_provider
            models = get_models_for_provider(provider)
            
            # Inject user custom models for Hugging Face
            if provider == "huggingface":
                cfg = get_config().get("image_gen", {})
                custom_models = cfg.get("custom_hf_models", [])
                for m in custom_models:
                    if m not in models:
                        models.append(m)

            return jsonify({"ok": True, "provider": provider, "models": models})
        except Exception as exc:
            logger.error(f"[ImageGen] get_models error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    # --- 2b. Horde Account Status ---

    @app.route("/hecos/api/plugins/image_gen/horde/status", methods=["GET"])
    def get_horde_status():
        """Return Horde account info (Kudos balance, username) for the configured key."""
        try:
            from plugin.providers.horde import HordeProvider
            cfg = get_config().get("image_gen", {})
            api_key = cfg.get("horde_api_key", "").strip()
            info = HordeProvider.get_user_info(api_key)
            return jsonify(info)
        except Exception as exc:
            logger.error(f"[ImageGen] Horde status error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/hecos/api/plugins/image_gen/horde/models", methods=["GET"])
    def get_horde_models():
        """Return live list of models currently available on the Horde cluster."""
        try:
            from plugin.providers.horde import HordeProvider
            models = HordeProvider.get_models()
            return jsonify({"ok": True, "models": models, "count": len(models)})
        except Exception as exc:
            logger.error(f"[ImageGen] Horde models error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    # --- 3. Prompt Refiner (Flux) ---

    @app.route("/hecos/api/plugins/image_gen/refine-prompt", methods=["POST"])
    def refine_media_prompt():
        try:
            data = request.json or {}
            prompt = data.get("prompt", "").strip()
            instructions = data.get("instructions", "").strip()
            if not prompt:
                return jsonify({"ok": False, "error": "Prompt is empty"})
                
            from hecos.core.llm import client
            from hecos.app.model_manager import ModelManager
            
            system_prompt = (
                "You are an expert prompt engineer specializing in the Flux image generation model. "
                "Flux prefers detailed, natural language descriptions over comma-separated tags. "
                f"{instructions}"
            )
            user_msg = f"Optimize this prompt for Flux: {prompt}"
            
            main_cfg = cfg_mgr.config
            effective_backend_type, effective_default_model = ModelManager.get_effective_model_info(main_cfg)
            backend_config = main_cfg.get('backend', {}).get(effective_backend_type, {}).copy()
            backend_config['model'] = effective_default_model
            backend_config['backend_type'] = effective_backend_type
            llm_cfg = main_cfg.get('llm', {})
            
            refined = client.generate(system_prompt, user_msg, backend_config, llm_cfg)
            
            if refined and not isinstance(refined, dict) and not refined.startswith("âš ï¸"):
                cleaned = refined.strip().strip('"').strip("'")
                return jsonify({"ok": True, "refined": cleaned})
                
            return jsonify({"ok": False, "error": "LLM returned empty or error"})
        except Exception as exc:
            logger.error(f"[ImageGen] refine_prompt error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    # --- 4. Preset Manager ---

    @app.route("/hecos/api/plugins/image_gen/presets", methods=["GET"])
    def list_presets():
        try:
            from plugin.presets import BUILTIN_PRESETS
            user_presets = get_config().get("image_gen", {}).get("presets", {})
            result = []
            for name, data in BUILTIN_PRESETS.items():
                result.append({"name": name, "builtin": True, "description": data.get("_description", ""), "provider": data.get("provider", ""), "model": data.get("model", "")})
            for name, data in user_presets.items():
                result.append({"name": name, "builtin": False, "description": data.get("_description", "User preset"), "provider": data.get("provider", ""), "model": data.get("model", "")})
            return jsonify({"ok": True, "presets": result})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/hecos/api/plugins/image_gen/presets/load/<path:name>", methods=["GET"])
    def load_preset(name):
        try:
            from plugin.presets import get_preset
            user_presets = get_config().get("image_gen", {}).get("presets", {})
            preset = get_preset(name, user_presets)
            if preset is None:
                return jsonify({"ok": False, "error": f"Preset '{name}' not found"}), 404
            clean = {k: v for k, v in preset.items() if not k.startswith("_")}
            return jsonify({"ok": True, "name": name, "config": clean})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/hecos/api/plugins/image_gen/presets/save", methods=["POST"])
    def save_preset():
        try:
            data = request.json or {}
            name = data.get("name", "").strip()
            config_snapshot = data.get("config", {})
            if not name:
                return jsonify({"ok": False, "error": "Preset name is required"}), 400
            from plugin.presets import save_user_preset
            ok = save_user_preset(name, config_snapshot)
            return jsonify({"ok": ok, "name": name})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/hecos/api/plugins/image_gen/presets/delete/<path:name>", methods=["DELETE"])
    def delete_preset(name):
        try:
            from plugin.presets import delete_user_preset
            ok = delete_user_preset(name)
            if not ok:
                return jsonify({"ok": False, "error": f"Cannot delete '{name}'"}), 400
            return jsonify({"ok": True, "deleted": name})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    # --- 5. Provider Probe / Diagnostica ---

    @app.route("/hecos/api/plugins/image_gen/probe", methods=["GET"])
    def probe_providers():
        """
        Testa tutti i provider e i server HuggingFace in parallelo.
        Chiamato dal bottone 'Testa Provider' nel pannello di configurazione.
        """
        try:
            import os
            from plugin.providers.probe import probe_all_providers
            
            # Fetch all possible keys
            keys = {}
            try:
                from hecos.core.keys.key_manager import get_key_manager
                km = get_key_manager()
                keys["huggingface"] = km.get_key("huggingface") or ""
                keys["gemini"]      = km.get_key("gemini") or ""
                keys["openai"]      = km.get_key("openai") or ""
                keys["stability"]   = km.get_key("stability") or ""
            except Exception:
                pass

            # Fallbacks to plugin config or .env (supports KEY_1, KEY_2 format)
            cfg = get_config().get("image_gen", {})
            if not keys.get("huggingface"):
                keys["huggingface"] = cfg.get("api_key", "").strip() or _get_env_key("HUGGINGFACE_API_KEY")
            if not keys.get("gemini"):
                keys["gemini"] = _get_env_key("GEMINI_API_KEY")
            if not keys.get("openai"):
                keys["openai"] = _get_env_key("OPENAI_API_KEY")
            if not keys.get("stability"):
                keys["stability"] = _get_env_key("STABILITY_API_KEY")

            results = probe_all_providers(keys=keys)
            return jsonify({"ok": True, "results": results})
        except Exception as exc:
            logger.error(f"[ImageGen] probe error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    # --- 6. Hugging Face Hub Explorer ---

    @app.route("/hecos/api/plugins/image_gen/hf-search", methods=["GET"])
    def search_hf_hub():
        try:
            import requests
            query = request.args.get("q", "").strip()
            limit = int(request.args.get("limit", 20))
            
            url = f"https://huggingface.co/api/models?pipeline_tag=text-to-image&sort=downloads&direction=-1&limit={limit}"
            if query:
                import urllib.parse
                url += f"&search={urllib.parse.quote(query)}"
                
            headers = {"User-Agent": "Hecos/0.18.2"}
            from plugin.providers.utils import get_proxies
            prox = get_proxies("huggingface")
            
            r = requests.get(url, headers=headers, timeout=15, proxies=prox)
            if r.status_code != 200:
                return jsonify({"ok": False, "error": f"HF Hub returned HTTP {r.status_code}"}), 502
                
            data = r.json()
            models = []
            for m in data:
                raw_tags = m.get("tags", [])
                if "lora" in [t.lower() for t in raw_tags]:
                    continue

                if "flux" in raw_tags: arch = "Flux"
                elif "stable-diffusion-xl" in raw_tags: arch = "SDXL"
                elif "stable-diffusion" in raw_tags: arch = "SD 1.5"
                else: arch = "Other"

                is_nsfw = "not-for-all-audiences" in raw_tags or "nsfw" in raw_tags

                models.append({
                    "id": m.get("id"),
                    "author": m.get("author", "unknown"),
                    "downloads": m.get("downloads", 0),
                    "likes": m.get("likes", 0),
                    "arch": arch,
                    "inference_status": m.get("inference", "unknown"),
                    "is_nsfw": is_nsfw,
                    "is_gated": str(m.get("gated", "false")).lower() != "false",
                    "tags": raw_tags[:5]
                })
            
            return jsonify({"ok": True, "models": models})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

