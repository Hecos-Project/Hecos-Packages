"""
search/engines/files_dorks.py
Deep File & Document Hunter.
Executes parallel multi-extension file dorks (PDF, DOCX, XLSX, ZIP, EPUB)
and aggregates Archive.org open document libraries to discover abundant unindexed files.
"""
from __future__ import annotations

import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set

from .base import BaseEngine
from ..models import SearchQuery, SearchResult
from .. import http_client

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.files")

COMMON_EXTS = ["pdf", "docx", "xlsx", "zip", "epub"]


class FilesDorksEngine(BaseEngine):
    """File Hunter using targeted multi-extension dorking syntax."""

    def __init__(self):
        super().__init__(
            engine_id="files_dorks",
            name="Deep File & Document Hunter",
            category="files",
            network="clearnet",
            priority=85
        )

    def is_available(self) -> bool:
        return True

    def search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen_urls: Set[str] = set()
        is_unlimited = (query.limit is not None and query.limit <= 0)
        target_limit = 100000 if is_unlimited else max(query.limit, 40)
        exts = query.file_types if query.file_types else COMMON_EXTS

        dork_max = 35 if is_unlimited or target_limit > 50 else 15
        archive_rows = 75 if is_unlimited or target_limit > 50 else 25

        def _fetch_dork_ext(ext: str) -> List[SearchResult]:
            items: List[SearchResult] = []
            try:
                from ddgs import DDGS
                ddg = DDGS(timeout=min(query.timeout, 8.0))
                raw = ddg.text(f"{query.query} filetype:{ext}", max_results=dork_max)
                for item in raw:
                    href = item.get("href", "") or item.get("url", "")
                    title = item.get("title", "")
                    body = item.get("body", "") or item.get("snippet", "")
                    if href and title:
                        items.append(SearchResult(
                            title=f"[{ext.upper()}] {title}",
                            url=href,
                            snippet=body,
                            engine="file_dork",
                            category="files",
                            network="clearnet",
                            metadata={"extension": ext}
                        ))
            except Exception as e:
                hecos_logger.debug(f"[SEARCH:DORKS] Dork filetype:{ext} note: {e}")
            return items

        def _fetch_archive_org() -> List[SearchResult]:
            items: List[SearchResult] = []
            try:
                import requests
                from ..config import get_search_config
                url = get_search_config().get("endpoints", {}).get("archives", {}).get("archive_org") or "https://archive.org/advancedsearch.php"
                params = {
                    "q": f"{query.query} mediatype:texts",
                    "fl[]": "identifier,title,description,format",
                    "rows": archive_rows,
                    "output": "json"
                }
                resp = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=min(query.timeout, 8.0))
                if resp.status_code == 200:
                    docs = resp.json().get("response", {}).get("docs", [])
                    for d in docs:
                        ident = d.get("identifier", "")
                        title = d.get("title", "") or ident
                        desc = d.get("description", "")
                        if isinstance(desc, list):
                            desc = " ".join(desc)
                        if ident:
                            page_url = f"https://archive.org/details/{ident}"
                            items.append(SearchResult(
                                title=f"[PDF/DOC] {title}",
                                url=page_url,
                                snippet=desc[:160] if desc else f"Archive Text: {ident}",
                                engine="archive_org:texts",
                                category="files",
                                network="clearnet",
                                metadata={"extension": "pdf", "identifier": ident}
                            ))
            except Exception as e:
                hecos_logger.debug(f"[SEARCH:DORKS] Archive.org fetch note: {e}")
            return items

        # Execute dork queries and Archive.org concurrently
        tasks = [_fetch_archive_org]
        for e in exts:
            tasks.append(lambda ext=e: _fetch_dork_ext(ext))

        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = [executor.submit(fn) for fn in tasks]
            for fut in as_completed(futures):
                try:
                    for item in fut.result():
                        if item.url not in seen_urls:
                            seen_urls.add(item.url)
                            results.append(item)
                            if len(results) >= target_limit:
                                break
                except Exception:
                    pass

        hecos_logger.info(f"[SEARCH:DORKS] Aggregated {len(results)} files & documents across dorks")
        return results
