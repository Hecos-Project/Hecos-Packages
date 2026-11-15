"""
search/engines/domain_directory.py
Indexed Domain Directory engine for Hecos Deep Search.
Queries high-volume SQLite domain compilations (role='directory') matched to query tokens,
runs multi-domain `site:` dork fan-out across DuckDuckGo / SearXNG, and executes bounded
concurrent HTTP probes against top matched niche domains to surface real pages and videos.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Set

from bs4 import BeautifulSoup

from .base import BaseEngine
from .. import http_client
from ..config import get_search_config
from ..models import SearchQuery, SearchResult

try:
    from hecos.modules.net_search.search.sources.domain_store import (
        _get_db_path,
        query_matching_domains,
    )
except (ImportError, ValueError):
    from ..sources.domain_store import _get_db_path, query_matching_domains

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.domain_directory")
logger = hecos_logger


_SKIP_LINK_TOKENS = (
    "login", "signin", "sign-in", "signup", "sign-up", "register",
    "privacy", "terms", "tos", "dmca", "2257", "cookie", "contact",
    "support", "faq", "about", "advertise", "affiliate", "javascript:",
    "mailto:", "webmaster", "report", "feedback",
)

_PARKED_MARKERS = (
    "domain is for sale",
    "buy this domain",
    "parked domain",
    "hugedomains",
    "sedo.com",
    "dan.com",
    "godaddy",
    "just a moment...",
    "attention required! | cloudflare",
    "access denied",
)


def _extract_tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-zA-Z0-9]{3,}", (text or "").lower())]


def _is_video_like(url: str, title: str, thumb: str, mode: str) -> bool:
    if mode in ("media", "videos"):
        return True
    low = f"{url} {title}".lower()
    if thumb:
        return True
    return any(tok in low for tok in ("/video", "/videos", "/watch", "tube", "clip", "porn", "xxx", "cam", "movie", ".mp4"))


class DomainDirectoryEngine(BaseEngine):
    """Searches active indexed domain directories (`role='directory'`) via dorks & concurrent HTTP probes."""

    def __init__(self):
        super().__init__(
            engine_id="domain_directory",
            name="Indexed Domain Directory",
            category="general",
            network="clearnet",
            priority=78,
        )

    def is_available(self) -> bool:
        try:
            db_path = _get_db_path()
            if not os.path.isfile(db_path):
                return False
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
            try:
                row = conn.execute(
                    """
                    SELECT 1 FROM domain_entries de
                    LEFT JOIN domain_sources ds ON ds.source_id = de.source_id
                    WHERE de.role = 'directory' AND COALESCE(ds.enabled, 1) = 1
                    LIMIT 1
                    """
                ).fetchone()
                return row is not None
            finally:
                conn.close()
        except Exception:
            return False

    def _probe_single_domain(
        self,
        domain: str,
        raw_query: str,
        tokens: List[str],
        mode: str,
        timeout: float,
    ) -> List[SearchResult]:
        """Fetches search/landing HTML on a matched domain and extracts live page/video links."""
        out: List[SearchResult] = []
        q_plus = urllib.parse.quote_plus(raw_query)
        probe_urls = [f"https://{domain}/?s={q_plus}", f"https://{domain}/"]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        resp_text = ""
        final_url = ""
        per_req_timeout = min(max(timeout, 2.0), 4.0)

        for target_url in probe_urls:
            try:
                resp = http_client.get(target_url, network="clearnet", headers=headers, timeout=per_req_timeout)
                if resp.status_code == 200 and resp.text and len(resp.text) > 300:
                    low_body = resp.text[:4000].lower()
                    if any(marker in low_body for marker in _PARKED_MARKERS):
                        return []
                    resp_text = resp.text
                    final_url = getattr(resp, "url", "") or target_url
                    break
            except Exception:
                continue

        if not resp_text:
            return []

        try:
            soup = BeautifulSoup(resp_text, "lxml")
            page_title = (soup.title.string or "").strip() if soup.title and soup.title.string else domain
            page_title_low = page_title.lower()
            if any(marker in page_title_low for marker in _PARKED_MARKERS):
                return []

            base_host = (urllib.parse.urlsplit(final_url).hostname or domain).lower().lstrip("www.")
            seen_hrefs: Set[str] = set()
            candidates: List[SearchResult] = []

            for a in soup.find_all("a", href=True):
                href = str(a.get("href") or "").strip()
                if not href or href.startswith(("#", "javascript:", "mailto:")):
                    continue
                low_href = href.lower()
                if any(bad in low_href for bad in _SKIP_LINK_TOKENS):
                    continue

                abs_url = urllib.parse.urljoin(final_url, href)
                parsed = urllib.parse.urlsplit(abs_url)
                if parsed.scheme not in ("http", "https"):
                    continue
                link_host = (parsed.hostname or "").lower().lstrip("www.")
                if base_host not in link_host and link_host not in base_host:
                    continue
                # Skip root/pagination-only links
                if parsed.path in ("", "/") and not parsed.query:
                    continue
                if abs_url in seen_hrefs:
                    continue
                seen_hrefs.add(abs_url)

                img = a.find("img")
                thumb = ""
                img_alt = ""
                if img:
                    thumb = str(
                        img.get("data-src")
                        or img.get("data-original")
                        or img.get("data-lazy-src")
                        or img.get("src")
                        or ""
                    ).strip()
                    if thumb and not thumb.startswith(("http://", "https://", "data:")):
                        thumb = urllib.parse.urljoin(final_url, thumb)
                    if thumb.startswith("data:"):
                        thumb = ""
                    img_alt = str(img.get("alt") or img.get("title") or "").strip()

                text = a.get_text(" ", strip=True)
                title = text or str(a.get("title") or "").strip() or img_alt
                if not title or len(title) < 6:
                    continue
                low_title = title.lower()
                if any(bad in low_title for bad in _SKIP_LINK_TOKENS):
                    continue

                token_hits = sum(1 for t in tokens if t in low_title or t in low_href)
                # Keep items that match query tokens OR look like concrete content/video cards with thumbnails
                if token_hits == 0 and not (thumb and len(parsed.path.strip("/")) >= 4):
                    continue

                is_vid = _is_video_like(abs_url, title, thumb, mode)
                score = 1.25 + (0.25 * token_hits) + (0.15 if thumb else 0.0)
                candidates.append(SearchResult(
                    title=title[:180],
                    url=abs_url,
                    snippet=f"Directory Probe: {domain} | {page_title[:90]}",
                    engine="domain_directory:probe",
                    category="videos" if is_vid else "general",
                    network="clearnet",
                    score=round(score, 3),
                    media_url=abs_url if is_vid else "",
                    thumbnail_url=thumb,
                    metadata={"directory_domain": domain, "token_hits": token_hits},
                ))

            # Best matching/thumbnail links first, max 10 per domain
            candidates.sort(key=lambda r: r.score, reverse=True)
            out.extend(candidates[:10])
        except Exception as e:
            logger.debug(f"[DomainDirectory:Probe] Parse failed for {domain}: {e}")
        return out

    def _dork_batch_ddgs(
        self,
        domains: List[str],
        raw_query: str,
        safe_search: bool,
        mode: str,
        timeout: float,
    ) -> List[SearchResult]:
        """Executes a `site:d1 OR site:d2 ... <query>` search via DDGS."""
        if not domains:
            return []
        site_clause = " OR ".join(f"site:{d}" for d in domains)
        dork_q = f"({site_clause}) {raw_query}"
        out: List[SearchResult] = []
        try:
            from ddgs import DDGS
            ddg = DDGS(timeout=min(max(timeout, 3.0), 6.0))
            raw = ddg.text(
                dork_q,
                max_results=30,
                safesearch="moderate" if safe_search else "off",
            ) or []
            for item in raw:
                href = item.get("href", "") or item.get("url", "")
                title = item.get("title", "")
                body = item.get("body", "") or item.get("snippet", "")
                if not href or not title:
                    continue
                is_vid = _is_video_like(href, title, "", mode)
                out.append(SearchResult(
                    title=title,
                    url=href,
                    snippet=f"[Directory Dork] {body}" if body else "[Directory Dork] Indexed directory match",
                    engine="domain_directory:dork",
                    category="videos" if is_vid else "general",
                    network="clearnet",
                    score=1.45,
                    media_url=href if is_vid else "",
                    metadata={"dork_domains": domains},
                ))
        except Exception as e:
            logger.debug(f"[DomainDirectory:DDGS] Batch dork failed: {e}")
        return out

    def _dork_batch_searxng(
        self,
        domains: List[str],
        raw_query: str,
        safe_search: bool,
        mode: str,
        timeout: float,
        local_only: bool = False,
    ) -> List[SearchResult]:
        """Executes a `site:` batch query against local/configured SearXNG."""
        if not domains:
            return []
        site_clause = " OR ".join(f"site:{d}" for d in domains)
        dork_q = f"({site_clause}) {raw_query}"
        out: List[SearchResult] = []
        try:
            from .clear_searxng import _get_configured_searxng_nodes
            nodes = _get_configured_searxng_nodes() or [{"url": "http://127.0.0.1:8889", "use_api_key": False, "api_key": ""}]
            if local_only:
                nodes = [n for n in nodes if "127.0.0.1" in n["url"] or "localhost" in n["url"]]
            for node in nodes[:2]:
                params = {
                    "q": dork_q,
                    "format": "json",
                    "safesearch": "1" if safe_search else "0",
                }
                req_url = f"{node['url'].rstrip('/')}/search?{urllib.parse.urlencode(params)}"
                headers = {"User-Agent": "Hecos-Search/1.0"}
                if node.get("use_api_key") and node.get("api_key"):
                    headers["X-API-Key"] = node["api_key"]
                try:
                    resp = http_client.get(req_url, network="clearnet", headers=headers, timeout=min(max(timeout, 3.0), 5.0))
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for item in (data.get("results") or [])[:35]:
                        href = item.get("url") or ""
                        title = item.get("title") or href
                        thumb = item.get("thumbnail_src") or item.get("img_src") or item.get("thumbnail") or ""
                        if not href:
                            continue
                        is_vid = _is_video_like(href, title, thumb, mode)
                        out.append(SearchResult(
                            title=title,
                            url=href,
                            snippet=f"[Directory Dork:SearXNG] {item.get('content', '')}".strip(),
                            engine="domain_directory:searxng",
                            category="videos" if is_vid else "general",
                            network="clearnet",
                            score=1.45,
                            media_url=href if is_vid else "",
                            thumbnail_url=thumb,
                            metadata={"dork_domains": domains},
                        ))
                    if out:
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[DomainDirectory:SearXNG] Batch dork failed: {e}")
        return out

    def search(self, query: SearchQuery) -> List[SearchResult]:
        cfg = get_search_config()
        is_local_only = (
            query.local_only
            if getattr(query, "local_only", None) is not None
            else bool(cfg.get("local_only", False))
        )
        safe_search = bool(query.safe_search)
        tokens = _extract_tokens(query.query)
        if not tokens:
            return []

        q_page = max(1, getattr(query, "page", 1))
        fetch_limit = min(48 * q_page, 192)
        all_matched = query_matching_domains(tokens, role="directory", limit=fetch_limit)
        if safe_search:
            all_matched = [m for m in all_matched if m.get("category") != "adult"]
        offset = (q_page - 1) * 24
        matched = all_matched[offset : offset + 48]
        if not matched and all_matched:
            matched = all_matched[-min(24, len(all_matched)):]
        if not matched:
            return []

        domains = [m["domain"] for m in matched]
        results: List[SearchResult] = []
        seen_urls: Set[str] = set()

        def _append_unique(items: List[SearchResult]) -> None:
            for it in items:
                if it.url and it.url not in seen_urls:
                    seen_urls.add(it.url)
                    results.append(it)

        # Stage 1 & Stage 2 run in parallel for speed (<8s wall clock)
        futures = []
        dork_batches = [domains[i : i + 6] for i in range(0, min(len(domains), 24), 6)]
        probe_targets = domains[:16]

        with ThreadPoolExecutor(max_workers=16) as pool:
            if not is_local_only:
                for dom in probe_targets:
                    futures.append(
                        pool.submit(self._probe_single_domain, dom, query.query, tokens, query.mode, query.timeout)
                    )
                for batch in dork_batches:
                    futures.append(
                        pool.submit(self._dork_batch_ddgs, batch, query.query, safe_search, query.mode, query.timeout)
                    )
            for batch in dork_batches[:2]:
                futures.append(
                    pool.submit(
                        self._dork_batch_searxng,
                        batch,
                        query.query,
                        safe_search,
                        query.mode,
                        query.timeout,
                        is_local_only,
                    )
                )

            for fut in as_completed(futures):
                try:
                    _append_unique(fut.result() or [])
                except Exception as fe:
                    logger.debug(f"[DomainDirectory] Worker error: {fe}")

        # Stage 3: Surface top matched niche directory sites as direct searchable entry points
        q_plus = urllib.parse.quote_plus(query.query)
        for idx, m in enumerate(matched[:20]):
            dom = m["domain"]
            mt = m.get("matched_tokens") or []
            if not mt:
                continue
            search_url = f"https://{dom}/?s={q_plus}"
            if search_url not in seen_urls:
                seen_urls.add(search_url)
                is_vid = _is_video_like(search_url, dom, "", query.mode) or m.get("category") == "adult"
                results.append(SearchResult(
                    title=f"{dom} — Search '{query.query}' ({', '.join(mt)})",
                    url=search_url,
                    snippet=f"Indexed Directory Match ({m.get('category', 'general')}) | Score: {m.get('score', 0)}",
                    engine="domain_directory:index",
                    category="videos" if is_vid else "general",
                    network="clearnet",
                    score=round(0.95 - (idx * 0.02), 3),
                    media_url=search_url if is_vid else "",
                    metadata={"directory_domain": dom, "matched_tokens": mt, "directory_score": m.get("score", 0)},
                ))

        hecos_logger.info(
            f"[DomainDirectory] Matched {len(matched)} indexed domains for '{query.query}' -> yielded {len(results)} results"
        )
        return results

