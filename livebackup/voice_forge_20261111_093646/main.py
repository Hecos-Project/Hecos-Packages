"""
Voice Forge - HPM Root Entry Point
Exposes VoiceForgeTools to Hecos agent loop and package manager.
"""

from typing import Dict, Any, List

try:
    from hecos.core.logging import logger
except ImportError:
    class _DummyLogger:
        def info(self, *a): print("[VOICE_FORGE]", *a)
        def error(self, *a): print("[VOICE_FORGE ERR]", *a)
        def debug(self, *a): print("[VOICE_FORGE DBG]", *a)
    logger = _DummyLogger()

from .core.pipeline import forge_pipeline, ForgePipeline
from .core.recipe import VoiceRecipe
from .library.presets_manager import bake_voice_profile, get_all_presets_meta, get_recipe_by_id


class VoiceForgeTools:
    """Hecos Voice Forge Plugin — Acoustic Timbre Sculpting & Fish Speech Voice Generator."""

    def __init__(self, config=None):
        self.tag = "VOICE_FORGE"
        self.desc = "Acoustic Vocal Timbre Sculpting & Forging Studio for Fish Speech S2-Pro."
        self.status = "ONLINE"
        self.slash_commands = [
            {
                "id": "voiceforge",
                "aliases": ["/voiceforge", "/forge", "/timbri"],
                "description": "Elenca o forgia timbri vocali originali per Fish Speech",
                "usage": "/voiceforge",
                "example": "/voiceforge",
                "icon": "🎙️",
                "method": "list_presets",
                "args_schema": {},
                "requires_args": False,
            }
        ]

    def list_presets(self) -> str:
        """Returns a formatted list of all available voice presets in Voice Forge catalog."""
        try:
            presets_data = get_all_presets_meta()
            if not presets_data:
                return "Nessun preset vocale trovato in Voice Forge."

            base = presets_data.get("base", [])
            cine = presets_data.get("cinematic", [])
            custom = presets_data.get("custom", [])
            total = len(base) + len(cine) + len(custom)
            if total == 0:
                return "Nessun preset vocale trovato in Voice Forge."

            lines = ["🎙️ **Catalogo Timbri Voice Forge:**"]
            if base:
                lines.append(f"\n**Voci Umane Base ({len(base)}):**")
                for p in base[:8]:
                    lines.append(f"- `{p['id']}`: {p.get('name', p['id'])}")
                if len(base) > 8:
                    lines.append(f"  *...e altri {len(base) - 8} preset base*")

            if cine:
                lines.append(f"\n**Personaggi Cinematografici ({len(cine)}):**")
                for p in cine[:8]:
                    lines.append(f"- `{p['id']}`: {p.get('name', p['id'])} — {p.get('description', '')}")
                if len(cine) > 8:
                    lines.append(f"  *...e altri {len(cine) - 8} preset cinematografici*")

            if custom:
                lines.append(f"\n**Timbri Personalizzati ({len(custom)}):**")
                for p in custom:
                    lines.append(f"- `{p.get('id', p.get('recipe_id'))}`: {p.get('name', '')}")

            lines.append("\n💡 *Usa il pannello Web di Voice Forge per ascoltare, scolpire e registrare nuove voci.*")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error listing presets: {e}")
            return f"Errore durante la lettura dei preset Voice Forge: {e}"

    def bake_preset(self, preset_id: str) -> str:
        """Bakes a preset by ID and registers it immediately into Fish Speech."""
        try:
            res = bake_voice_profile(preset_id)
            if res.get("ok"):
                return f"✅ Timbro vocale `{preset_id}` forgiato e registrato con successo in Fish Speech!"
            return f"❌ Errore durante il bake di `{preset_id}`: {res.get('error', 'Unknown')}"
        except Exception as e:
            logger.error(f"Error baking preset {preset_id}: {e}")
            return f"Errore: {e}"


_tools_instance = VoiceForgeTools()
tools = _tools_instance


def get_plugin():
    return _tools_instance


def info() -> Dict[str, Any]:
    return {
        "id": "voice_forge",
        "name": "Voice Forge",
        "tag": "VOICE_FORGE",
        "version": "1.0.1",
        "type": "app",
        "category": "MULTIMEDIA",
        "description": "Vocal Timbre Sculpting & Forging Studio for Fish Speech S2-Pro.",
        "author": "Antonio Meloni",
        "status": _tools_instance.status,
    }


def status() -> Dict[str, Any]:
    return {"status": _tools_instance.status, "ok": True}
