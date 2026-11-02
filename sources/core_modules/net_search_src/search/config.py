"""
search/config.py
Configuration manager for Hecos Deep Search.
Integrates with Hecos ConfigManager while offering safe standalone defaults,
and re-exports endpoints and Tor browser utilities for unified access.
"""
from __future__ import annotations

import os
import json
import logging
from typing import Dict, Any, Optional, Tuple, List

# Sub-module imports
try:
    from hecos.modules.net_search.search.tor_browser import (
        detect_tor_browser_path,
        get_tor_browser_path,
        launch_tor_browser
    )
    from hecos.modules.net_search.search.endpoints_config import (
        DEFAULT_SEARXNG_FALLBACKS,
        build_endpoint_url,
        decompose_endpoint_url,
        get_endpoints,
        update_endpoints,
        get_engine_auth_headers,
        reset_endpoints_to_defaults
    )
except (ImportError, ValueError):
    from .tor_browser import (
        detect_tor_browser_path,
        get_tor_browser_path,
        launch_tor_browser
    )
    from .endpoints_config import (
        DEFAULT_SEARXNG_FALLBACKS,
        build_endpoint_url,
        decompose_endpoint_url,
        get_endpoints,
        update_endpoints,
        get_engine_auth_headers,
        reset_endpoints_to_defaults
    )

logger = logging.getLogger("browser.search.config")

