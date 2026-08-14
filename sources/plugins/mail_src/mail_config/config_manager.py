"""
Mail Package — Config Manager (Pydantic + TOML)
Reads/writes the package's own mail.toml using HPMBaseConfigManager.
All state is local to this package. No central hecos yaml files are touched.
"""
import uuid
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

try:
    from hecos.core.logging import logger
    from hecos.core.package_manager.config import HPMBaseConfigManager
except ImportError:
    class _L:
        def info(self, *a):    print("[MAIL CONFIG]", *a)
        def error(self, *a):   print("[MAIL CONFIG ERR]", *a)
        def warning(self, *a): print("[MAIL CONFIG WARN]", *a)
    logger = _L()
    class HPMBaseConfigManager:
        pass


class MailAccount(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "My Account"
    mail_address: str = ""
    mail_app_password: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "STARTTLS"
    imap_host: str = ""
    imap_port: int = 993
    imap_security: str = "SSL"


class MailConfig(BaseModel):
    model_config = ConfigDict(extra='allow')
    accounts: list[MailAccount] = []
    active_account_id: str = ""
    
    # Legacy fields (kept for migration)
    mail_address: str = ""
    mail_app_password: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "STARTTLS"
    imap_host: str = ""
    imap_port: int = 993
    imap_security: str = "SSL"
    
    max_messages: int = 100
    sync_on_open: bool = True
    auto_detect_provider: bool = True


_THIS_DIR    = Path(__file__).parent.resolve()
_CONFIG_FILE = _THIS_DIR / "mail.toml"

_manager = None
if hasattr(HPMBaseConfigManager, "get"):
    _manager = HPMBaseConfigManager(MailConfig, _CONFIG_FILE, "mail")


def get_config() -> dict:
    """Returns the full mail config dict. Migrates legacy single-account to multi-account if needed."""
    cfg = MailConfig()
    if _manager:
        cfg = _manager.get()
        
    # Migration: if we have legacy credentials but no accounts, migrate them
    if not cfg.accounts and cfg.mail_address:
        new_account = MailAccount(
            name=cfg.mail_address.split("@")[0].capitalize(),
            mail_address=cfg.mail_address,
            mail_app_password=cfg.mail_app_password,
            smtp_host=cfg.smtp_host,
            smtp_port=cfg.smtp_port,
            smtp_security=cfg.smtp_security,
            imap_host=cfg.imap_host,
            imap_port=cfg.imap_port,
            imap_security=cfg.imap_security
        )
        cfg.accounts.append(new_account)
        cfg.active_account_id = new_account.id
        
        # Clear legacy credentials so we don't migrate again
        cfg.mail_address = ""
        cfg.mail_app_password = ""
        if _manager:
            _manager.save(cfg)
            
    # Default active account if none set
    if not cfg.active_account_id and cfg.accounts:
        cfg.active_account_id = cfg.accounts[0].id
        if _manager:
            _manager.save(cfg)
            
    return cfg.model_dump(mode='json')


def save_config(new_config: dict) -> bool:
    if not _manager:
        return False
    try:
        obj = MailConfig.model_validate(new_config)
        return _manager.save(obj)
    except Exception as e:
        logger.error(f"[MAIL] Config save error: {e}")
        return False

