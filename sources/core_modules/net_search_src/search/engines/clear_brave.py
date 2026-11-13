"""
search/engines/clear_brave.py
Brave Search API direct engine for Hecos Net Search.
Provides uncensored, independent-index results with no CAPTCHA and no rate-limiting
when an API key is configured. Free tier: 2000 queries/month.

API Docs: https://api.search.brave.com/app/documentation/web-search/get-started
"""
from __future__ import annotations

import logging
import time
from typing import List

from .base import BaseEngine
from .files_apis import infer_extension
from ..models import SearchQuery, SearchResult
from ..config import get_search_config
from .. import http_client

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.brave")


BRAVE_SEARCH_API_URL = "https://api.search.brave.com/res/v1/web/search"


class ClearBraveEngine(BaseEngine):
    """
    Brave Search API direct engine.
    Returns up to 100 high-quality, uncensored results per query.
    Requires a Brave Search API key (free tier: 2000 req/month).
    Configure via: search.endpoints.brave_api_key in Hecos settings.
    """

    def __init__(self):
        super().__init__(
            engine_id="clear_brave",
            name="Brave Search API (Direct)",
            category="general",
            network="clearnet",
            priority=92  # High priority — reliable, no CAPTCHA
        )

    def is_available(self) -> bool:
        cfg = get_search_config()
        api_key = (
            cfg.get("endpoints", {}).get("brave_api_key", "")
            or cfg.get("brave_api_key", "")
        )
        available = bool(api_key and str(api_key).strip())
        if not available:
            hecos_logger.debug(
                "[BraveAPI] Engine unavailable: no brave_api_key configured. "
                "Get a free key at https://api.search.brave.com/app/keys"
            )
        return available

    def search(self, query: SearchQuery) -> List[SearchResult]:
        t0 = time.time()
        cfg = get_search_config()
        api_key = (
            cfg.get("endpoints", {}).get("brave_api_key", "")
            or cfg.get("brave_api_key", "")
        ).strip()

        if not api_key:
            hecos_logger.warning("[BraveAPI] No API key — skipping Brave Search")
            return []

        is_unlimited = (query.limit is not None and query.limit <= 0)
        target = 100000 if is_unlimited else max(query.limit or 20, 20)
        # Brave API: max 20 per request, max 100 per query (5 pages of 20)
        max_brave_results = min(target, 100)
        count_per_page = 20
        max_pages = max(1, min(5, (max_brave_results + count_per_page - 1) // count_per_page))

        safesearch = "off" if not query.safe_search else "moderate"

        hecos_logger.info(
            f"[BraveAPI] Querying Brave Search API (pages={max_pages}, "
            f"safe={safesearch}, target={max_brave_results}): '{query.query}'"
        )

        results: List[SearchResult] = []
        seen_urls = set()

        for page in range(max_pages):
            offset = page * count_per_page
            if len(results) >= max_brave_results:
                break

            q_text = query.query
            if query.mode == "files" and "filetype:" not in q_text.lower():
                if query.file_types:
                    ft_clause = " OR ".join(f"filetype:{ft.strip().lstrip('.')}" for ft in query.file_types[:5] if ft.strip())
                    q_text = f"{q_text} ({ft_clause})" if ft_clause else q_text
                else:
                    q_text = f"{q_text} (filetype:pdf OR filetype:docx OR filetype:csv OR filetype:zip OR filetype:iso OR filetype:py)"

            params = {
                "q": q_text,
                "count": count_per_page,
                "offset": offset,
                "safesearch": safesearch,
                "text_decorations": "false",
                "result_filter": "web",
                "search_lang": "en",
                "ui_lang": "en-US",
            }
            if query.time_range:
                freshness_map = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}
                brave_freshness = freshness_map.get(query.time_range, "")
                if brave_freshness:
                    params["freshness"] = brave_freshness

            try:
                resp = http_client.get(
                    BRAVE_SEARCH_API_URL,
                    network="clearnet",
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                        "X-Subscription-Token": api_key,
                    },
                    params=params,
                    timeout=min(query.timeout, 8.0)
                )

                if resp.status_code == 401:
                    hecos_logger.error("[BraveAPI] Invalid API key (HTTP 401). Check brave_api_key in settings.")
                    break
                if resp.status_code == 429:
                    hecos_logger.warning("[BraveAPI] Rate limited (HTTP 429). Free tier exhausted for today.")
                    break
                if resp.status_code != 200:
                    hecos_logger.warning(f"[BraveAPI] HTTP {resp.status_code} on page {page+1}")
                    break

                data = resp.json()
                web_results = data.get("web", {}).get("results", [])

                if not web_results:
                    hecos_logger.debug(f"[BraveAPI] Page {page+1}: no results returned")
                    break

                page_added = 0
                for item in web_results:
                    url = item.get("url", "")
                    title = item.get("title", "")
                    description = item.get("description", "")
                    extra = item.get("extra_snippets", [])
                    snippet = description
                    if extra:
                        snippet = description + " | " + " ".join(extra[:2])

                    if title and url and url not in seen_urls:
                        seen_urls.add(url)
                        ext = infer_extension(url, fallback="pdf" if query.mode == "files" else "")
                        meta = {
                            "source_engine": "brave",
                            "age": item.get("age", ""),
                            "language": item.get("language", ""),
                        }
                        if ext:
                            meta["extension"] = ext
                        results.append(SearchResult(
                            title=title,
                            url=url,
                            snippet=snippet,
                            engine="brave_api",
                            engine_id="clear_brave",
                            category="files" if query.mode == "files" else "general",
                            network="clearnet",
                            score=1.5,  # High base score — Brave results are reliable
                            metadata=meta
                        ))
                        page_added += 1

                hecos_logger.debug(f"[BraveAPI] Page {page+1} (offset={offset}): +{page_added} results")

                if page_added == 0:
                    break

            except Exception as e:
                hecos_logger.error(f"[BraveAPI] Request failed (page {page+1}): {e}")
                break

        elapsed = round((time.time() - t0) * 1000)
        hecos_logger.info(f"[BraveAPI] Completed: {len(results)} results in {elapsed}ms for '{query.query}'")
        return results