_DEFAULT_SEARCH_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "local_only": False,               # Privacy Shield: Deactivates third-party public cloud engines/scrapers
    "default_mode": "clear",
    "default_limit": 250,
    "safe_search": False,
    "auto_fallback_tor": True,
    "tor": {
        "enabled": False,              # Default off until user turns on or starts daemon
        "socks_port": 9055,            # Custom port to never clash with Tor Browser (9050/9150)
        "control_port": 9056,
        "use_system_tor_if_available": True,
        "auto_start": True,
        "custom_proxy_url": "",
        "onion_action": "hecos_viewer",  # "hecos_viewer" | "tor_browser" | "ask_menu"
        "tor_browser_path": ""
    },
    "searxng": {
        "enabled": True,
        "url": "http://127.0.0.1:8888",
        "port": 8888,
        "auto_start": True,
        "custom_engines": ""
    },
    "engines": {
        "clear_ddgs": True,
        "clear_news": True,
        "clear_searxng": True,
        "dark_ahmia": True,
        "dark_torch": True,
        "dark_haystak": True,
        "dark_onionland": True,
        "dark_excavator": True,
        "dark_phobos": True,
        "dark_tor66": True,
        "dark_danieltore": True,
        "dark_custom": True,
        "media_images": True,
        "media_videos": True,
        "media_audio": True,
        "files_dorks": True,
        "osint_sherlock": True
    },
    "endpoints": {
        "searxng": {
            "local_url": "http://127.0.0.1:8888",
            "fallbacks": [
                "https://searx.be",
                "https://baresearch.org",
                "https://priv.au",
                "https://searx.tiekoetter.com",
                "https://paulgo.io"
            ],
            "engines": [
                {"id": "bing", "name": "bing", "label": "Bing Web Search", "category": "general", "enabled": True},
                {"id": "yandex", "name": "yandex", "label": "Yandex Web Search", "category": "general", "enabled": True},
                {"id": "yahoo", "name": "yahoo", "label": "Yahoo Web Search", "category": "general", "enabled": True},
                {"id": "duckduckgo", "name": "duckduckgo", "label": "DuckDuckGo", "category": "general", "enabled": True},
                {"id": "google", "name": "google", "label": "Google Web Search", "category": "general", "enabled": True},
                {"id": "brave", "name": "brave", "label": "Brave Web Search", "category": "general", "enabled": True},
                {"id": "qwant", "name": "qwant", "label": "Qwant Web Search", "category": "general", "enabled": True},
                {"id": "startpage", "name": "startpage", "label": "Startpage", "category": "general", "enabled": True},
                {"id": "wikipedia", "name": "wikipedia", "label": "Wikipedia", "category": "general", "enabled": True},
                {"id": "wikidata", "name": "wikidata", "label": "Wikidata", "category": "general", "enabled": True},
                {"id": "mojeek", "name": "mojeek", "label": "Mojeek (Independent Index)", "category": "general", "enabled": False},
                {"id": "yep", "name": "yep", "label": "Yep Search", "category": "general", "enabled": False},
                {"id": "google_news", "name": "google news", "label": "Google News", "category": "news", "enabled": True},
                {"id": "bing_news", "name": "bing news", "label": "Bing News", "category": "news", "enabled": True},
                {"id": "yahoo_news", "name": "yahoo news", "label": "Yahoo News", "category": "news", "enabled": True},
                {"id": "brave_news", "name": "brave news", "label": "Brave News", "category": "news", "enabled": True},
                {"id": "duckduckgo_news", "name": "duckduckgo news", "label": "DuckDuckGo News", "category": "news", "enabled": True},
                {"id": "reuters", "name": "reuters", "label": "Reuters", "category": "news", "enabled": True},
                {"id": "wikinews", "name": "wikinews", "label": "Wikinews", "category": "news", "enabled": True},
                {"id": "yandex_images", "name": "yandex images", "label": "Yandex Images (Uncensored)", "category": "images", "enabled": True},
                {"id": "bing_images", "name": "bing images", "label": "Bing Images", "category": "images", "enabled": True},
                {"id": "google_images", "name": "google images", "label": "Google Images", "category": "images", "enabled": True},
                {"id": "brave_images", "name": "brave images", "label": "Brave Images", "category": "images", "enabled": True},
                {"id": "qwant_images", "name": "qwant images", "label": "Qwant Images", "category": "images", "enabled": True},
                {"id": "flickr", "name": "flickr", "label": "Flickr", "category": "images", "enabled": True},
                {"id": "deviantart", "name": "deviantart", "label": "DeviantArt", "category": "images", "enabled": True},
                {"id": "unsplash", "name": "unsplash", "label": "Unsplash", "category": "images", "enabled": True},
                {"id": "openverse", "name": "openverse", "label": "Openverse (CC-Licensed)", "category": "images", "enabled": True},
                {"id": "wikicommons", "name": "wikicommons", "label": "Wikimedia Commons", "category": "images", "enabled": True},
                {"id": "pinterest", "name": "pinterest", "label": "Pinterest", "category": "images", "enabled": True},
                {"id": "wallhaven", "name": "wallhaven", "label": "Wallhaven (Wallpapers & Art)", "category": "images", "enabled": True},
                {"id": "pixabay_images", "name": "pixabay images", "label": "Pixabay Images", "category": "images", "enabled": False},
                {"id": "imgur", "name": "imgur", "label": "Imgur", "category": "images", "enabled": False},
                {"id": "google_videos", "name": "google_videos", "label": "Google Videos", "category": "videos", "enabled": True},
                {"id": "bing_videos", "name": "bing_videos", "label": "Bing Videos", "category": "videos", "enabled": True},
                {"id": "brave_videos", "name": "brave videos", "label": "Brave Videos", "category": "videos", "enabled": True},
                {"id": "qwant_videos", "name": "qwant videos", "label": "Qwant Videos", "category": "videos", "enabled": True},
                {"id": "dailymotion", "name": "dailymotion", "label": "Dailymotion", "category": "videos", "enabled": True},
                {"id": "peertube", "name": "peertube", "label": "PeerTube", "category": "videos", "enabled": True},
                {"id": "vimeo", "name": "vimeo", "label": "Vimeo", "category": "videos", "enabled": True},
                {"id": "rumble", "name": "rumble", "label": "Rumble", "category": "videos", "enabled": True},
                {"id": "piped", "name": "piped", "label": "Piped (YouTube Frontend)", "category": "videos", "enabled": True},
                {"id": "odysee", "name": "odysee", "label": "Odysee / LBRY", "category": "videos", "enabled": True},
                {"id": "bitchute", "name": "bitchute", "label": "BitChute (Uncensored)", "category": "videos", "enabled": True},
                {"id": "bilibili", "name": "bilibili", "label": "Bilibili", "category": "videos", "enabled": False},
                {"id": "sepiasearch", "name": "sepiasearch", "label": "SepiaSearch (PeerTube Index)", "category": "videos", "enabled": True},
                {"id": "soundcloud", "name": "soundcloud", "label": "SoundCloud", "category": "music", "enabled": True},
                {"id": "mixcloud", "name": "mixcloud", "label": "Mixcloud", "category": "music", "enabled": True},
                {"id": "bandcamp", "name": "bandcamp", "label": "Bandcamp", "category": "music", "enabled": True},
                {"id": "deezer", "name": "deezer", "label": "Deezer", "category": "music", "enabled": True},
                {"id": "genius", "name": "genius", "label": "Genius (Lyrics)", "category": "music", "enabled": True},
                {"id": "radio_browser", "name": "radio browser", "label": "Radio Browser", "category": "music", "enabled": True},
                {"id": "piped_music", "name": "piped.music", "label": "Piped Music (YouTube Music)", "category": "music", "enabled": True},
                {"id": "arxiv", "name": "arxiv", "label": "arXiv (Preprints)", "category": "science", "enabled": True},
                {"id": "google_scholar", "name": "google scholar", "label": "Google Scholar", "category": "science", "enabled": True},
                {"id": "pubmed", "name": "pubmed", "label": "PubMed (Biomedical)", "category": "science", "enabled": True},
                {"id": "semantic_scholar", "name": "semantic scholar", "label": "Semantic Scholar", "category": "science", "enabled": False},
                {"id": "github", "name": "github", "label": "GitHub", "category": "it", "enabled": True},
                {"id": "stackoverflow", "name": "stackoverflow", "label": "Stack Overflow", "category": "it", "enabled": True},
                {"id": "pypi", "name": "pypi", "label": "PyPI (Python Packages)", "category": "it", "enabled": True},
                {"id": "docker_hub", "name": "docker hub", "label": "Docker Hub", "category": "it", "enabled": True},
                {"id": "hackernews", "name": "hackernews", "label": "Hacker News", "category": "it", "enabled": True},
                {"id": "npm", "name": "npm", "label": "npm (Node.js Packages)", "category": "it", "enabled": False},
                {"id": "reddit", "name": "reddit", "label": "Reddit", "category": "social media", "enabled": True},
                {"id": "mastodon_users", "name": "mastodon users", "label": "Mastodon Users", "category": "social media", "enabled": True},
                {"id": "lemmy_posts", "name": "lemmy posts", "label": "Lemmy Posts", "category": "social media", "enabled": True},
                {"id": "kickass", "name": "kickass", "label": "KickassTorrents", "category": "files", "enabled": True},
                {"id": "piratebay", "name": "piratebay", "label": "The Pirate Bay", "category": "files", "enabled": True},
                {"id": "solidtorrents", "name": "solidtorrents", "label": "Solid Torrents", "category": "files", "enabled": True},
                {"id": "bt4g", "name": "bt4g", "label": "BT4G Torrent Search", "category": "files", "enabled": True},
                {"id": "annas_archive", "name": "annas archive", "label": "Anna's Archive (Books)", "category": "files", "enabled": True},
                {"id": "zlibrary", "name": "z-library", "label": "Z-Library (Books & Papers)", "category": "files", "enabled": True},
                {"id": "imdb", "name": "imdb", "label": "IMDB (Movies & TV)", "category": "other", "enabled": True},
                {"id": "openstreetmap", "name": "openstreetmap", "label": "OpenStreetMap", "category": "map", "enabled": True},
                {"id": "currency", "name": "currency", "label": "Currency Converter", "category": "general", "enabled": True},
                {"id": "wttr", "name": "wttr.in", "label": "Weather (wttr.in)", "category": "other", "enabled": True}
            ]
        },
        "dark_ahmia": {
            "onion_url": "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion",
            "clearnet_url": "https://ahmia.fi"
        },
        "dark_torch": {
            "ddg_onion": "https://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion/html/",
            "torch_onion": "http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion/cgi-bin/omega/omega"
        },
        "dark_haystak": {
            "onion_url": "http://haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion"
        },
        "dark_onionland": {
            "clearnet_url": "https://onionsearchengine.com/search.php",
            "onion_url": "http://37djtvjcpiprohcrlyvlhfil45kdlfizsyvilqskgvdrafn5mocz4cid.onion/search.php"
        },
        "dark_excavator": {
            "onion_url": "http://2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion/search"
        },
        "dark_phobos": {
            "onion_url": "http://phobosxilamwcg75xt22id7aywkzol6q6rfl2flipcqoc4e4ahima5id.onion/search"
        },
        "dark_tor66": {
            "onion_url": "http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search"
        },
        "dark_danieltore": {
            "onion_url": "http://tordexu73joywapk2txdr54jed4imqledpcvcuf75qsas2gwdgksvnyd.onion/search"
        },
        "archives": {
            "archive_org": "https://archive.org/advancedsearch.php",
            "wikimedia_commons": "https://commons.wikimedia.org/w/api.php"
        },
        "media_streams": {
            "eporner": {
                "id": "eporner",
                "name": "Eporner Stream API",
                "url": "https://www.eporner.com/api/v2/video/search/",
                "enabled": True,
                "category": "videos",
                "adult_only": True
            },
            "redtube": {
                "id": "redtube",
                "name": "RedTube Stream API",
                "url": "https://api.redtube.com/",
                "enabled": True,
                "category": "videos",
                "adult_only": True
            }
        },
        "custom_nodes": [],
        "custom_onion_engines": []
    },
    "max_concurrent_engines": 6,
    "request_timeout_sec": 12.0
}


