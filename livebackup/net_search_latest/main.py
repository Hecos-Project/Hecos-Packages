"""
net_search/main.py
Root entry-point for the Net Search System App (ClearWeb, Tor DarkWeb, Media & Files).
"""
from __future__ import annotations

import os
import sys
import logging
from typing import Optional, Dict, Any

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search")

logger = hecos_logger

# Ensure local module directory is in sys.path
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from .search.tools import SearchTools
from .search import init_search_subsystem


class NetSearchTools:
    """Callable LLM Tools and Slash Commands for Hecos Net Search."""

    def __init__(self):
        self.tag = "NETSEARCH"
        self.desc = "Net Search: Multi-engine Web, Tor DarkWeb (.onion), OSINT, Media and Deep File Intelligence."
        self.icon = "fas fa-satellite-dish"
        self.status = "ONLINE"
        self.category = "SISTEMA"
        self.routing_instructions = (
            "NET SEARCH & INTELLIGENCE EXECUTION RULES:\n\n"
            "1. WEB SEARCH: If the user asks to search the web, find news, or search anything online, call NETSEARCH__web_search(query=...).\n"
            "2. DARK WEB: If the user asks for Tor, .onion, hidden services, dark web, or uninhibited search, call NETSEARCH__dark_search(query=...).\n"
            "3. DEEP SEARCH: If the user asks for comprehensive / deep search combining Clear + Dark + Files, call NETSEARCH__deep_search(query=...).\n"
            "4. MEDIA SEARCH: If the user asks for images, videos, audio/soundtracks, call NETSEARCH__media_search(query=..., media_type=...).\n"
            "5. FILE SEARCH: If the user asks for documents, PDFs, ebooks, zip archives, or file downloads, call NETSEARCH__file_search(query=..., file_types=...).\n"
            "6. OSINT: If the user asks to find a person's online accounts, usernames, or social profiles, call NETSEARCH__osint_search(username=...).\n"
            "7. READ WEBPAGE: If the user asks to inspect, read, or scrape a specific URL (clearnet or .onion), call NETSEARCH__fetch_page(url=...)."
        )
        self.slash_commands = [
            {
                "id": "search",
                "aliases": ["/search", "/netsearch", "/cerca", "/websearch"],
                "description": "Searches the web, dark web, media, and files across all engines",
                "usage": "/search <query>",
                "example": "/search artificial intelligence",
                "icon": "🌐",
                "category": "NETSEARCH",
                "method": "slash_search",
                "args_schema": {"query": "str"},
                "requires_args": True,
            },
            {
                "id": "dark",
                "aliases": ["/dark", "/onion", "/tor_search"],
                "description": "Searches the Tor Dark Web (.onion hidden services)",
                "usage": "/dark <query>",
                "example": "/dark cybersecurity",
                "icon": "🧅",
                "category": "NETSEARCH",
                "method": "slash_dark",
                "args_schema": {"query": "str"},
                "requires_args": True,
            },
            {
                "id": "media",
                "aliases": ["/media", "/find_media"],
                "description": "Searches for images, videos, podcasts and audio online",
                "usage": "/media <query>",
                "example": "/media 4k nature",
                "icon": "🎬",
                "category": "NETSEARCH",
                "method": "slash_media",
                "args_schema": {"query": "str"},
                "requires_args": True,
            },
            {
                "id": "videos",
                "aliases": ["/videos", "/video", "/cerca_video"],
                "description": "Searches for videos across YouTube, Vimeo, Peertube, and web sources",
                "usage": "/videos <query>",
                "example": "/videos flying horses",
                "icon": "📹",
                "category": "NETSEARCH",
                "method": "slash_videos",
                "args_schema": {"query": "str"},
                "requires_args": True,
            },
            {
                "id": "images",
                "aliases": ["/images", "/immagini", "/foto_web", "/cerca_immagini"],
                "description": "Searches the web for real photos, illustrations, and images",
                "usage": "/images <query>",
                "example": "/images flying horses",
                "icon": "🖼️",
                "category": "NETSEARCH",
                "method": "slash_images",
                "args_schema": {"query": "str"},
                "requires_args": True,
            },
            {
                "id": "files",
                "aliases": ["/files", "/file", "/dorks", "/cerca_file"],
                "description": "Hunts for downloadable files, PDFs, ebooks, and archives online",
                "usage": "/files <query>",
                "example": "/files machine learning pdf",
                "icon": "📁",
                "category": "NETSEARCH",
                "method": "slash_files",
                "args_schema": {"query": "str"},
                "requires_args": True,
            },
            {
                "id": "osint",
                "aliases": ["/osint", "/whois_user"],
                "description": "Searches for a username across 15+ social and coding platforms",
                "usage": "/osint <username>",
                "example": "/osint johndoe",
                "icon": "🕵️",
                "category": "NETSEARCH",
                "method": "slash_osint",
                "args_schema": {"username": "str"},
                "requires_args": True,
            },
            {
                "id": "fetch",
                "aliases": ["/fetch", "/scrape", "/read_page"],
                "description": "Fetches and extracts clean text from any URL (Clearnet or Tor .onion)",
                "usage": "/fetch <url>",
                "example": "/fetch https://example.com",
                "icon": "📄",
                "category": "NETSEARCH",
                "method": "slash_fetch",
                "args_schema": {"url": "str"},
                "requires_args": True,
            },
            {
                "id": "tor_new",
                "aliases": ["/tor_new", "/new_circuit"],
                "description": "Requests a new Tor identity circuit",
                "usage": "/tor_new",
                "example": "/tor_new",
                "icon": "🧅",
                "category": "NETSEARCH",
                "method": "slash_tor_new",
                "args_schema": {},
                "requires_args": False,
            },
            {
                "id": "search_engines",
                "aliases": ["/search_engines", "/engines"],
                "description": "Displays the status of active search engines and daemons",
                "usage": "/search_engines",
                "example": "/search_engines",
                "icon": "🛰️",
                "category": "NETSEARCH",
                "method": "slash_search_engines",
                "args_schema": {},
                "requires_args": False,
            },
            {
                "id": "search_config",
                "aliases": ["/search_config"],
                "description": "Inspects or updates Net Search configuration",
                "usage": "/search_config [set <key> <val>]",
                "example": "/search_config",
                "icon": "⚙️",
                "category": "NETSEARCH",
                "method": "slash_search_config",
                "args_schema": {"args": "str"},
                "requires_args": False,
            }
        ]
        self._tools_impl = SearchTools()

    # ── LLM Function Calling Tools ────────────────────────────────────────────

    def web_search(self, query: str, max_results: int = 10) -> str:
        """Searches the Clearnet using privacy-preserving aggregators (SearXNG, DuckDuckGo, Brave, etc.)."""
        return self._tools_impl.web_search(query=query, max_results=max_results)

    def dark_search(self, query: str, max_results: int = 10) -> str:
        """Searches the Tor Dark Web (.onion hidden services) through Ahmia, TorDex, Phobos, and onion crawlers."""
        return self._tools_impl.dark_search(query=query, max_results=max_results)

    def deep_search(self, query: str, max_results: int = 15) -> str:
        """Deep uninhibited search aggregating Clear Web, Dark Web (.onion), and file hunting."""
        return self._tools_impl.deep_search(query=query, max_results=max_results)

    def media_search(self, query: str, media_type: str = "all", max_results: int = 10) -> str:
        """Searches for images, videos, audio and podcasts matching the query."""
        return self._tools_impl.media_search(query=query, media_type=media_type, max_results=max_results)

    def file_search(self, query: str, file_types: str = "pdf,docx,xlsx,zip,epub", max_results: int = 20) -> str:
        """Hunts for downloadable files and documents using multi-extension dork queries and Archive.org."""
        return self._tools_impl.file_search(query=query, file_types=file_types, max_results=max_results)

    def osint_search(self, username: str) -> str:
        """OSINT identity hunt: finds active user profiles across 15+ social and coding platforms."""
        return self._tools_impl.osint_search(username=username)

    def fetch_page(self, url: str, max_chars: int = 4000) -> str:
        """Reads and extracts the textual content of any webpage (Clearnet or Tor .onion)."""
        return self._tools_impl.fetch_page(url=url, max_chars=max_chars)

    # ── Slash Commands ────────────────────────────────────────────────────────

    def slash_netsearch(self, args: str) -> str:
        if not args:
            return "Please specify a search query. Example: `/netsearch artificial intelligence`"
        return self.deep_search(args.strip())

    def slash_search(self, args: str) -> str:
        if not args:
            return "Please specify a search query. Example: `/search artificial intelligence`"
        return self.deep_search(args.strip())

    def slash_dark(self, args: str) -> str:
        if not args:
            return "Please specify a query for Dark Web search. Example: `/dark cybersecurity`"
        return self.dark_search(args.strip())

    def slash_files(self, args: str) -> str:
        if not args:
            return "Please specify what to search. Example: `/files machine learning pdf`"
        return self.file_search(args.strip())

    def slash_osint(self, args: str) -> str:
        if not args:
            return "Please specify a username. Example: `/osint johndoe123`"
        return self.osint_search(args.strip())

    def slash_tor_new(self, args: str = "") -> str:
        try:
            from .search.components.catalog import get_component
            comp = get_component("tor_daemon")
            if comp:
                ok, msg = comp.new_circuit()
                return f"🧅 Tor: {msg}"
            return "⚠️ Tor component not found."
        except Exception as e:
            return f"⚠️ Tor command error: {e}"

    def slash_images(self, args: str) -> str:
        if not args:
            return "Please specify an image query. Example: `/images running horses`"
        return self.media_search(args.strip(), media_type="images")

    def slash_videos(self, args: str) -> str:
        if not args:
            return "Please specify a video query. Example: `/videos flying horses`"
        return self.media_search(args.strip(), media_type="videos")

    def slash_audio(self, args: str) -> str:
        if not args:
            return "Please specify an audio or podcast query. Example: `/audio epic soundtrack`"
        return self.media_search(args.strip(), media_type="audio")

    def slash_media(self, args: str) -> str:
        if not args:
            return "Please specify a media query. Example: `/media 4k nature`"
        return self.media_search(args.strip(), media_type="all")

    def slash_fetch(self, args: str) -> str:
        if not args:
            return "Please specify a URL to scrape and analyze. Example: `/fetch https://example.com`"
        return self.fetch_page(args.strip())

    def slash_search_engines(self, args: str = "") -> str:
        from .search.config import get_search_config
        from .search.components.catalog import get_all_statuses
        cfg = get_search_config()
        lines = ["### 🛰 Net Search Engine & Subsystem Status\n"]
        lines.append(f"- **Local Privacy Shield**: `{'ACTIVE' if cfg.get('local_only') else 'OFF'}`")
        lines.append(f"- **Tor Routing**: `{'ACTIVE' if cfg.get('tor', {}).get('enabled') else 'OFF'}`")
        lines.append(f"- **SearXNG Daemon**: `{'ACTIVE' if cfg.get('searxng', {}).get('enabled') else 'OFF'}` ({cfg.get('searxng', {}).get('url')})")
        lines.append("\n**Components:**")
        for st in get_all_statuses():
            is_run = st.get("is_running", False)
            is_inst = st.get("is_installed", False)
            ico = "🟢" if is_run else ("⚪" if is_inst else "🔴")
            lines.append(f"- {ico} **{st.get('name', 'Component')}** (`{st.get('id')}`): {'Running' if is_run else ('Installed' if is_inst else 'Not installed')}")
        return "\n".join(lines)

    def slash_search_config(self, args: str = "") -> str:
        from .search.config import get_search_config, update_search_config
        arg_str = args.strip()
        if not arg_str:
            cfg = get_search_config()
            return (
                "### ⚙️ Net Search Config\n"
                f"- `local_only`: `{cfg.get('local_only', False)}` (strictly local SearXNG daemon)\n"
                f"- `default_mode`: `{cfg.get('default_mode', 'clear')}`\n"
                f"- `safe_search`: `{cfg.get('safe_search', False)}`\n"
                f"- `tor.enabled`: `{cfg.get('tor', {}).get('enabled', False)}`\n"
                "\n*Use `/search_config set local_only true|false` or `/search_config set tor true|false` to update.*"
            )
        parts = arg_str.split()
        if len(parts) >= 3 and parts[0].lower() == "set":
            key, val = parts[1].lower(), parts[2].lower()
            bval = val in ("1", "true", "yes", "on", "si")
            if key in ("local_only", "privacy_shield"):
                update_search_config({"local_only": bval})
                return f"✅ `local_only` set to `{bval}`."
            elif key in ("tor", "tor_enabled"):
                update_search_config({"tor": {"enabled": bval}})
                return f"✅ `tor.enabled` set to `{bval}`."
        return "⚠️ Usage: `/search_config` or `/search_config set <local_only|tor> <true|false>`"



