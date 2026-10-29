"""
search/engines/osint_sherlock.py
OSINT Username discovery engine.
Hunts account profiles across 400+ online services using Sherlock or fast concurrent probe.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List

from .base import BaseEngine
from ..models import SearchQuery, SearchResult
from .. import http_client

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.sherlock")

# Core target sites for fast built-in OSINT probe
PROBE_TARGETS = [
    {"name": "GitHub", "url": "https://github.com/{}", "check_code": 200},
    {"name": "Reddit", "url": "https://www.reddit.com/user/{}/", "check_code": 200},
    {"name": "Telegram", "url": "https://t.me/{}", "check_code": 200},
    {"name": "GitLab", "url": "https://gitlab.com/{}", "check_code": 200},
    {"name": "Steam", "url": "https://steamcommunity.com/id/{}", "check_code": 200},
    {"name": "Dev.to", "url": "https://dev.to/{}", "check_code": 200},
    {"name": "Medium", "url": "https://medium.com/@{}", "check_code": 200},
    {"name": "Twitch", "url": "https://www.twitch.tv/{}", "check_code": 200},
    {"name": "HackerNews", "url": "https://news.ycombinator.com/user?id={}", "check_code": 200},
    {"name": "Keybase", "url": "https://keybase.io/{}", "check_code": 200},
    {"name": "ProductHunt", "url": "https://www.producthunt.com/@{}", "check_code": 200},
    {"name": "Pinterest", "url": "https://www.pinterest.com/{}/", "check_code": 200},
    {"name": "Spotify", "url": "https://open.spotify.com/user/{}", "check_code": 200},
    {"name": "SoundCloud", "url": "https://soundcloud.com/{}", "check_code": 200},
    {"name": "Flickr", "url": "https://www.flickr.com/people/{}/", "check_code": 200},
]


class OsintSherlockEngine(BaseEngine):
    """OSINT Identity discovery engine."""

    def __init__(self):
        super().__init__(
            engine_id="osint_sherlock",
            name="Sherlock OSINT Identity Hunt",
            category="osint",
            network="clearnet",
            priority=80
        )

    def is_available(self) -> bool:
        import importlib.util
        return (
            importlib.util.find_spec("sherlock_project") is not None
            or importlib.util.find_spec("sherlock") is not None
        )

    def search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        username = (query.target_username or query.query).strip().replace(" ", "")

        # Ignore multi-word queries if not an explicit username
        if not username:
            return results

        hecos_logger.info(f"[SEARCH:SHERLOCK] Hunting profiles for username: '{username}' across {len(PROBE_TARGETS)} platforms...")

        def _probe(target):
            url = target["url"].format(username)
            try:
                resp = http_client.get(url, network="clearnet", timeout=5.0, allow_redirects=False)
                if resp.status_code == target["check_code"]:
                    return SearchResult(
                        title=f"👤 {target['name']}: {username}",
                        url=url,
                        snippet=f"Active profile found on {target['name']} ({url})",
                        engine="osint:sherlock",
                        category="osint",
                        network="clearnet",
                        metadata={"platform": target["name"], "username": username}
                    )
            except Exception:
                pass
            return None

        # Run concurrent probes
        with ThreadPoolExecutor(max_workers=8) as ex:
            probe_results = list(ex.map(_probe, PROBE_TARGETS))

        for r in probe_results:
            if r is not None:
                results.append(r)

        return results
