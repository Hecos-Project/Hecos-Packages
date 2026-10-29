"""
search/models.py
Data models for Hecos Deep Search & Intelligence.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class SearchResult:
    """Individual search result item."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    url: str = ""
    snippet: str = ""
    engine: str = "generic"            # e.g. "ddgs:brave", "ahmia", "torch", "yt-dlp"
    engine_id: str = ""                # Canonical engine identifier, e.g. "clear_ddgs", "clear_news"
    category: str = "general"          # general, news, images, videos, audio, files, onion, osint
    network: str = "clearnet"          # clearnet | tor
    score: float = 1.0
    media_url: Optional[str] = None    # Direct link for playable video/audio/highres img
    thumbnail_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SearchResult:
        valid_fields = {f for f in cls.__annotations__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class SearchQuery:
    """Search request specification."""
    query: str
    mode: str = "clear"                # clear, dark, deep, media, files, osint
    engines: List[str] = field(default_factory=list)      # Empty = all enabled for mode
    categories: List[str] = field(default_factory=lambda: ["general"])
    limit: int = 50
    timeout: float = 15.0
    safe_search: bool = False          # Default unmoderated
    dark_bypass: bool = True           # Bypass Ahmia/Tor blacklists and moral censorship
    time_range: Optional[str] = None   # d (day), w (week), m (month), y (year)
    file_types: List[str] = field(default_factory=list)   # e.g. ["pdf", "epub"]
    auto_fallback_tor: bool = True     # If clearweb yields zero, fallback to Tor
    target_username: Optional[str] = None  # for OSINT mode

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchSession:
    """A search execution session with all aggregated results."""
    id: str = field(default_factory=lambda: "hs_" + uuid.uuid4().hex[:10])
    query: str = ""
    mode: str = "clear"
    engines_queried: List[str] = field(default_factory=list)
    total_results: int = 0
    duration_ms: int = 0
    results: List[SearchResult] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["results"] = [r.to_dict() if isinstance(r, SearchResult) else r for r in self.results]
        return d


@dataclass
class ComponentStatus:
    """Status information of an on-demand engine / daemon."""
    id: str
    name: str
    description: str
    category: str                      # core, tor, scraper, osint
    is_installed: bool
    is_running: bool
    can_autostart: bool = True
    auto_start: bool = True
    port: Optional[int] = None
    version: Optional[str] = None
    download_size: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
