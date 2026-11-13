"""
search/engines/files_dorks.py
Deep File & Document Hunter.
Combines batched multi-extension dorking across Clearnet (DDGS + direct HTML fallback)
with fast open-API file & repository adapters (`files_apis.py`) covering Documents (PDF/DOC/EPUB),
Data & Sheets (CSV/XLSX/JSON), Archives (ZIP/ISO/7z), and Code & Packages (GitHub/npm).
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Tuple

from .base import BaseEngine
from .files_apis import (
    ARCHIVE_EXTS,
    CODE_EXTS,
    DATA_EXTS,
    DOC_EXTS,
    fetch_archive_org_files,
    fetch_arxiv_pdfs,
    fetch_github_repos,
    fetch_huggingface_datasets,
    fetch_npm_packages,
    fetch_openalex_pdfs,
    fetch_wikimedia_files,
    infer_extension,
)
from .. import http_client
from ..config import get_search_config
from ..models import SearchQuery, SearchResult

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.files")

# Thematic dork batches align 1:1 with File Hunter UI subtabs (Docs, Data, Archives, Code)
DEFAULT_DORK_BATCHES: List[Tuple[str, List[str]]] = [
    ("pdf", ["pdf", "docx", "epub", "odt"]),
    ("csv", ["xlsx", "csv", "json", "sql"]),
    ("zip", ["zip", "iso", "7z", "rar"]),
    ("py",  ["py", "sh", "yaml", "js"]),
]


def _extract_ddg_html_dork(dork_query: str, fallback_ext: str, limit: int, timeout: float) -> List[SearchResult]:
    """Direct HTML DuckDuckGo fallback using Hecos http_client when DDGS library is rate-limited."""
    items: List[SearchResult] = []
    try:
        resp = http_client.post(
            "https://html.duckduckgo.com/html/",
            network="clearnet",
            data={"q": dork_query, "b": "", "kp": "-2"},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
                "Referer": "https://html.duckduckgo.com/",
                "Origin": "https://html.duckduckgo.com",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=min(timeout, 5.0),
        )
        if resp.status_code != 200 or not resp.text:
            return items
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml")
        for node in soup.find_all("div", class_="result"):
            if "result--ad" in node.get("class", []):
                continue
            a_tag = node.find("a", class_="result__a")
            s_tag = node.find("a", class_="result__snippet")
            if not a_tag:
                continue
            href = (a_tag.get("href") or "").strip()
            title = a_tag.get_text(" ", strip=True)
            if not (href.startswith(("http://", "https://")) and title):
                continue
            ext = infer_extension(href, fallback=fallback_ext)
            items.append(SearchResult(
                title=f"[{ext.upper()}] {title}" if ext else title,
                url=href,
                snippet=(s_tag.get_text(" ", strip=True) if s_tag else ""),
                engine="file_dork:html",
                category="files",
                network="clearnet",
                score=1.1,
                metadata={"extension": ext} if ext else {},
            ))
            if len(items) >= limit:
                break
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:DORKS] DDG HTML fallback note: {exc}")
    return items


class FilesDorksEngine(BaseEngine):
    """File Hunter aggregating multi-extension dorks and open file/code/dataset APIs."""

    def __init__(self):
        super().__init__(
            engine_id="files_dorks",
            name="Deep File & Document Hunter",
            category="files",
            network="clearnet",
            priority=96,
        )

    def is_available(self) -> bool:
        return True

    def search(self, query: SearchQuery) -> List[SearchResult]:
        cfg = get_search_config()
        is_local_only = (
            bool(query.local_only)
            if getattr(query, "local_only", None) is not None
            else bool(cfg.get("local_only", False))
        )
        if is_local_only:
            hecos_logger.info("[SEARCH:DORKS] Privacy Shield local_only active — skipping external File Hunter APIs.")
            return []

        results: List[SearchResult] = []
        seen_urls: Set[str] = set()
        is_unlimited = query.limit is not None and query.limit <= 0
        target_limit = 100000 if is_unlimited else max(query.limit or 50, 60)

        dork_max = 30 if (is_unlimited or target_limit > 60) else 15
        api_rows = 30 if (is_unlimited or target_limit > 60) else 18

        req_exts = [e.strip().lower().lstrip(".") for e in (query.file_types or []) if e and e.strip()]
        if req_exts:
            batches: List[Tuple[str, List[str]]] = [(ext, [ext]) for ext in req_exts[:6]]
        else:
            batches = DEFAULT_DORK_BATCHES

        def _fetch_dork_batch(fallback_ext: str, exts: List[str]) -> List[SearchResult]:
            items: List[SearchResult] = []
            if len(exts) == 1:
                dork_q = f"{query.query} filetype:{exts[0]}"
            else:
                or_clause = " OR ".join(f"filetype:{x}" for x in exts)
                dork_q = f"{query.query} ({or_clause})"

            try:
                from ddgs import DDGS
                ddg = DDGS(timeout=min(query.timeout, 7.0))
                raw = ddg.text(dork_q, max_results=dork_max)
                for item in raw or []:
                    href = (item.get("href") or item.get("url") or "").strip()
                    title = (item.get("title") or "").strip()
                    body = (item.get("body") or item.get("snippet") or "").strip()
                    if href and title:
                        ext = infer_extension(href, fallback="")
                        if not ext:
                            title_low = title.lower()
                            for candidate in exts:
                                if re.search(rf"\b{re.escape(candidate)}\b", title_low):
                                    ext = candidate
                                    break
                        ext = ext or fallback_ext
                        items.append(SearchResult(
                            title=f"[{ext.upper()}] {title}",
                            url=href,
                            snippet=body,
                            engine="file_dork",
                            category="files",
                            network="clearnet",
                            score=1.15,
                            metadata={"extension": ext},
                        ))
            except Exception as exc:
                hecos_logger.debug(f"[SEARCH:DORKS] DDGS batch {exts} note: {exc}")

            if not items:
                items = _extract_ddg_html_dork(dork_q, fallback_ext, limit=min(dork_max, 20), timeout=query.timeout)
            return items

        # Build concurrent tasks: always include dork batches + relevant open APIs
        tasks = [lambda fb=fb, ex=ex: _fetch_dork_batch(fb, ex) for fb, ex in batches]
        tasks.append(lambda: fetch_archive_org_files(query.query, rows=api_rows, timeout=query.timeout, file_types=req_exts))

        req_set = set(req_exts)
        if not req_set or (req_set & DOC_EXTS):
            tasks.append(lambda: fetch_openalex_pdfs(query.query, rows=api_rows, timeout=query.timeout))
            tasks.append(lambda: fetch_arxiv_pdfs(query.query, rows=min(api_rows, 20), timeout=query.timeout))
            tasks.append(lambda: fetch_wikimedia_files(query.query, rows=min(api_rows, 20), timeout=query.timeout))
        if not req_set or (req_set & DATA_EXTS):
            tasks.append(lambda: fetch_huggingface_datasets(query.query, rows=min(api_rows, 20), timeout=query.timeout))
        if not req_set or (req_set & (CODE_EXTS | ARCHIVE_EXTS)):
            tasks.append(lambda: fetch_github_repos(query.query, rows=min(api_rows, 20), timeout=query.timeout))
        if not req_set or (req_set & CODE_EXTS):
            tasks.append(lambda: fetch_npm_packages(query.query, rows=min(api_rows, 15), timeout=query.timeout))

        try:
            with ThreadPoolExecutor(max_workers=min(len(tasks), 10)) as executor:
                futures = [executor.submit(fn) for fn in tasks]
                for fut in as_completed(futures, timeout=max(float(query.timeout or 12.0), 8.0)):
                    try:
                        for item in fut.result():
                            if item.url and item.url not in seen_urls:
                                seen_urls.add(item.url)
                                results.append(item)
                                if len(results) >= target_limit:
                                    break
                    except Exception:
                        pass
        except Exception as exc:
            hecos_logger.debug(f"[SEARCH:DORKS] Executor wait note: {exc}")

        hecos_logger.info(
            f"[SEARCH:DORKS] Aggregated {len(results)} unique files/docs/datasets/repos for '{query.query}'"
        )
        return results
