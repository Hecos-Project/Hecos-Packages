"""
Messenger Config Manager (Pydantic v2 + TOML).
Composes per-provider schemas, follow-up session memory settings, 3-tier transparent
routing overrides (synchronized to `routing_override.yaml`), and configurable
anti-hallucination guard settings.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

try:
    from hecos.core.package_manager.config import HPMBaseConfigManager
except ImportError:
    class HPMBaseConfigManager:  # type: ignore[no-redef]
        pass

from ..core.defaults import (
    DEFAULT_ANTI_HALLUCINATION_PROMPT,
    DEFAULT_GENERAL_ROUTING_OVERRIDE,
    compose_routing_override,
)
from ..providers.telegram.config import TelegramBotConfig, TelegramConfig, TelegramGroupConfig
from ..providers.whatsapp.config import WhatsAppConfig

__all__ = [
    "TelegramBotConfig",
    "TelegramGroupConfig",
    "TelegramConfig",
    "WhatsAppConfig",
    "MessengerConfig",
    "get_config",
    "save_config",
    "get_config_obj",
    "sync_routing_override_yaml",
]


class MessengerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    remember_last_channel: bool = True
    last_channel_ttl_minutes: int = 15
    general_override_enabled: bool = True
    general_override: str = DEFAULT_GENERAL_ROUTING_OVERRIDE
    anti_hallucination_guard_enabled: bool = True
    anti_hallucination_prompt: str = DEFAULT_ANTI_HALLUCINATION_PROMPT

    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)


_THIS_DIR = Path(__file__).parent.resolve()
_PLUGIN_ROOT = _THIS_DIR.parent.resolve()
_ROUTING_OVERRIDE_FILE = _PLUGIN_ROOT / "routing_override.yaml"


def _resolve_config_file() -> Path:
    try:
        from hecos.core.constants import CONFIG_DATA_DIR
        data_dir = Path(CONFIG_DATA_DIR) / "plugins"
    except Exception:
        try:
            from hecos.core.config import get_data_dir
            data_dir = Path(get_data_dir()) / "plugins"
        except Exception:
            candidate = _THIS_DIR
            found = None
            for _ in range(15):
                probe = candidate / "config" / "data" / "plugins"
                if probe.parent.exists() and candidate.name == "hecos":
                    found = probe
                    break
                candidate = candidate.parent
            data_dir = found if found else (_THIS_DIR / "config" / "data" / "plugins")

    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / "messenger.toml"

    try:
        wrong_dir = _THIS_DIR.parent.parent.parent / "config" / "data" / "plugins"
        wrong_file = wrong_dir / "messenger.toml"
        if wrong_file.exists() and not target.exists() and wrong_dir != data_dir:
            shutil.copy2(str(wrong_file), str(target))
    except Exception:
        pass

    return target


_CONFIG_FILE = _resolve_config_file()

_manager = None
if hasattr(HPMBaseConfigManager, "get"):
    _manager = HPMBaseConfigManager(MessengerConfig, _CONFIG_FILE, "messenger")


def sync_routing_override_yaml(cfg: Optional[MessengerConfig] = None) -> bool:
    """
    Writes `hecos/hpm/messenger/routing_override.yaml` so `RoutingManager`
    dynamically injects the user's active General + Platform overrides into LLM routing rules.
    """
    if yaml is None:
        return False
    try:
        active_cfg = cfg if cfg is not None else get_config_obj()
        enabled, instruction = compose_routing_override(active_cfg)
        payload = {
            "enabled": bool(enabled and instruction),
            "instruction": instruction,
        }
        with open(_ROUTING_OVERRIDE_FILE, "w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)
        return True
    except Exception:
        return False


def get_config() -> dict:
    if _manager:
        return _manager.get().model_dump(mode="json")
    return MessengerConfig().model_dump(mode="json")


def save_config(data: dict) -> bool:
    if _manager:
        try:
            obj = MessengerConfig.model_validate(data)
            ok = _manager.save(obj)
            if ok:
                sync_routing_override_yaml(obj)
            return ok
        except Exception:
            return False
    return False


def get_config_obj() -> MessengerConfig:
    if _manager:
        return _manager.get()
    return MessengerConfig()