def _get_config_manager():
    try:
        import sys
        if hasattr(sys, "hecos_config_manager") and sys.hecos_config_manager:
            return sys.hecos_config_manager
        from hecos.app.config import ConfigManager
        return ConfigManager()
    except Exception:
        return None


def get_search_config() -> Dict[str, Any]:
    """Retrieve the search config merged with defaults."""
    cfg_mgr = _get_config_manager()
    current = {}
    if cfg_mgr:
        try:
            browser_cfg = cfg_mgr.config.get("plugins", {}).get("BROWSER", {})
            current = browser_cfg.get("search", {})
        except Exception as e:
            logger.debug(f"Could not read search config from ConfigManager: {e}")

    # Deep merge with defaults
    result = json.loads(json.dumps(_DEFAULT_SEARCH_CONFIG))
    def _merge(dest: dict, src: dict):
        for k, v in src.items():
            if isinstance(v, dict) and k in dest and isinstance(dest[k], dict):
                _merge(dest[k], v)
            else:
                dest[k] = v
    if isinstance(current, dict):
        _merge(result, current)

    # Auto-populate tor_browser_path if not set
    tor_cfg = result.setdefault("tor", {})
    if not tor_cfg.get("tor_browser_path"):
        detected = detect_tor_browser_path()
        if detected:
            tor_cfg["tor_browser_path"] = detected

    return result


