"""
Abstract base provider contract and data structures for Hecos Messenger.
Every messaging platform (WhatsApp, Telegram, or future providers) implements
BaseMessengerProvider so the facade, resolver, inbound router, and WebUI remain
completely platform-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class SendResult:
    """Standardized result returned by every provider send operation."""

    ok: bool
    platform: str
    recipient: str
    message: str
    verified: bool = False
    warning: bool = False
    method_used: str = ""

    def format_for_agent(self) -> str:
        """Formats the result with Hecos status prefixes expected by AgentTrace."""
        if not self.ok:
            prefix = "❌"
        elif self.warning:
            prefix = "⚠️"
        else:
            prefix = "✅"

        base = self.message.strip()
        if base.startswith(("✅", "⚠️", "❌")):
            return base
        return f"{prefix} {base}"


@dataclass
class ProviderHealth:
    """Live diagnostic status of a messaging provider."""

    platform: str
    enabled: bool
    state: str  # ONLINE | READY | DEGRADED | OFFLINE | DISABLED | ERROR | MISSING_DEP
    summary: str
    method_used: str = ""
    details: dict[str, Any] = field(default_factory=dict)


InboundCallback = Callable[[str, str, str, Optional[str], bool], None]


class BaseMessengerProvider(ABC):
    """Contract implemented by each isolated platform package under providers/."""

    name: str = ""
    display_name: str = ""
    icon: str = "💬"
    supports_inbound: bool = False
    supports_media: bool = False

    def get_provider_config(self, root_cfg: Any) -> Any:
        """Extracts this provider's sub-config from MessengerConfig."""
        return getattr(root_cfg, self.name, None)

    def is_enabled(self, root_cfg: Any) -> bool:
        pcfg = self.get_provider_config(root_cfg)
        return bool(pcfg and getattr(pcfg, "enabled", False))

    @abstractmethod
    def send_text(
        self,
        provider_cfg: Any,
        recipient: str,
        text: str,
        **options: Any,
    ) -> SendResult:
        """Sends a text message to the resolved recipient."""

    def send_media(
        self,
        provider_cfg: Any,
        recipient: str,
        file_paths: list[str],
        caption: str = "",
        **options: Any,
    ) -> SendResult:
        """Sends one or more local media/document files with an optional caption."""
        return SendResult(
            ok=False,
            platform=self.name,
            recipient=recipient,
            message=f"Media attachments are not supported by provider '{self.display_name}'.",
        )

    @abstractmethod
    def check_health(self, provider_cfg: Any) -> ProviderHealth:
        """Performs a live connectivity/readiness check for this provider."""

    @abstractmethod
    def describe_accounts(self, provider_cfg: Any) -> list[str]:
        """Returns formatted human-readable account lines for list_accounts()."""

    def start_listener(
        self,
        provider_cfg: Any,
        inbound_callback: Optional[InboundCallback] = None,
    ) -> None:
        """Starts background inbound message listeners if supported."""
        return None

    def stop_listener(self) -> None:
        """Stops all active background listeners gracefully."""
        return None
