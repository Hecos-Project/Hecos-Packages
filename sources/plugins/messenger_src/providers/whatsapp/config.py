"""
Configuration schema for the WhatsApp Web provider (v2.4.3).
Supports:
  - Explicit delivery modes ('cdp' shared browser vs 'persistent_profile' isolated session)
  - Global & per-group toggleable `[Signature]` prefix with 'auto' (active Soul) or 'custom' text (e.g. 'Pippo')
  - Dedicated WhatsApp Groups directory with voice aliases and per-group authorized inbound listening modes.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from ...core.defaults import DEFAULT_WHATSAPP_ROUTING_OVERRIDE


class WhatsAppGroupConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    enabled: bool = True
    group_title: str = ""
    aliases: str = ""
    # 'global' inherits WhatsAppConfig.group_signature_enabled / mode / text;
    # 'off' disables signature for this group; 'auto' uses active Soul; 'custom' uses custom_signature.
    signature_mode: Literal["global", "off", "auto", "custom"] = "global"
    custom_signature: str = ""
    sign_persona: bool = True  # Legacy compatibility field
    inbound_mode: Literal["off", "mention", "keyword", "all"] = "mention"
    inbound_keywords: str = "urania, hecos, haicos"
    default_persona: str = ""


class WhatsAppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    session_mode: Literal["cdp", "persistent_profile"] = "cdp"
    cdp_port: int = 9222
    auto_open_tab: bool = True
    persistent_headless: bool = False
    phone_country_code: str = "+39"
    send_as_single_block: bool = True
    use_template: bool = False
    template_id: str = ""
    group_signature_enabled: bool = True
    group_signature_mode: Literal["auto", "custom"] = "auto"
    group_signature_text: str = ""
    cdp_timeout: int = 30
    worker_timeout: int = 60
    inbound_poll_seconds: int = 8
    groups: list[WhatsAppGroupConfig] = Field(default_factory=list)
    routing_override_enabled: bool = True
    routing_override: str = DEFAULT_WHATSAPP_ROUTING_OVERRIDE
