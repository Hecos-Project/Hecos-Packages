"""
search/engines/osint_sherlock.py
OSINT Username & Identity Discovery Engine.
Uses Sherlock's real 480+ site catalog (`sherlock_project/resources/data.json`) with
proper `errorType` (`status_code`, `message`, `response_url`), `regexCheck`,
`safe_search` (`isNSFW`), and multi-variant handle resolution for person queries.
Falls back cleanly to built-in curated sites if `sherlock_project` is absent.
"""
from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseEngine
from .osint_apis import classify_osint_group, parse_osint_input
from .. import http_client
from ..config import get_search_config
from ..models import SearchQuery, SearchResult

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.sherlock")

# High-signal priority platforms probed first (matching Sherlock names where possible)
PRIORITY_PLATFORM_NAMES = [
    "GitHub", "GitLab", "Reddit", "Telegram", "Instagram", "TikTok",
    "YouTube", "Medium", "Dev.to", "Substack", "Patreon", "Linktree",
    "Pinterest", "Flickr", "Twitch", "Steam", "Spotify", "SoundCloud",
    "Keybase", "HackerNews", "ProductHunt", "Bluesky", "Mastodon",
    "CodePen", "Dribbble", "Behance", "Kaggle", "HuggingFace", "PyPI",
    "Docker Hub", "About.me", "Roblox", "Bandcamp", "Vimeo", "Gravatar",
    "Bitbucket", "Replit", "Strava", "Letterboxd", "Goodreads",
]

# Built-in fallback targets when sherlock_project resources are unavailable
PROBE_TARGETS: List[Dict[str, Any]] = [
    {"name": "GitHub", "url": "https://github.com/{}", "errorType": "status_code", "group": "dev"},
    {"name": "GitLab", "url": "https://gitlab.com/{}", "errorType": "status_code", "group": "dev"},
    {"name": "Reddit", "url": "https://www.reddit.com/user/{}/", "errorType": "message", "errorMsg": "Sorry, nobody on Reddit", "group": "social"},
    {"name": "Telegram", "url": "https://t.me/{}", "errorType": "message", "errorMsg": "tgme_page_extra", "group": "social"},
    {"name": "Dev.to", "url": "https://dev.to/{}", "errorType": "status_code", "group": "dev"},
    {"name": "Medium", "url": "https://medium.com/@{}", "errorType": "status_code", "group": "media"},
    {"name": "Twitch", "url": "https://www.twitch.tv/{}", "errorType": "status_code", "group": "media"},
    {"name": "Steam", "url": "https://steamcommunity.com/id/{}", "errorType": "message", "errorMsg": "The specified profile could not be found", "group": "media"},
    {"name": "HackerNews", "url": "https://news.ycombinator.com/user?id={}", "errorType": "message", "errorMsg": "No such user.", "group": "dev"},
    {"name": "Keybase", "url": "https://keybase.io/{}", "errorType": "status_code", "group": "dev"},
    {"name": "ProductHunt", "url": "https://www.producthunt.com/@{}", "errorType": "status_code", "group": "social"},
    {"name": "Pinterest", "url": "https://www.pinterest.com/{}/", "errorType": "status_code", "group": "social"},
    {"name": "Spotify", "url": "https://open.spotify.com/user/{}", "errorType": "status_code", "group": "media"},
    {"name": "SoundCloud", "url": "https://soundcloud.com/{}", "errorType": "status_code", "group": "media"},
    {"name": "Flickr", "url": "https://www.flickr.com/people/{}/", "errorType": "status_code", "group": "media"},
    {"name": "About.me", "url": "https://about.me/{}", "errorType": "status_code", "group": "social"},
    {"name": "Linktree", "url": "https://linktr.ee/{}", "errorType": "status_code", "group": "social"},
    {"name": "Patreon", "url": "https://www.patreon.com/{}", "errorType": "status_code", "group": "media"},
    {"name": "Substack", "url": "https://{}.substack.com", "errorType": "status_code", "group": "media"},
    {"name": "Vimeo", "url": "https://vimeo.com/{}", "errorType": "status_code", "group": "media"},
    {"name": "CodePen", "url": "https://codepen.io/{}", "errorType": "status_code", "group": "dev"},
    {"name": "Docker Hub", "url": "https://hub.docker.com/u/{}", "errorType": "status_code", "group": "dev"},
    {"name": "PyPI", "url": "https://pypi.org/user/{}/", "errorType": "status_code", "group": "dev"},
    {"name": "HuggingFace", "url": "https://huggingface.co/{}", "errorType": "status_code", "group": "dev"},
    {"name": "Kaggle", "url": "https://www.kaggle.com/{}", "errorType": "status_code", "group": "dev"},
]

