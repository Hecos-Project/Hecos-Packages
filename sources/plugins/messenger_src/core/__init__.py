"""
Core abstractions for the modular Hecos Messenger plugin.
"""

from .base_provider import BaseMessengerProvider, ProviderHealth, SendResult
from .defaults import (
    DEFAULT_ANTI_HALLUCINATION_PROMPT,
    DEFAULT_GENERAL_ROUTING_OVERRIDE,
    DEFAULT_TELEGRAM_ROUTING_OVERRIDE,
    DEFAULT_WHATSAPP_ROUTING_OVERRIDE,
    compose_routing_override,
    get_ui_defaults,
)
from .registry import ProviderRegistry, registry
from .session_memory import (
    LastVerifiedSend,
    clear_recent_context,
    get_recent_context,
    record_verified_send,
)

__all__ = [
    "BaseMessengerProvider",
    "ProviderHealth",
    "SendResult",
    "ProviderRegistry",
    "registry",
    "DEFAULT_GENERAL_ROUTING_OVERRIDE",
    "DEFAULT_WHATSAPP_ROUTING_OVERRIDE",
    "DEFAULT_TELEGRAM_ROUTING_OVERRIDE",
    "DEFAULT_ANTI_HALLUCINATION_PROMPT",
    "compose_routing_override",
    "get_ui_defaults",
    "LastVerifiedSend",
    "record_verified_send",
    "get_recent_context",
    "clear_recent_context",
]
