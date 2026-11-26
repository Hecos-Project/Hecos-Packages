"""
Provider registration entry point for Hecos Messenger.
Registers active built-in providers (Telegram and WhatsApp) with the central
ProviderRegistry. Future platforms can be registered here without altering core/.
"""

from __future__ import annotations

from ..core.registry import ProviderRegistry, registry
from .telegram import TelegramProvider
from .whatsapp import WhatsAppProvider


def register_default_providers(target_registry: ProviderRegistry = registry) -> ProviderRegistry:
    if not target_registry.get("telegram"):
        target_registry.register(TelegramProvider())
    if not target_registry.get("whatsapp"):
        target_registry.register(WhatsAppProvider())
    return target_registry


register_default_providers(registry)

__all__ = ["TelegramProvider", "WhatsAppProvider", "register_default_providers"]