_SHERLOCK_CACHE: Optional[List[Dict[str, Any]]] = None


def _load_sherlock_catalog() -> List[Dict[str, Any]]:
    """Load and prioritize Sherlock data.json sites (cached once)."""
    global _SHERLOCK_CACHE
    if _SHERLOCK_CACHE is not None:
        return _SHERLOCK_CACHE

    catalog: List[Dict[str, Any]] = []
    try:
        import sherlock_project
        data_path = os.path.join(os.path.dirname(sherlock_project.__file__), "resources", "data.json")
        with open(data_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)

        priority_rank = {name.lower(): idx for idx, name in enumerate(PRIORITY_PLATFORM_NAMES)}
        for name, info in raw.items():
            if name == "$schema" or not isinstance(info, dict):
                continue
            url_tpl = info.get("url") or ""
            if "{}" not in url_tpl:
                continue
            entry = {
                "name": name,
                "url": url_tpl,
                "urlProbe": info.get("urlProbe") or url_tpl,
                "errorType": info.get("errorType") or "status_code",
                "errorMsg": info.get("errorMsg"),
                "errorUrl": info.get("errorUrl"),
                "regexCheck": info.get("regexCheck"),
                "headers": info.get("headers") or {},
                "isNSFW": bool(info.get("isNSFW", False)),
                "group": classify_osint_group(url_tpl, platform=name, title=name),
                "_rank": priority_rank.get(name.lower(), 10000),
            }
            catalog.append(entry)

        catalog.sort(key=lambda x: (x["_rank"], x["name"].lower()))
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:SHERLOCK] Falling back to built-in probe catalog: {exc}")
        catalog = [dict(t, urlProbe=t["url"]) for t in PROBE_TARGETS]

    _SHERLOCK_CACHE = catalog
    return catalog


def _check_probe_exists(resp, target: Dict[str, Any]) -> bool:
    """Validate response against Sherlock site error semantics."""
    err_type = target.get("errorType", "status_code")
    if err_type == "status_code":
        return 200 <= resp.status_code < 300

    if err_type == "message":
        if not (200 <= resp.status_code < 400):
            return False
        err_msg = target.get("errorMsg")
        body = resp.text or ""
        if isinstance(err_msg, list):
            return not any(str(m) in body for m in err_msg if m)
        if err_msg:
            return str(err_msg) not in body
        return resp.status_code == 200

    if err_type == "response_url":
        if not (200 <= resp.status_code < 300):
            return False
        err_url = (target.get("errorUrl") or "").rstrip("/")
        final_url = str(getattr(resp, "url", "") or "").rstrip("/")
        if err_url and err_url in final_url:
            return False
        return True

    return resp.status_code == 200


