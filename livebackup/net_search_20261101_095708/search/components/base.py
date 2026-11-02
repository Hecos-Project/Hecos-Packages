"""
search/components/base.py
Abstract base class for all on-demand search components and daemons.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, Optional, Callable

from ..models import ComponentStatus


class BaseComponent(ABC):
    """Represents an installable/startable component for Hecos Deep Search."""

    def __init__(
        self,
        component_id: str,
        name: str,
        description: str,
        category: str = "core",
        auto_start: bool = True
    ):
        self.id = component_id
        self.name = name
        self.description = description
        self.category = category
        self.auto_start = auto_start

    @abstractmethod
    def is_installed(self) -> bool:
        """Returns True if the required libraries or binaries are present."""
        pass

    @abstractmethod
    def is_running(self) -> bool:
        """Returns True if the daemon / service is currently alive."""
        pass

    @abstractmethod
    def install(self, progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None) -> Tuple[bool, str]:
        """Installs the component (downloads binaries or runs pip)."""
        pass

    @abstractmethod
    def uninstall(self) -> Tuple[bool, str]:
        """Removes the component."""
        pass

    def start(self) -> Tuple[bool, str]:
        """Starts the daemon process (if applicable)."""
        return True, "No service process required."

    def stop(self) -> Tuple[bool, str]:
        """Stops the daemon process (if applicable)."""
        return True, "No service process required."

    def get_status(self) -> ComponentStatus:
        """Returns structured status for WebUI and configuration."""
        return ComponentStatus(
            id=self.id,
            name=self.name,
            description=self.description,
            category=self.category,
            is_installed=self.is_installed(),
            is_running=self.is_running(),
            auto_start=self.auto_start,
            details=self.get_details()
        )

    def get_details(self) -> Dict[str, Any]:
        """Optional extra details dict."""
        return {}
