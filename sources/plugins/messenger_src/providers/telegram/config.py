"""
Configuration schema for the Telegram provider (v2.3).
Includes multi-bot configuration, Persona-aware bot matching, and dedicated
Groups & Channels directory with phonetic/STT aliases.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...core.defaults import DEFAULT_TELEGRAM_ROUTING_OVERRIDE


class TelegramBotConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    enabled: bool = False
    bot_token: str = ""
    default_chat_id: str = ""
    is_admin: bool = False
    is_primary: bool = False
    group_mode: str = "mention"  # "mention" | "keyword" | "all"
    group_keywords: str = ""


class TelegramGroupConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    enabled: bool = True
    chat_id: str = ""          # e.g. '@hecos_project' or '-1003708995593'
    aliases: str = ""          # comma-separated voice/STT aliases, e.g. 'ecos, ekos, hecos project'
    preferred_bot: str = ""    # optional bot override; empty = auto-match active Persona/Primary


class TelegramConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    auto_match_persona_bot: bool = True
    bots: list[TelegramBotConfig] = Field(default_factory=list)
    groups: list[TelegramGroupConfig] = Field(default_factory=list)
    routing_override_enabled: bool = True
    routing_override: str = DEFAULT_TELEGRAM_ROUTING_OVERRIDE
