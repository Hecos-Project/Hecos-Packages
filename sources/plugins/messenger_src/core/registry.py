"""
Dynamic Provider Registry for Hecos Messenger.
Adding a new platform in the future only requires registering a BaseMessengerProvider
instance here or in providers/__init__.py without modifying core routing logic.
"""

from __future__ import annotations

from typing import Any, Optional
from .base_provider import BaseMessengerProvider


PLATFORM_ALIASES: dict[str, str] = {
    "wa": "whatsapp",
    "wazzap": "whatsapp",
    "whatsapp_web": "whatsapp",
    "whatsapp web": "whatsapp",
    "whatsappweb": "whatsapp",
    "tg": "telegram",
    "telegram_bot": "telegram",
}


class ProviderRegistry:
    """Central registry of installed messaging providers."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseMessengerProvider] = {}

    def normalize_name(self, name: Optional[str]) -> str:
        if not name:
            return ""
        cleaned = str(name).strip().lower()
        return PLATFORM_ALIASES.get(cleaned, cleaned)

    def register(self, provider: BaseMessengerProvider) -> None:
        key = provider.name.strip().lower()
        if not key:
            raise ValueError("Provider must define a non-empty 'name'.")
        self._providers[key] = provider

    def get(self, name: Optional[str]) -> Optional[BaseMessengerProvider]:
        key = self.normalize_name(name)
        return self._providers.get(key)

    def all(self) -> list[BaseMessengerProvider]:
        return list(self._providers.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._providers.keys())

    def enabled_providers(self, root_cfg: Any) -> list[BaseMessengerProvider]:
        return [p for p in self._providers.values() if p.is_enabled(root_cfg)]


registry = ProviderRegistry()