class OsintSherlockEngine(BaseEngine):
    """OSINT Identity & Username discovery engine backed by Sherlock's platform catalog."""

    def __init__(self):
        super().__init__(
            engine_id="osint_sherlock",
            name="Sherlock OSINT Identity Hunt",
            category="osint",
            network="clearnet",
            priority=88,
        )

    def is_available(self) -> bool:
        return True

    def search(self, query: SearchQuery) -> List[SearchResult]:
        cfg = get_search_config()
        is_local_only = (
            bool(query.local_only)
            if getattr(query, "local_only", None) is not None
            else bool(cfg.get("local_only", True))
        )
        if is_local_only:
            hecos_logger.info("[SEARCH:SHERLOCK] Privacy Shield local_only active — skipping direct external probes.")
            return []

        raw_q = (query.target_username or query.query or "").strip()
        if not raw_q:
            return []

        osint_cfg = cfg.get("osint", {}) or {}
        use_db = osint_cfg.get("use_sherlock_db", True) is not False
        gen_variants = osint_cfg.get("generate_name_variants", True) is not False
        parsed = parse_osint_input(raw_q)

        variants = parsed.get("variants") or []
        if not variants:
            return []
        if not gen_variants and len(variants) > 1:
            variants = variants[:1]

        is_unlimited = query.limit is not None and query.limit <= 0
        cfg_max_sites = int(osint_cfg.get("sherlock_max_sites", 80) or 80)
        max_sites = min(160, max(cfg_max_sites, 100)) if is_unlimited else min(max(cfg_max_sites, 30), 120)

        catalog = _load_sherlock_catalog() if use_db else [dict(t, urlProbe=t["url"]) for t in PROBE_TARGETS]
        filtered_sites: List[Dict[str, Any]] = []
        for entry in catalog:
            if query.safe_search and entry.get("isNSFW"):
                continue
            filtered_sites.append(entry)
            if len(filtered_sites) >= max_sites:
                break

        # Build bounded (target, username_variant) pairs: primary variant across all selected sites,
        # plus optional second variant (e.g., lisa.ellis) across top 25 priority platforms for person names.
        probe_pairs: List[Tuple[Dict[str, Any], str]] = [(site, variants[0]) for site in filtered_sites]
        if parsed["kind"] == "person" and len(variants) > 1:
            for site in filtered_sites[:25]:
                probe_pairs.append((site, variants[1]))

        hecos_logger.info(
            f"[SEARCH:SHERLOCK] Probing {len(probe_pairs)} platform-handle targets for '{raw_q}' "
            f"(variants={variants[:2]}, catalog={'sherlock_project' if use_db else 'builtin'})"
        )

        def _probe(pair: Tuple[Dict[str, Any], str]) -> Optional[SearchResult]:
            target, uname = pair
            regex = target.get("regexCheck")
            if regex:
                try:
                    if not re.search(regex, uname):
                        return None
                except re.error:
                    pass

            profile_url = target["url"].format(uname)
            probe_url = (target.get("urlProbe") or target["url"]).format(uname)
            req_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                **(target.get("headers") or {}),
            }
            allow_redir = target.get("errorType") in ("message", "response_url")
            try:
                resp = http_client.get(
                    probe_url,
                    network="clearnet",
                    headers=req_headers,
                    timeout=min(float(query.timeout or 15.0), 4.5),
                    allow_redirects=allow_redir,
                )
                if _check_probe_exists(resp, target):
                    return SearchResult(
                        title=f"👤 {target['name']}: {uname}",
                        url=profile_url,
                        snippet=f"Active profile candidate on {target['name']} ({profile_url})",
                        engine="osint:sherlock",
                        category="osint",
                        network="clearnet",
                        score=1.25,
                        metadata={
                            "platform": target["name"],
                            "username": uname,
                            "osint_group": target.get("group") or classify_osint_group(profile_url, target["name"]),
                        },
                    )
            except Exception:
                pass
            return None

        results: List[SearchResult] = []
        seen_urls = set()
        with ThreadPoolExecutor(max_workers=16) as ex:
            futures = [ex.submit(_probe, pair) for pair in probe_pairs]
            try:
                for fut in as_completed(futures, timeout=max(float(query.timeout or 12.0), 9.0)):
                    try:
                        res = fut.result()
                        if res is not None and res.url not in seen_urls:
                            seen_urls.add(res.url)
                            results.append(res)
                    except Exception:
                        pass
            except Exception:
                pass

        return results
