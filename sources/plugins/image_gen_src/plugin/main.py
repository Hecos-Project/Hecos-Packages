"""
Plugin: Image Generation â€” Entry Point
Thin wrapper: registers the tool, delegates all logic to sub-modules.
"""

try:
    from hecos_sdk import logger
except ImportError:
    class _DummyLogger:
        def error(self, *a): print("[IMAGE_GEN ERR]", *a)
        def info(self, *a):  print("[IMAGE_GEN]", *a)
    logger = _DummyLogger()

from .generator import run_generation
from .providers.probe import probe_all_providers
from .local.health import format_status_report, check_backend_status
from .local.models import discover_models, get_model_summary


class ImageGenTools:
    def __init__(self):
        self.tag    = "IMAGE_GEN"
        self.desc   = "Generates images from text descriptions using AI image models."
        self.status = "ONLINE"
        self.slash_commands = [
            {
                "id": "img",
                "aliases": ["/img", "/image", "/photo", "/foto"],
                "description": "Genera un'immagine AI da una descrizione testuale",
                "usage": "/img <descrizione>",
                "example": "/img foto fotorealistica di un gatto su Marte",
                "icon": "ðŸ–¼ï¸",
                "method": "generate_image",
                "args_schema": {"prompt": "str"},
                "requires_args": True,
            }
        ]

    def generate_image(self, prompt: str, provider: str = "", model: str = "", hf_server: str = "", **kwargs) -> str:
        """
        Generates an image from a text description.

        Optional overrides (only for this call, does NOT save to config):
        - provider: e.g. 'huggingface', 'pollinations', 'gemini', 'openai', 'swarmui'
        - model: e.g. 'black-forest-labs/FLUX.1-schnell' (cloud) or 'sd_xl_base_1.0' (local)
        - hf_server: HuggingFace target server e.g. 'fal-ai', 'together', 'replicate', 'hf-inference'

        Use provider='swarmui' for local generation via SwarmUI.

        IMPORTANT: You MUST include the EXACT output of this tool in your final response,
        including the [[IMG:filename.ext]] tag and any metadata text that follows it.
        DO NOT summarize or drop the > **[Image Gen Config]** block if it is present!
        """
        logger.info(f"[IMAGE_GEN] generate_image called. Prompt: {prompt[:60]}... provider_override={provider or 'cfg'} model_override={model or 'cfg'} hf_server_override={hf_server or 'cfg'}")
        return run_generation(prompt, provider_override=provider, model_override=model, hf_server_override=hf_server)

    def probe_providers(self, api_key: str = "") -> str:
        """
        Tests all available image generation providers and HuggingFace servers.
        Returns a formatted report of which configurations are working.
        """
        logger.info("[IMAGE_GEN] probe_providers called")
        try:
            import os
            keys = {
                "huggingface": api_key or os.environ.get("HUGGINGFACE_API_KEY", ""),
                "gemini": os.environ.get("GEMINI_API_KEY", ""),
                "openai": os.environ.get("OPENAI_API_KEY", ""),
                "stability": os.environ.get("STABILITY_API_KEY", "")
            }
            results = probe_all_providers(keys=keys)
            # Format into readable markdown
            lines = ["## 🔍 Diagnostica Provider Image Gen\n"]
            for r in results:
                icon = "✅" if r["ok"] else "❌"
                latency = f" ({r['latency_ms']}ms)" if r.get("latency_ms") else ""
                lines.append(f"{icon} **{r['name']}**{latency}")
                if not r["ok"] and r.get("error"):
                    lines.append(f"   └ {r['error']}")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ Errore nel probe provider: {e}"

    def check_local_status(self) -> str:
        """
        Checks the status of the local image generation backend (SwarmUI).
        Returns a diagnostic report including connectivity, version,
        available models, and supported samplers/schedulers.
        Use when the user asks about local generation status or troubleshooting.
        """
        logger.info("[IMAGE_GEN] check_local_status called")
        try:
            try:
                from igen_config.config_manager import get_image_gen_config
            except ImportError:
                from ..igen_config.config_manager import get_image_gen_config

            cfg = get_image_gen_config()
            local_cfg = cfg.get("local", {})
            url = local_cfg.get("url", "http://localhost:7801")
            enabled = local_cfg.get("enabled", False)

            if not enabled:
                return ("⚠️ Local generation is **disabled** in config.\n"
                        f"URL configured: `{url}`\n"
                        "Enable it in the Image Gen config panel under the Local section.")

            # Try creating a client for detailed info
            try:
                from .local.client import SwarmUIClient
                client = SwarmUIClient(
                    base_url=url,
                    timeout=local_cfg.get("timeout", 120),
                    auth_token=local_cfg.get("auth_token", ""),
                )
            except Exception:
                client = None

            return format_status_report(url, client=client)

        except Exception as e:
            return f"⚠️ Error checking local backend: {e}"

    def list_local_models(self) -> str:
        """
        Lists all models available in the local SwarmUI instance,
        categorized by architecture (Flux, SDXL, SD 1.5, etc.).
        """
        logger.info("[IMAGE_GEN] list_local_models called")
        try:
            try:
                from igen_config.config_manager import get_image_gen_config
            except ImportError:
                from ..igen_config.config_manager import get_image_gen_config

            cfg = get_image_gen_config()
            local_cfg = cfg.get("local", {})
            url = local_cfg.get("url", "http://localhost:7801")

            from .local.client import SwarmUIClient
            client = SwarmUIClient(
                base_url=url,
                timeout=15,
                auth_token=local_cfg.get("auth_token", ""),
            )

            models = discover_models(client, force_refresh=True)
            if not models:
                return "❌ No models found. Is SwarmUI running and loaded?"

            summary = get_model_summary(models)
            return f"## 🧠 Local Models ({len(models)} total)\n\n{summary}"

        except Exception as e:
            return f"⚠️ Error listing local models: {e}"


# â”€â”€ Module exports â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
tools = ImageGenTools()

def info():
    return {"tag": tools.tag, "desc": tools.desc}

def status():
    return tools.status