tools = NetSearchTools()


def on_load(config=None, **kwargs):
    """Called on Hecos boot when on_load = true in hpkg_manifest.toml."""
    try:
        init_search_subsystem()
    except Exception as e:
        logger.warning(f"[NetSearch] on_load init warning: {e}")

    # NOTE: Flask routes are registered explicitly by server_flask.py.
    # The block below is a fallback for hot-reload / late-boot scenarios only.
    # We guard against double registration (Flask raises AssertionError otherwise).
    app = getattr(sys, "hecos_flask_app", None)
    cfg_mgr = getattr(sys, "hecos_config_manager", None)
    if app:
        # Check if /search is already registered to avoid duplicate endpoint errors
        already_registered = "search_page" in app.view_functions
        if not already_registered:
            try:
                from .web.routes import init_plugin_routes
                init_plugin_routes(app, cfg_mgr, os.path.dirname(os.path.abspath(__file__)))
                logger.info("[NetSearch] Routes registered via on_load fallback.")
            except Exception as e:
                logger.error(f"[NetSearch] Error registering routes: {e}", exc_info=True)
        else:
            logger.debug("[NetSearch] Routes already registered — skipping on_load duplicate.")
    return tools


def info() -> Dict[str, Any]:
    return {
        "tag": "NETSEARCH",
        "name": "Net Search",
        "version": "1.0.0",
        "type": "system_app",
        "description": "Hecos Net Search & Intelligence System App: Multi-engine ClearWeb, Tor DarkWeb, Media and File hunting.",
        "commands": {
            "web_search": "Search the clear web without censorship.",
            "dark_search": "Search the Tor dark web (.onion hidden services).",
            "deep_search": "Deep uninhibited search combining clear, dark web, and file hunting.",
            "media_search": "Search images, videos, podcasts, and audio.",
            "file_search": "Hunt for documents and files (PDF, DOCX, ZIP, EPUB) using dorks and Archive.org.",
            "osint_search": "OSINT profile hunt across 15+ major platforms.",
            "fetch_page": "Extract and clean text content of any webpage (Clearnet or Tor .onion).",
            "/netsearch": "Deep search from chat",
            "/search": "Deep search from chat",
            "/dark": "Tor Dark Web search from chat",
            "/files": "Hunt files and documents from chat",
            "/osint": "OSINT username hunt from chat",
            "/tor_new": "Generate a new Tor circuit identity (NEWNYM)",
            "/images": "Search images and photos from chat",
            "/videos": "Search videos with thumbnails and players from chat",
            "/audio": "Search audio tracks and podcasts from chat",
            "/media": "Search combined media (images, videos, audio) from chat",
            "/fetch": "Scrape and clean webpage content from chat",
            "/search_engines": "Show status of all search engines and daemons",
            "/search_config": "Inspect or set quick search configuration"
        }
    }


def status() -> str:
    return "ONLINE"
