"""
image_gen — SwarmUI Provider
Bridge between the existing provider registry and the local/ subsystem.
Follows the same static interface as all other providers (generate, get_models).
Includes automatic installation detection, auto-startup of SwarmUI if closed,
and real-time user traces/logs.
"""

import os

from ..local.client import SwarmUIClient, SwarmUIError, SwarmUIConnectionError
from ..local.launcher import (
    SwarmUILauncher,
    SwarmUIBackendFailure,
    SwarmUINotInstalledError,
    SwarmUINotRunningError,
    SwarmUIStartupError,
    _emit_trace,
)
from ..local.params import build_swarmui_params, extract_generation_metadata
from ..local.models import discover_models, get_default_model
from .utils import log_debug, save_image_bytes

try:
    from hecos_sdk import logger
except ImportError:
    class _L:
        def info(self, *a): print("[SWARMUI_PROVIDER]", *a)
        def error(self, *a): print("[SWARMUI_PROVIDER ERR]", *a)
        def debug(self, *a): pass
    logger = _L()


def _get_local_config() -> dict:
    """Read the [local] section from image_gen config."""
    try:
        try:
            from igen_config.config_manager import get_image_gen_config
        except ImportError:
            from ...igen_config.config_manager import get_image_gen_config
        cfg = get_image_gen_config()
        return cfg.get("local", {})
    except Exception as e:
        log_debug(f"[SwarmUIProvider] Failed to read local config: {e}")
        return {}


def _get_client(local_cfg: dict = None) -> SwarmUIClient:
    """Create a SwarmUIClient from config."""
    if local_cfg is None:
        local_cfg = _get_local_config()

    url = local_cfg.get("url") or local_cfg.get("host") or "http://localhost:7801"
    timeout = local_cfg.get("timeout", 120)
    auth_token = local_cfg.get("auth_token", "")

    return SwarmUIClient(base_url=url, timeout=timeout, auth_token=auth_token)


# ── Singleton client (reuse sessions) ─────────────────────────────────────
_cached_client: SwarmUIClient | None = None
_cached_url: str = ""


def _get_or_create_client(local_cfg: dict = None) -> SwarmUIClient:
    """Get or create a cached client instance (reuses session)."""
    global _cached_client, _cached_url

    if local_cfg is None:
        local_cfg = _get_local_config()

    url = local_cfg.get("url") or local_cfg.get("host") or "http://localhost:7801"

    # Recreate client if URL changed
    if _cached_client is None or _cached_url != url:
        _cached_client = _get_client(local_cfg)
        _cached_url = url

    return _cached_client


