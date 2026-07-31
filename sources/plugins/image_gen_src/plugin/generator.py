"""
Plugin: Image Generation â€” Generator
Core generation loop: reads autonomous config, resolves params, builds prompt,
handles key rotation, retry logic, and delegates to the provider engine.
"""

import os

try:
    from hecos_sdk import logger
    from hecos.core.i18n import translator
except ImportError:
    class _L:
        def info(self, *a): print("[GENERATOR]", *a)
        def warning(self, *a): print("[GENERATOR WARN]", *a)
        def error(self, *a): print("[GENERATOR ERR]", *a)
    logger = _L()
    class translator:
        @staticmethod
        def t(k, **kw): return k

try:
    from igen_config.config_manager import get_image_gen_config, save_image_gen_section
except ImportError:
    from ..igen_config.config_manager import get_image_gen_config, save_image_gen_section
from .dimensions import resolve_dimensions
from .prompt_engine import build_prompt
from .providers import generate_image as _engine_generate


_RETRIABLE_SIGNALS = [
    "401", "403", "402", "429", "503", "500", "504",
    "CUDA out of memory", "Model is loading",
    "Rate limit reached", "You have reached your limit",
    "server is overloaded", "upstream request timeout",
    "timed out", "timeout",
]

def _is_retriable(err_msg: str) -> bool:
    import re
    # Check for HTTP status codes surrounded by word boundaries
    if re.search(r'\b(401|402|403|429|500|503|504)\b', err_msg):
        return True
    return any(sig.lower() in err_msg.lower() for sig in _RETRIABLE_SIGNALS[7:])


def _get_api_key(provider: str, pinned_key: str, configured_provider: str = "") -> str:
    """Tries KeyManager -> Hecos .env -> OS env."""

    km_provider = "gemini" if provider == "gemini_native" else provider

    try:
        from hecos.core.keys.key_manager import get_key_manager
        manager = get_key_manager()
        key = manager.get_key(km_provider)
        if key:
            logger.info(f"[GENERATOR] KeyManager returned key for {km_provider}")
            return key
    except ImportError:
        pass

    _ENV_KEY_MAP = {
        "gemini":        "GEMINI_API_KEY",
        "gemini_native": "GEMINI_API_KEY",
        "openai":        "OPENAI_API_KEY",
        "stability":     "STABILITY_API_KEY",
        "huggingface":   "HUGGINGFACE_API_KEY",
        "horde":         "HORDE_API_KEY",
    }
    env_var = _ENV_KEY_MAP.get(provider, "")
    if not env_var:
        return ""

    # Check OS env with _1, _2 support (Hecos loads .env into os.environ on startup)
    v = os.environ.get(env_var, "").strip()
    if v: return v
    for i in range(1, 10):
        v = os.environ.get(f"{env_var}_{i}", "").strip()
        if v: return v

    # Fallback: Read .env directly if running in isolated venv without dotenv
    import pathlib
    plugin_dir = pathlib.Path(__file__).parent.parent.parent
    env_candidates = [
        plugin_dir.parent / ".env",         # C:\Hecos\hecos\.env
        plugin_dir.parent.parent / ".env",  # C:\Hecos\.env (fallback)
    ]
    for env_path in env_candidates:
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("#") or "=" not in line: continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.split("#")[0].strip().strip('"').strip("'")
                    if k == env_var or k.startswith(env_var + "_"):
                        if v:
                            logger.info(f"[GENERATOR] Read key from .env file directly for {provider}")
                            return v
            except Exception as e:
                logger.error(f"[GENERATOR] Failed to read .env: {e}")
            break
    
    return ""


def _mark_exhausted(provider: str, api_key: str, err_msg: str) -> None:
    try:
        from hecos.core.keys.key_manager import get_key_manager
        manager = get_key_manager()
        if "401" in err_msg or "403" in err_msg:
            reason = "invalid"
            cooldown = 86400  # Disable until restart
        elif "402" in err_msg or "429" in err_msg:
            reason = "rate_limited"
            cooldown = 60.0
        else:
            reason = "server_overload"
            cooldown = 3600
        manager.mark_exhausted(provider, api_key, reason=reason, cooldown=cooldown)
    except Exception:
        pass


