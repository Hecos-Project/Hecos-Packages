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
        self.slash_commands = ["/netsearch", "/search", "/dark", "/tor_new", "/files", "/osint"]
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
            "web_search": "Cerca nel Clear Web senza filtri.",
            "dark_search": "Cerca nel Dark Web (.onion) via Tor.",
            "deep_search": "Ricerca profonda combinata Clear + Tor + File.",
            "media_search": "Cerca immagini, video e audio.",
            "file_search": "Cerca file e documenti (PDF, DOCX, ZIP, EPUB) con dorks e Archive.org.",
            "osint_search": "OSINT: ricerca profili utente su 15+ piattaforme.",
            "fetch_page": "Leggi e pulisci il testo di qualsiasi pagina (Clearnet o .onion).",
            "/netsearch": "Ricerca profonda da chat",
            "/search": "Ricerca profonda da chat",
            "/dark": "Ricerca Dark Web da chat",
            "/files": "Cerca file e documenti da chat",
            "/osint": "OSINT username hunt da chat",
            "/tor_new": "Genera una nuova identità e circuito Tor (NEWNYM)"
        }
    }


def status() -> str:
    return "ONLINE"