class SwarmUIProvider:
    """
    SwarmUI provider for the image_gen provider registry.
    Implements the same static interface as other providers.
    """
    NAME = "swarmui"
    last_autostart_notice: str = ""

    @staticmethod
    def get_models() -> list:
        """Return list of model names available in SwarmUI."""
        try:
            local_cfg = _get_local_config()
            logger.info(f"[SwarmUIProvider] get_models: Config URL={local_cfg.get('url')}")
            client = _get_or_create_client(local_cfg)
            models = discover_models(client)
            names = [m.get("name", "") for m in models if m.get("name")]
            logger.info(f"[SwarmUIProvider] get_models: Returning {len(names)} models.")
            return names
        except Exception as e:
            logger.error(f"[SwarmUIProvider] get_models failed: {e}")
            return []

    @staticmethod
    def get_vaes() -> list:
        try:
            client = _get_or_create_client()
            models = client.list_models(subtype="VAE")
            return [m.get("name", "") for m in models if m.get("name")]
        except Exception as e:
            logger.error(f"[SwarmUIProvider] get_vaes failed: {e}")
            return []

    @staticmethod
    def get_loras() -> list:
        try:
            client = _get_or_create_client()
            models = client.list_models(subtype="LoRA")
            return [m.get("name", "") for m in models if m.get("name")]
        except Exception as e:
            logger.error(f"[SwarmUIProvider] get_loras failed: {e}")
            return []

    @staticmethod
    def get_models_info() -> list:
        try:
            local_cfg = _get_local_config()
            client = _get_or_create_client(local_cfg)
            models = discover_models(client)
            return [{
                "name":         m.get("name", ""),
                "compat_class": m.get("compat_class", ""),
                "architecture": m.get("architecture", ""),
                "class":        m.get("class", ""),
                "loaded":       m.get("loaded", False),
            } for m in models if m.get("name")]
        except Exception as e:
            return []

    @staticmethod
    def get_loras_info() -> list:
        try:
            client = _get_or_create_client()
            models = client.list_models(subtype="LoRA")
            result = []
            for m in models:
                if not m.get("name"): continue
                result.append({
                    "name":                m.get("name", ""),
                    "title":               m.get("title", m.get("name", "")),
                    "compat_class":        m.get("compat_class", ""),
                    "architecture":        m.get("architecture", ""),
                    "class":               m.get("class", ""),
                    "trigger_phrase":      m.get("trigger_phrase", ""),
                    "lora_default_weight": m.get("lora_default_weight", ""),
                })
            return result
        except Exception as e:
            return []

    @staticmethod
    def generate(prompt: str, width: int, height: int, model: str,
                 api_key: str = "", negative_prompt: str = "",
                 guidance_scale: float = 7.5, num_inference_steps: int = 30,
                 seed: int = -1, sampler: str = "euler", scheduler: str = "normal",
                 **kwargs) -> str:
        """
        Generate an image via SwarmUI.
        Automatically checks if SwarmUI is installed & running, and launches it
        if needed, emitting live user traces at each step.

        Returns:
            Filename of the saved image.
        """
        SwarmUIProvider.last_autostart_notice = ""
        local_cfg = dict(_get_local_config() or {})
        if isinstance(kwargs.get("local"), dict):
            local_cfg.update(kwargs["local"])
        model = str(model or "")

        # ── 1. Ensure SwarmUI is installed and running (auto-launch if closed) ──
        launcher = SwarmUILauncher.get_instance()
        ok, status_code, status_msg = launcher.ensure_running(local_cfg)
        if not ok:
            if status_code == "NOT_INSTALLED":
                raise SwarmUINotInstalledError(status_msg, status_code=status_code, user_notice=status_msg)
            elif status_code in ("OFFLINE_CLOSED", "REMOTE_OFFLINE", "AUTH_REQUIRED"):
                raise SwarmUINotRunningError(status_msg, status_code=status_code, user_notice=status_msg)
            else:
                raise SwarmUIStartupError(status_msg, status_code=status_code, user_notice=status_msg)

        if status_code == "STARTED":
            SwarmUIProvider.last_autostart_notice = status_msg

        client = _get_or_create_client(local_cfg)
        if status_code == "STARTED":
            # Fresh instance started — clear any stale session id
            client._invalidate_session()

        # ── 2. Resolve model name ─────────────────────────────────────────
        try:
            available_models = discover_models(client, force_refresh=(status_code == "STARTED"))
        except Exception as e:
            available_models = []
            log_debug(f"[SwarmUIProvider] Model discovery warning: {e}")

        if not model or model.lower() in ("auto", "default", ""):
            model = get_default_model(available_models) if available_models else ""
            if not model:
                err_txt = (
                    "❌ **No models found in SwarmUI.**\n"
                    f"- SwarmUI is active on `{client.base_url}`, but no models were found in `Models/Stable-Diffusion` or `Models/diffusion_models`.\n"
                    "- Add at least one `.safetensors` model in SwarmUI and try again."
                )
                _emit_trace("No models found in SwarmUI.", level="error")
                raise SwarmUIBackendFailure(err_txt, status_code="NO_MODELS", user_notice=err_txt)
            log_debug(f"[SwarmUIProvider] Auto-selected model: {model}")
        elif available_models:
            # Verify configured model exists in SwarmUI; if not, fallback to available default with trace
            model_names = [m.get("name", "") for m in available_models if m.get("name")]
            if model_names and model not in model_names:
                matched = next((m for m in model_names if model.lower() in m.lower()), None)
                if matched:
                    model = matched
                else:
                    fallback_model = get_default_model(available_models) or model_names[0]
                    _emit_trace(
                        f"⚠️ Model '{model}' not found in SwarmUI. Using available model: '{fallback_model}'.",
                        level="warning",
                    )
                    model = fallback_model

        # ── 3. Build SwarmUI params ───────────────────────────────────────
        params = build_swarmui_params(
            prompt=prompt,
            model=model,
            width=width,
            height=height,
            steps=num_inference_steps,
            cfg=guidance_scale,
            seed=seed,
            sampler=sampler,
            scheduler=scheduler,
            negative_prompt=negative_prompt,
            images=1,
            vae=kwargs.get("vae", ""),
            loras=kwargs.get("loras", []),
        )

        _emit_trace(
            f"🎨 Generating with SwarmUI: model='{model}', {width}x{height}, steps={num_inference_steps}, cfg={guidance_scale}...",
            level="tool",
        )
        log_debug(f"[SwarmUIProvider] Generating with params: "
                  f"model={model}, steps={num_inference_steps}, "
                  f"cfg={guidance_scale}, size={width}x{height}")

        # ── 4. Generate ───────────────────────────────────────────────────
        try:
            logger.info(f"[SwarmUIProvider] Sending generate request to {client.base_url}")
            image_paths, response_data = client.generate(params)
        except SwarmUIConnectionError as e:
            err_txt = (
                f"❌ **Connection to SwarmUI lost during generation** (`{client.base_url}`).\n"
                f"- **Details:** `{e}`\n"
                "- **Resolution:** Check that SwarmUI was not closed or crashed due to insufficient GPU memory (VRAM)."
            )
            _emit_trace(f"Connection to SwarmUI lost during generation: {e}", level="error")
            raise SwarmUIBackendFailure(err_txt, status_code="CONNECTION_LOST", user_notice=err_txt)
        except Exception as e:
            logger.error(f"[SwarmUIProvider] SwarmUI generation failed: {e}")
            err_txt = (
                f"❌ **SwarmUI generation error:** `{e}`\n"
                f"- **Model:** `{model}`\n"
                f"- **Server:** `{client.base_url}`\n"
                "- **Resolution:** Check the SwarmUI console (or the selected model/LoRA in the Image Gen panel)."
            )
            _emit_trace(f"SwarmUI generation error: {e}", level="error")
            raise SwarmUIBackendFailure(err_txt, status_code="GENERATION_ERROR", user_notice=err_txt)

        # ── 5. Download the first image ───────────────────────────────────
        image_path = image_paths[0]
        try:
            image_bytes = client.download_image(image_path)
        except SwarmUIError as e:
            err_txt = f"❌ **Image download from SwarmUI failed:** `{e}`"
            _emit_trace(err_txt, level="error")
            raise SwarmUIBackendFailure(err_txt, status_code="DOWNLOAD_ERROR", user_notice=err_txt)

        # ── 6. Determine file extension & save ────────────────────────────
        ext = "png"
        if image_path.lower().endswith(".jpg") or image_path.lower().endswith(".jpeg"):
            ext = "jpg"
        elif image_path.lower().endswith(".webp"):
            ext = "webp"

        log_debug(f"[SwarmUIProvider] Image downloaded: {len(image_bytes)} bytes ({ext})")

        metadata = extract_generation_metadata(params, backend="swarmui")
        saved_file = save_image_bytes(
            image_bytes, ext, prompt=prompt,
            params=metadata,
        )
        _emit_trace(f"✅ SwarmUI image generated and saved: {saved_file}", level="success")
        return saved_file
