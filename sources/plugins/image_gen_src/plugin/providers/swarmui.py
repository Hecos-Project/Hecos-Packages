"""
image_gen — SwarmUI Provider
Bridge between the existing provider registry and the local/ subsystem.
Follows the same static interface as all other providers (generate, get_models).
"""

import os

from ..local.client import SwarmUIClient, SwarmUIError
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

    url = local_cfg.get("url", "http://localhost:7801")
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

    url = local_cfg.get("url", "http://localhost:7801")

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

        Follows the same signature as all other providers.
        The api_key parameter is ignored (local generation doesn't need it).

        Returns:
            Filename of the saved image.
        """
        local_cfg = _get_local_config()
        client = _get_or_create_client(local_cfg)

        # ── Resolve model name ────────────────────────────────────────────
        if not model or model.lower() in ("auto", "default", ""):
            # Auto-discover and pick default
            try:
                models = discover_models(client)
                model = get_default_model(models)
                if not model:
                    raise Exception("No models found in SwarmUI")
                log_debug(f"[SwarmUIProvider] Auto-selected model: {model}")
            except Exception as e:
                raise Exception(f"SwarmUI model auto-selection failed: {e}")

        # ── Build SwarmUI params ──────────────────────────────────────────
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

        log_debug(f"[SwarmUIProvider] Generating with params: "
                  f"model={model}, steps={num_inference_steps}, "
                  f"cfg={guidance_scale}, size={width}x{height}")

        # ── Generate ──────────────────────────────────────────────────────
        try:
            logger.info(f"[SwarmUIProvider] Sending generate request to {client.base_url}")
            image_paths, response_data = client.generate(params)
        except Exception as e:
            logger.error(f"[SwarmUIProvider] SwarmUI generation failed: {e}")
            raise Exception(f"SwarmUI generation failed: {e}")

        # ── Download the first image ──────────────────────────────────────
        image_path = image_paths[0]
        try:
            image_bytes = client.download_image(image_path)
        except SwarmUIError as e:
            raise Exception(f"SwarmUI image download failed: {e}")

        # ── Determine file extension ──────────────────────────────────────
        ext = "png"
        if image_path.lower().endswith(".jpg") or image_path.lower().endswith(".jpeg"):
            ext = "jpg"
        elif image_path.lower().endswith(".webp"):
            ext = "webp"

        log_debug(f"[SwarmUIProvider] Image downloaded: {len(image_bytes)} bytes ({ext})")

        # ── Save using the standard utility ───────────────────────────────
        metadata = extract_generation_metadata(params, backend="swarmui")
        return save_image_bytes(
            image_bytes, ext, prompt=prompt,
            params=metadata,
        )
