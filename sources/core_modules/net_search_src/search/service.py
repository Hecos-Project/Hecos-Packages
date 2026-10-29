"""
search/service.py
Central orchestrator for Hecos Deep Search & Intelligence.
Handles parallel engine fan-out, streaming SSE callbacks, deduplication,
scoring, session persistence, and automatic Tor fallback.
"""
from __future__ import annotations

import time
import urllib.parse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Callable, Generator

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.service")

from .models import SearchQuery, SearchResult, SearchSession
from .engines import get_engines_for_mode, get_all_engines
from .sessions import get_session_store
from .config import get_search_config


def _normalize_url(url: str) -> str:
    """Strips tracking params and trailing slashes for clean deduplication."""
    try:
        parsed = urllib.parse.urlparse(url)
        # Strip common tracking query params
        qs = urllib.parse.parse_qsl(parsed.query)
        clean_qs = [(k, v) for k, v in qs if not k.startswith("utm_") and k not in ("fbclid", "gclid", "ref")]
        clean_query = urllib.parse.urlencode(clean_qs)
        path = parsed.path.rstrip("/")
        return f"{parsed.scheme}://{parsed.netloc}{path}{'?' + clean_query if clean_query else ''}".lower()
    except Exception:
        return url.strip().rstrip("/").lower()


class HecosSearchService:
    """Orchestrator for all search queries and discovery workflows."""

    def __init__(self):
        self.session_store = get_session_store()

    def search(
        self,
        query: SearchQuery,
        stream_cb: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> SearchSession:
        """
        Executes search across engines with fan-out, dedup, and persistence.
        """
        start_time = time.time()
        cfg = get_search_config()

        session = SearchSession(
            query=query.query,
            mode=query.mode
        )

        if not cfg.get("enabled", True):
            hecos_logger.warning(f"[SEARCH] Query aborted: Deep Search is disabled in system configuration.")
            session.total_results = 0
            session.error = "Deep Search is disabled in system settings. Enable it under Browser Settings (/hecos/config/ui#browser)."
            if stream_cb:
                stream_cb({
                    "type": "error",
                    "error": session.error
                })
            return session

        max_workers = int(cfg.get("max_concurrent_engines", 6))

        engines = get_engines_for_mode(query.mode, query.engines)
        session.engines_queried = [e.id for e in engines]

        if not engines:
            hecos_logger.warning(f"[SEARCH] No active/available engines for mode '{query.mode}'.")
            session.total_results = 0
            session.error = f"No active engines available for mode '{query.mode}'. Ensure required components (e.g. Tor or DDGS) are installed and enabled in settings (/hecos/config/ui#browser)."
            if stream_cb:
                stream_cb({
                    "type": "error",
                    "error": session.error
                })
            return session

        hecos_logger.info(
            f"[SEARCH] Query started: '{query.query}' [mode={query.mode}, limit={query.limit}] "
            f"across {len(engines)} engines: {session.engines_queried}"
        )

        if stream_cb:
            stream_cb({
                "type": "start",
                "session_id": session.id,
                "engines": session.engines_queried,
                "query": query.query,
                "mode": query.mode
            })

        accumulated_results: List[SearchResult] = []
        seen_urls: Dict[str, SearchResult] = {}

        def _run_engine(eng):
            try:
                hecos_logger.debug(f"[SEARCH] Launching engine '{eng.id}' for query '{query.query}'...")
                t0 = time.time()
                items = eng.search(query)
                dur = round((time.time() - t0) * 1000)
                hecos_logger.info(f"[SEARCH] Engine '{eng.id}' completed in {dur}ms: found {len(items)} results")
                return eng.id, items, dur, None
            except Exception as exc:
                hecos_logger.warning(f"[SEARCH] Engine '{eng.id}' error: {exc}")
                return eng.id, [], 0, str(exc)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_engine = {executor.submit(_run_engine, eng): eng for eng in engines}

            for future in as_completed(future_to_engine):
                engine_id, items, dur, err = future.result()

                new_items_for_stream: List[Dict[str, Any]] = []

                if err:
                    hecos_logger.debug(f"[SEARCH] Engine '{engine_id}' reported error: {err}")
                else:
                    for item in items:
                        item.engine_id = engine_id
                        if item.metadata is None:
                            item.metadata = {}
                        item.metadata["engine_id"] = engine_id

                        norm = _normalize_url(item.url)
                        if norm in seen_urls:
                            # Bump score if found by multiple engines
                            existing = seen_urls[norm]
                            existing.score += 0.5
                            if engine_id not in existing.engine:
                                existing.engine += f", {engine_id}"
                            existing_ids = existing.metadata.setdefault("engine_ids", [])
                            if engine_id not in existing_ids:
                                existing_ids.append(engine_id)
                        else:
                            seen_urls[norm] = item
                            accumulated_results.append(item)
                            new_items_for_stream.append(item.to_dict())

                if stream_cb:
                    stream_cb({
                        "type": "engine_done",
                        "engine": engine_id,
                        "duration_ms": dur,
                        "new_results": new_items_for_stream,
                        "total_so_far": len(accumulated_results),
                        "error": err
                    })

        # Automatic fallback: only if tor is explicitly enabled in config, tor is online, and clear web returned 0 results
        tor_enabled = cfg.get("tor", {}).get("enabled", False)
        if not accumulated_results and query.auto_fallback_tor and tor_enabled and query.mode in ("clear", "deep"):
            hecos_logger.info("[SEARCH:TOR] Clear Web yielded 0 results. Triggering automatic Tor Dark Web fallback...")
            if stream_cb:
                stream_cb({
                    "type": "fallback",
                    "message": "No results found on Clear Web. Automatically initiating Tor Dark Web fallback search..."
                })

            dark_engines = get_engines_for_mode("dark")
            for deng in dark_engines:
                session.engines_queried.append(deng.id)
                try:
                    hecos_logger.info(f"[SEARCH:TOR] Running Tor fallback engine '{deng.id}'...")
                    d_items = deng.search(query)
                    hecos_logger.info(f"[SEARCH:TOR] Fallback engine '{deng.id}' returned {len(d_items)} results")
                    for item in d_items:
                        norm = _normalize_url(item.url)
                        if norm not in seen_urls:
                            seen_urls[norm] = item
                            accumulated_results.append(item)
                except Exception as e:
                    hecos_logger.debug(f"[SEARCH:TOR] Tor fallback engine '{deng.id}' error: {e}")

        # Sort by score desc, keeping all unique multi-engine results
        accumulated_results.sort(key=lambda x: x.score, reverse=True)
        if query.limit and query.limit > 0:
            max_total = max(int(cfg.get("max_total_results", 500)), query.limit * max(1, len(engines)))
            session.results = accumulated_results[:max_total]
        else:
            # Unlimited / Infinite mode (query.limit <= 0 or None)
            session.results = accumulated_results
        session.total_results = len(session.results)
        session.duration_ms = round((time.time() - start_time) * 1000)

        # Save session
        self.session_store.save_session(session)

        if stream_cb:
            stream_cb({
                "type": "complete",
                "session_id": session.id,
                "total_results": session.total_results,
                "duration_ms": session.duration_ms
            })

        hecos_logger.info(
            f"[SEARCH] Query finished: {session.total_results} unique results (from {len(accumulated_results)} raw) "
            f"in {session.duration_ms}ms [Session: {session.id}]"
        )
        return session


_global_service: Optional[HecosSearchService] = None

def get_search_service() -> HecosSearchService:
    global _global_service
    if _global_service is None:
        _global_service = HecosSearchService()
    return _global_service
