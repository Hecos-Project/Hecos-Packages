"""
MODULE: Mail Credential Helper
DESCRIPTION: Reads and saves SMTP/IMAP credentials for the Mail plugin (multi-account).
"""

import os
import uuid
from hecos.core.logging import logger

def _get_mail_cfg() -> dict:
    try:
        from .mail_config.config_manager import get_config
        return get_config()
    except Exception as e:
        logger.error(f"[MAIL] Could not read mail config: {e}")
        return {}

def get_account(account_id: str = None) -> dict:
    """Returns the account dict for the given ID, or the active account."""
    cfg = _get_mail_cfg()
    accounts = cfg.get("accounts", [])
    if not accounts:
        return {}
    
    if not account_id:
        account_id = cfg.get("active_account_id")
        
    for acc in accounts:
        if acc.get("id") == account_id:
            return acc
            
    # Fallback to first if not found
    return accounts[0] if accounts else {}

def get_user_email(username: str = "admin", account_id: str = None) -> str:
    env_email = os.environ.get("HECOS_MAIL_ADDRESS", "").strip()
    if env_email and not account_id:
        return env_email
    acc = get_account(account_id)
    return (acc.get("mail_address") or "").strip()

def get_user_app_password(username: str = "admin", account_id: str = None) -> str:
    env_pwd = os.environ.get("HECOS_MAIL_APP_PASSWORD", "").strip()
    if env_pwd and not account_id:
        return env_pwd
    acc = get_account(account_id)
    return (acc.get("mail_app_password") or "").strip()

def get_user_smtp_host_override(username: str = "admin", account_id: str = None) -> str:
    return (get_account(account_id).get("smtp_host") or "").strip()

def get_user_imap_host_override(username: str = "admin", account_id: str = None) -> str:
    return (get_account(account_id).get("imap_host") or "").strip()

def set_mail_credentials(email: str, password: str, account_id: str = None) -> bool:
    try:
        from .mail_config.config_manager import get_config, save_config
        current = get_config()
        
        # If no account_id, modify the active one, or create one if none exist
        if not account_id:
            account_id = current.get("active_account_id")
            
        accounts = current.get("accounts", [])
        
        target = None
        for acc in accounts:
            if acc.get("id") == account_id:
                target = acc
                break
                
        if not target:
            # Create new fallback account
            target = {
                "id": str(uuid.uuid4()),
                "name": email.split("@")[0].capitalize() if email else "My Account",
                "mail_address": "",
                "mail_app_password": "",
                "smtp_host": "", "smtp_port": 587, "smtp_security": "STARTTLS",
                "imap_host": "", "imap_port": 993, "imap_security": "SSL"
            }
            accounts.append(target)
            if not current.get("active_account_id"):
                current["active_account_id"] = target["id"]
                
        updated = False
        if email:
            target["mail_address"] = email.strip()
            updated = True
        if password:
            target["mail_app_password"] = password.strip()
            updated = True
            
        if not updated:
            return False
            
        current["accounts"] = accounts
        ok = save_config(current)
        if ok:
            logger.info(f"[MAIL] Credentials saved to mail.toml")
        return ok
    except Exception as e:
        logger.error(f"[MAIL] set_mail_credentials error: {e}")
        return False

def set_user_app_password(username: str, password: str) -> bool:
    return set_mail_credentials(email="", password=password)

# Provider auto-detection (same as before)
_PROVIDER_MAP = {
    "gmail.com":      {"smtp_host": "smtp.gmail.com",         "smtp_port": 587, "smtp_security": "STARTTLS",
                       "imap_host": "imap.gmail.com",          "imap_port": 993, "imap_security": "SSL"},
    "googlemail.com": {"smtp_host": "smtp.gmail.com",         "smtp_port": 587, "smtp_security": "STARTTLS",
                       "imap_host": "imap.gmail.com",          "imap_port": 993, "imap_security": "SSL"},
    "outlook.com":    {"smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587, "smtp_security": "STARTTLS",
                       "imap_host": "outlook.office365.com",   "imap_port": 993, "imap_security": "SSL"},
    "hotmail.com":    {"smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587, "smtp_security": "STARTTLS",
                       "imap_host": "outlook.office365.com",   "imap_port": 993, "imap_security": "SSL"},
    "live.com":       {"smtp_host": "smtp-mail.outlook.com",  "smtp_port": 587, "smtp_security": "STARTTLS",
                       "imap_host": "outlook.office365.com",   "imap_port": 993, "imap_security": "SSL"},
    "yahoo.com":      {"smtp_host": "smtp.mail.yahoo.com",    "smtp_port": 587, "smtp_security": "STARTTLS",
                       "imap_host": "imap.mail.yahoo.com",     "imap_port": 993, "imap_security": "SSL"},
    "icloud.com":     {"smtp_host": "smtp.mail.me.com",       "smtp_port": 587, "smtp_security": "STARTTLS",
                       "imap_host": "imap.mail.me.com",        "imap_port": 993, "imap_security": "SSL"},
    "libero.it":      {"smtp_host": "smtp.libero.it",         "smtp_port": 465, "smtp_security": "TLS",
                       "imap_host": "imap.libero.it",          "imap_port": 993, "imap_security": "SSL"},
    "virgilio.it":    {"smtp_host": "out.virgilio.it",        "smtp_port": 465, "smtp_security": "TLS",
                       "imap_host": "in.virgilio.it",          "imap_port": 993, "imap_security": "SSL"},
    "tiscali.it":     {"smtp_host": "smtp.tiscali.it",        "smtp_port": 465, "smtp_security": "TLS",
                       "imap_host": "imap.tiscali.it",         "imap_port": 993, "imap_security": "SSL"},
}

def auto_detect_provider(email: str) -> dict | None:
    if not email or "@" not in email:
        return None
    domain = email.split("@")[-1].lower()
    return _PROVIDER_MAP.get(domain)

def resolve_mail_settings(cfg: dict, username: str = "admin", account_id: str = None) -> dict:
    email    = get_user_email(username, account_id)
    password = get_user_app_password(username, account_id)
    acc      = get_account(account_id)

    settings = {}
    if cfg.get("auto_detect_provider", True) and email:
        detected = auto_detect_provider(email)
        if detected:
            settings.update(detected)

    # Merge explicit config overrides from the account object
    for key in ("smtp_host", "smtp_port", "smtp_security", "imap_host", "imap_port", "imap_security"):
        val = acc.get(key)
        if val and str(val).strip():
            settings[key] = val

    settings["username"] = email
    settings["password"] = password
    settings["email"]    = email
    return settings
