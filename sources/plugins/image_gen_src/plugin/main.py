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
        - provider: e.g. 'huggingface', 'pollinations', 'gemini', 'openai'
        - model: e.g. 'black-forest-labs/FLUX.1-schnell'
        - hf_server: HuggingFace target server e.g. 'fal-ai', 'together', 'replicate', 'hf-inference'

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


# â”€â”€ Module exports â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
tools = ImageGenTools()

def info():
    return {"tag": tools.tag, "desc": tools.desc}

def status():
    return tools.status

