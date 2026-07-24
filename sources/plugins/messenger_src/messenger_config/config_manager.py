"""
MODULE: Messenger Config Manager (Pydantic + TOML)
"""
from pathlib import Path
from pydantic import BaseModel, Field

try:
    from hecos.core.package_manager.config import HPMBaseConfigManager
except ImportError:
    class HPMBaseConfigManager:
        pass


class TelegramBotConfig(BaseModel):
    name: str = ""                # Identificatore (es. "admin", "urania")
    enabled: bool = False
    bot_token: str = ""
    default_chat_id: str = ""
    is_admin: bool = False        # Se true, risponde ai comandi remoti e protegge la chat
    group_mode: str = "mention"   # "mention" | "keyword" | "all"
    group_keywords: str = ""

class TelegramConfig(BaseModel):
    enabled: bool = False
    bots: list[TelegramBotConfig] = Field(default_factory=list)


class WhatsAppConfig(BaseModel):
    enabled: bool = False
    phone_country_code: str = "+39"
    send_as_single_block: bool = True
    use_template: bool = True
    template_id: str = "bbcd5a3b-557d-47db-97b9-7546b5df2cf5"
    cdp_timeout: int = 30
    worker_timeout: int = 60


class DiscordConfig(BaseModel):
    enabled: bool = False
    webhook_url: str = ""
    default_channel: str = ""


class MessengerConfig(BaseModel):
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)


_THIS_DIR = Path(__file__).parent.resolve()

# Save config in the persistent Hecos user-data directory so it survives
# package reinstalls and source-code syncs.
def _resolve_config_file() -> Path:
    # Primary: Hecos standard data dir (works when installed inside Hecos)
    try:
        from hecos.core.config import get_data_dir
        data_dir = Path(get_data_dir()) / "plugins"
    except Exception:
        # Fallback: walk up from this file to find hecos/config/data
        candidate = _THIS_DIR
        found = None
        for _ in range(10):
            probe = candidate / "config" / "data" / "plugins"
            if probe.parent.exists():
                found = probe
                break
            candidate = candidate.parent
        data_dir = found if found else _THIS_DIR

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "messenger.toml"

_CONFIG_FILE = _resolve_config_file()

_manager = None
if hasattr(HPMBaseConfigManager, "get"):
    # We use empty root_key "" here because previously messenger did not have a root key in the TOML file.
    # Wait, HPMBaseConfigManager requires a root key right now to dump properly, 
    # but we can pass "messenger" and adjust `get_config_obj` to just return manager.get()
    # It will automatically migrate or nest it under [messenger].
    _manager = HPMBaseConfigManager(MessengerConfig, _CONFIG_FILE, "messenger")


def get_config() -> dict:
    if _manager:
        return _manager.get().model_dump(mode='json')
    return MessengerConfig().model_dump(mode='json')


def save_config(data: dict) -> bool:
    if _manager:
        try:
            obj = MessengerConfig.model_validate(data)
            return _manager.save(obj)
        except Exception:
            return False
    return False


def get_config_obj() -> MessengerConfig:
    if _manager:
        return _manager.get()
    return MessengerConfig()

