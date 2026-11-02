"""
search/tools.py
LLM Tool wrappers for Hecos Deep Search.
Returns dense, formatted Markdown for AI synthesis and appends the [[HSEARCH:<id>]]
interactive widget token for the Chat UI.
"""
from __future__ import annotations

import logging
from typing import Optional

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.tools")

from .models import SearchQuery
from .service import get_search_service
from .extract.fetcher import fetch_and_clean_page


class SearchTools:
    """Callable LLM tools for web and dark web discovery."""

    def __init__(self):
        self.service = get_search_service()

    def _format_for_llm(self, session, heading: str) -> str:
        """Formats search results concisely for the LLM context."""
        if getattr(session, "error", None):
            return f"⚠️ {heading}: {session.error}"

        if not session.results:
            return (
                f"⚠️ {heading}: No results found for query '{session.query}'.\n"
                f"Try rephrasing the query or using broader keywords."
            )

        lines = [f"### 🔍 {heading}: \"{session.query}\" ({session.total_results} results in {session.duration_ms}ms)\n"]

        for idx, r in enumerate(session.results, start=1):
            net_badge = "🧅 [TOR]" if r.network == "tor" else "🌐"
            source_tag = f"({r.engine})"
            lines.append(f"**[{idx}]** {net_badge} **[{r.title}]({r.url})** {source_tag}")
            if r.snippet:
                clean_snippet = r.snippet.replace("\n", " ").strip()
                lines.append(f"> {clean_snippet}")
            if r.media_url and r.media_url != r.url:
                lines.append(f"Media URL: {r.media_url}")
            lines.append("")

        lines.append(
            f"**AI Instructions**: Synthesize the findings concisely citing sources with reference numbers [1], [2], etc. "
            f"Do not dump the raw link list unless specifically requested by the user."
        )

        # Append interactive token for Chat UI
        lines.append(f"\n[[HSEARCH:{session.id}]]")

        return "\n".join(lines)

    # ── Tool Implementations ──────────────────────────────────────────────────

    def web_search(self, query: str, max_results: int = 10, engines: str = "all") -> str:
        """
        Searches the Clear Web across Google, Bing, Brave, DuckDuckGo and other engines.
        Returns dense summaries with sources.
        """
        hecos_logger.info(f"[SEARCH:TOOL] web_search called: query='{query}', limit={max_results}, engines='{engines}'")
        eng_list = [e.strip() for e in engines.split(",") if e.strip()] if engines != "all" else []
        sq = SearchQuery(
            query=query,
            mode="clear",
            limit=max_results,
            engines=eng_list
        )
        session = self.service.search(sq)
        hecos_logger.info(f"[SEARCH:TOOL] web_search completed: {session.total_results} results in {session.duration_ms}ms (session={session.id})")
        return self._format_for_llm(session, "Clear Web Search Results")

    def dark_search(self, query: str, max_results: int = 10, engines: str = "all") -> str:
        """
        Searches the Dark Web (.onion services) via Tor across Ahmia, Torch, Haystak, etc.
        Requires active Tor routing.
        """
        hecos_logger.info(f"[SEARCH:TOOL] dark_search called: query='{query}', limit={max_results}, engines='{engines}'")
        eng_list = [e.strip() for e in engines.split(",") if e.strip()] if engines != "all" else []
        sq = SearchQuery(
            query=query,
            mode="dark",
            limit=max_results,
            engines=eng_list
        )
        session = self.service.search(sq)
        hecos_logger.info(f"[SEARCH:TOOL] dark_search completed: {session.total_results} results in {session.duration_ms}ms (session={session.id})")
        return self._format_for_llm(session, "Dark Web (Tor) Search Results")

    def deep_search(self, query: str, max_results: int = 15) -> str:
        """
        Deep uninhibited search aggregating Clear Web, Dark Web (.onion), and file hunting.
        Automatically falls back to Tor if clear web has no results.
        """
        hecos_logger.info(f"[SEARCH:TOOL] deep_search called: query='{query}', limit={max_results}")
        sq = SearchQuery(
            query=query,
            mode="deep",
            limit=max_results
        )
        session = self.service.search(sq)
        hecos_logger.info(f"[SEARCH:TOOL] deep_search completed: {session.total_results} results in {session.duration_ms}ms (session={session.id})")
        return self._format_for_llm(session, "Deep Search Results (Clear + Tor + Files)")

    def media_search(self, query: str, media_type: str = "all", max_results: int = 10) -> str:
        """
        Searches for images, videos, audio and podcasts matching the query.
        media_type can be 'all', 'images', 'videos', or 'audio'.
        """
        hecos_logger.info(f"[SEARCH:TOOL] media_search called: query='{query}', media_type='{media_type}', limit={max_results}")
        mode = "media"
        engines = []
        if media_type == "images":
            engines = ["media_images"]
        elif media_type == "videos":
            engines = ["media_videos"]
        elif media_type == "audio":
            engines = ["media_audio"]

        sq = SearchQuery(
            query=query,
            mode=mode,
            engines=engines,
            limit=max_results
        )
        session = self.service.search(sq)
        hecos_logger.info(f"[SEARCH:TOOL] media_search completed: {session.total_results} results in {session.duration_ms}ms (session={session.id})")
        return self._format_for_llm(session, f"Media Search Results ({media_type})")

    def file_search(self, query: str, file_types: str = "pdf,docx,xlsx,zip,epub", max_results: int = 20) -> str:
        """
        Hunts for downloadable files and documents using deep file dorking across the Clear Web
        and Archive.org open library. Supports PDF, DOCX, XLSX, ZIP, EPUB and more.
        """
        hecos_logger.info(f"[SEARCH:TOOL] file_search called: query='{query}', types='{file_types}', limit={max_results}")
        ftype_list = [t.strip().lower() for t in file_types.split(",") if t.strip()]
        sq = SearchQuery(
            query=query,
            mode="files",
            limit=max_results,
            file_types=ftype_list
        )
        session = self.service.search(sq)
        hecos_logger.info(f"[SEARCH:TOOL] file_search completed: {session.total_results} results in {session.duration_ms}ms (session={session.id})")
        return self._format_for_llm(session, f"File & Document Search Results ({file_types})")

    def osint_search(self, username: str) -> str:
        """
        OSINT identity hunt: searches for active user profiles across 15+ major platforms
        (GitHub, Reddit, Telegram, Steam, Twitch, Medium, SoundCloud, etc.).
        """
        hecos_logger.info(f"[SEARCH:TOOL] osint_search called: username='{username}'")
        sq = SearchQuery(
            query=username,
            mode="osint",
            limit=50,
            target_username=username
        )
        session = self.service.search(sq)
        hecos_logger.info(f"[SEARCH:TOOL] osint_search completed: {session.total_results} profiles found in {session.duration_ms}ms (session={session.id})")
        return self._format_for_llm(session, f"OSINT Profile Hunt: {username}")

    def fetch_page(self, url: str, max_chars: int = 4000) -> str:
        """
        Reads and extracts the textual content of any webpage (Clearnet or Tor .onion).
        Use this to inspect links found during searches.
        """
        hecos_logger.info(f"[FETCHER:TOOL] fetch_page called: url='{url}', max_chars={max_chars}")
        data = fetch_and_clean_page(url=url, max_chars=max_chars)
        if not data["ok"]:
            hecos_logger.warning(f"[FETCHER:TOOL] fetch_page failed for url='{url}': {data.get('error')}")
            return f"⚠️ Error loading webpage ({url}): {data.get('error', 'Unable to access')}"

        title = data.get("title", "Webpage")
        desc = data.get("description", "")
        text = data.get("text", "")

        hecos_logger.info(f"[FETCHER:TOOL] fetch_page succeeded: title='{title}', chars={len(text)}, method={data.get('clean_method')}")
        out = [f"### 📄 {title} ({data['url']})"]
        if desc:
            out.append(f"**Description**: {desc}\n")
        out.append(text)
        out.append(f"\n[Content extracted via {data.get('fetch_engine', 'requests')} + {data.get('clean_method', 'cleaner')}]")
        return "\n".join(out)
