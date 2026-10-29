"""
search/engines/base.py
Abstract base class for all search engines.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from ..models import SearchQuery, SearchResult


class BaseEngine(ABC):
    """Abstract search engine."""

    def __init__(
        self,
        engine_id: str,
        name: str,
        category: str = "general",
        network: str = "clearnet",
        priority: int = 10
    ):
        self.id = engine_id
        self.name = name
        self.category = category       # general, news, images, videos, audio, files, onion, osint
        self.network = network         # clearnet | tor
        self.priority = priority

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the engine's requirements (network/libraries) are met."""
        pass

    @abstractmethod
    def search(self, query: SearchQuery) -> List[SearchResult]:
        """Executes search and returns a list of SearchResult items."""
        pass

    def get_info(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "network": self.network,
            "priority": self.priority,
            "available": self.is_available()
        }