def update_search_config(updates: Dict[str, Any]) -> bool:
    """Updates the search section in Hecos plugins.BROWSER.search."""
    cfg_mgr = _get_config_manager()
    if not cfg_mgr:
        logger.warning("No ConfigManager available to persist search config.")
        return False

    try:
        current = get_search_config()
        # Merge
        def _merge(dest: dict, src: dict):
            for k, v in src.items():
                if isinstance(v, dict) and k in dest and isinstance(dest[k], dict):
                    _merge(dest[k], v)
                else:
                    dest[k] = v
        _merge(current, updates)

        browser_cfg = cfg_mgr.config.get("plugins", {}).get("BROWSER", {})
        browser_cfg["search"] = current

        payload = {
            "plugins": {
                "BROWSER": browser_cfg
            }
        }
        res = cfg_mgr.update_config(payload)
        logger.info(f"Deep Search config updated: ok={bool(res)}")
        return bool(res)
    except Exception as e:
        logger.error(f"Failed to update search config: {e}")
        return False


__all__ = [
    "get_search_config",
    "update_search_config",
    "_DEFAULT_SEARCH_CONFIG",
    "DEFAULT_SEARXNG_FALLBACKS",
    "build_endpoint_url",
    "decompose_endpoint_url",
    "get_endpoints",
    "update_endpoints",
    "get_engine_auth_headers",
    "reset_endpoints_to_defaults",
    "detect_tor_browser_path",
    "get_tor_browser_path",
    "launch_tor_browser"
]