def run_generation(raw_prompt: str, provider_override: str = "", model_override: str = "", hf_server_override: str = "") -> str:
    try:
        cfg = get_image_gen_config()

        provider    = provider_override.strip().lower() if provider_override else cfg.get("provider", "pollinations")
        provider    = provider.replace("-", "_")
        if provider == "pollination": provider = "pollinations"

        model       = model_override.strip() if model_override else cfg.get("model", "flux")
        hf_provider = hf_server_override.strip() if hf_server_override else cfg.get("hf_provider", "hf-inference")
        aspect_ratio = cfg.get("aspect_ratio", "1:1")
        width       = int(cfg.get("width",  1024))
        height      = int(cfg.get("height", 1024))
        seed        = int(cfg.get("seed", -1))
        
        if seed < 0:
            import random
            seed = random.randint(1, 2147483647)
        
        # Persist the concrete seed used so the UI can offer 'Reuse Last Seed'
        try:
            save_image_gen_section({"last_seed": seed})
        except Exception as _e:
            logger.debug(f"[GENERATOR] Failed to persist last_seed: {_e}")
            
        sampler     = cfg.get("sampler", "euler_a")
        scheduler   = cfg.get("scheduler", "euler")
        pinned_key  = cfg.get("api_key", "").strip()

        neg_enabled = cfg.get("enable_negative_prompt", True)
        neg_prompt  = cfg.get("negative_prompt", "") if neg_enabled else ""
        guidance    = float(cfg.get("guidance_scale", 7.5))
        steps       = int(cfg.get("num_inference_steps", 30))

        optimize_flux       = cfg.get("optimize_for_flux", True)
        flux_instructions   = cfg.get("flux_refiner_instructions",
            "Convert keywords into a descriptive natural language paragraph for Flux.")
        auto_enrich         = cfg.get("auto_enrich", True)
        enrich_keywords     = cfg.get("enrich_keywords", "")
        style               = cfg.get("style", "none")
        show_meta_chat      = cfg.get("show_metadata_in_chat", False)

        # ── Horde-specific config ─────────────────────────────────────────────
        horde_api_key         = cfg.get("horde_api_key", "").strip()
        horde_nsfw            = cfg.get("horde_nsfw", True)
        horde_worker_blacklist = cfg.get("horde_worker_blacklist", "")

        if provider_override or model_override or hf_server_override:
            logger.info(f"[GENERATOR] Override attivo — provider={provider}, model={model}, hf_provider={hf_provider}")

        meta_str = ""
        if show_meta_chat:
            hf_suffix = f", HF Server: `{hf_provider}`" if provider == "huggingface" else ""
            meta_str = f"\n\n> **[Image Gen Config]** Provider: `{provider}`, Model: `{model}`, Seed: `{seed}`, CFG: `{guidance}`, Sampler: `{sampler}`, Steps: `{steps}`{hf_suffix}"

        final_width, final_height = resolve_dimensions(aspect_ratio, width, height)
        logger.info(f"[GENERATOR] Aspect ratio '{aspect_ratio}' â†’ {final_width}Ã—{final_height}")

        final_prompt = build_prompt(
            raw_prompt=raw_prompt, style=style, auto_enrich=auto_enrich,
            enrich_keywords=enrich_keywords, model=model, optimize_for_flux=optimize_flux,
            flux_instructions=flux_instructions,
        )

        max_attempts = 5
        last_error   = None
        current_pinned = pinned_key

        for attempt in range(1, max_attempts + 1):
            # Pass the globally configured provider so pinned_key is only used for that provider
            api_key = _get_api_key(provider, current_pinned, configured_provider=cfg.get("provider", ""))

            if not api_key and provider not in ("pollinations", "airforce", "horde"):
                msg = (f"No API key available for '{provider}'. "
                       "Add at least one valid key in Key Manager or configuration.")
                if last_error:
                    raise last_error
                raise Exception(msg)

            try:
                logger.info(f"[GENERATOR] Attempt {attempt}/{max_attempts} — {provider}/{model} (hf_server={hf_provider})")
                filename = _engine_generate(
                    prompt=final_prompt, provider=provider, model=model,
                    width=final_width, height=final_height, api_key=api_key,
                    negative_prompt=neg_prompt, guidance_scale=guidance,
                    num_inference_steps=steps, seed=seed, sampler=sampler, scheduler=scheduler,
                    hf_provider=hf_provider,
                    horde_nsfw=horde_nsfw,
                    horde_worker_blacklist=horde_worker_blacklist,
                )

                clean_prompt = final_prompt.strip()
                if len(clean_prompt) > 250:
                    clean_prompt = clean_prompt[:247] + "..."
                prefix = f"🎨 Ecco l'immagine generata per: {clean_prompt}"
                return f"{prefix}\n\n[[IMG:{filename}]]{meta_str}"

            except Exception as e:
                last_error = e
                err_msg = str(e)
                if _is_retriable(err_msg):
                    logger.warning(f"[GENERATOR] Retriable error on attempt {attempt}: {err_msg}")
                    _mark_exhausted(provider, api_key, err_msg)
                    current_pinned = ""
                    continue
                raise

        raise last_error or Exception("Max generation attempts reached without success.")

    except Exception as e:
        logger.error(f"[GENERATOR] Generation failed: {e}")
        err_str = str(e)
        if "Artist" not in err_str:
            provider_name = cfg.get("provider", "unknown").capitalize() if "cfg" in dir() else "Unknown"
            err_str = f"Artist [{provider_name}] rejected: {err_str}"
        return f"âš ï¸ Image generation failed. {err_str}. Verify provider config or prompt safety.{meta_str}"

