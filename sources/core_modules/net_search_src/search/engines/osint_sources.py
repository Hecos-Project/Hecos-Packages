"""
search/engines/osint_sources.py
Deep OSINT Sources Engine: People/Social Dorks + Zero-Key Identity APIs.
Mirrors `files_dorks.py` for OSINT Hunt: combines multi-platform profile dorking
(LinkedIn, X/Twitter, Instagram, Facebook, TikTok, YouTube, GitHub, Reddit, Bio/Records)
with concurrent open-API lookups in `osint_apis.py`.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Tuple

from .base import BaseEngine
from .osint_apis import (
    classify_osint_group,
    fetch_archive_org_osint,
    fetch_crtsh_osint,
    fetch_github_osint,
    fetch_gitlab_osint,
    fetch_gravatar_osint,
    fetch_hackernews_osint,
    fetch_keybase_osint,
    fetch_reddit_osint,
    fetch_wikidata_osint,
    fetch_wikipedia_osint,
    parse_osint_input,
)
from .. import http_client
from ..config import get_search_config
from ..models import SearchQuery, SearchResult

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.osint_sources")

OSINT_DORK_BATCHES: List[Tuple[str, str]] = [
    (
        "social",
        "site:linkedin.com/in OR site:facebook.com OR site:instagram.com OR site:x.com OR site:twitter.com OR site:tiktok.com OR site:threads.net OR site:bsky.app",
    ),
    (
        "dev",
        "site:github.com OR site:gitlab.com OR site:stackoverflow.com OR site:dev.to OR site:huggingface.co OR site:keybase.io OR site:reddit.com/user",
    ),
    (
        "records",
        "site:youtube.com OR site:medium.com OR site:substack.com OR site:about.me OR site:linktr.ee OR site:pinterest.com OR site:wikipedia.org OR site:imdb.com",
    ),
]


def _extract_ddg_html_osint(dork_query: str, group_hint: str, limit: int, timeout: float) -> List[SearchResult]:
    """Direct HTML DuckDuckGo fallback using Hecos http_client when DDGS is rate-limited."""
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
            osint_group = classify_osint_group(href, title=title) or group_hint
            items.append(SearchResult(
                title=title,
                url=href,
                snippet=(s_tag.get_text(" ", strip=True) if s_tag else ""),
                engine="osint:dork_html",
                category="osint",
                network="clearnet",
                score=1.15,
                metadata={"osint_group": osint_group},
            ))
            if len(items) >= limit:
                break
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:OSINT_DORKS] DDG HTML fallback note: {exc}")
    return items


class OsintSourcesEngine(BaseEngine):
    """OSINT engine combining profile dorking across social/dev/records and open OSINT APIs."""

    def __init__(self):
        super().__init__(
            engine_id="osint_sources",
            name="OSINT People & Profile APIs",
            category="osint",
            network="clearnet",
            priority=94,
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
            hecos_logger.info("[SEARCH:OSINT] Privacy Shield local_only active — skipping external OSINT APIs & dorks.")
            return []

        raw_q = (query.target_username or query.query or "").strip()
        if not raw_q:
            return []

        parsed = parse_osint_input(raw_q)
        search_expr = f'"{parsed["clean"]}"' if parsed["kind"] == "person" else parsed["clean"]
        is_unlimited = query.limit is not None and query.limit <= 0
        target_limit = 100000 if is_unlimited else max(query.limit or 50, 80)
        dork_max = 30 if (is_unlimited or target_limit > 60) else 15
        api_rows = 20 if (is_unlimited or target_limit > 60) else 12

        results: List[SearchResult] = []
        seen_urls: Set[str] = set()

        def _run_dork_batch(group_hint: str, sites_clause: str) -> List[SearchResult]:
            dork_q = f"{search_expr} ({sites_clause})"
            items: List[SearchResult] = []
            try:
                from ddgs import DDGS
                ddg = DDGS(timeout=min(query.timeout, 7.0))
                raw = ddg.text(dork_q, max_results=dork_max, timelimit=query.time_range)
                for item in raw or []:
                    href = (item.get("href") or item.get("url") or "").strip()
                    title = (item.get("title") or "").strip()
                    body = (item.get("body") or item.get("snippet") or "").strip()
                    if href and title:
                        grp = classify_osint_group(href, title=title) or group_hint
                        items.append(SearchResult(
                            title=title,
                            url=href,
                            snippet=body,
                            engine="osint:dork",
                            category="osint",
                            network="clearnet",
                            score=1.25,
                            metadata={"osint_group": grp},
                        ))
            except Exception as exc:
                hecos_logger.debug(f"[SEARCH:OSINT] DDGS dork batch ({group_hint}) note: {exc}")

            if not items:
                items = _extract_ddg_html_osint(dork_q, group_hint, limit=min(dork_max, 20), timeout=query.timeout)
            return items

        src_flags = cfg.get("osint", {}).get("sources", {}) or {}
        src_on = lambda k: src_flags.get(k, True) is not False

        api_query = parsed["clean"]
        primary_variant = parsed["variants"][0] if parsed["variants"] else api_query
        tasks = []

        if src_on("people_dorks"):
            tasks.extend(lambda grp=grp, clause=clause: _run_dork_batch(grp, clause) for grp, clause in OSINT_DORK_BATCHES)
        if src_on("github"):
            tasks.append(lambda: fetch_github_osint(api_query, rows=api_rows, timeout=query.timeout))
        if src_on("gitlab"):
            tasks.append(lambda: fetch_gitlab_osint(api_query, rows=min(api_rows, 15), timeout=query.timeout))
        if src_on("reddit"):
            tasks.append(lambda: fetch_reddit_osint(api_query, rows=min(api_rows, 15), timeout=query.timeout))
        if src_on("hackernews"):
            tasks.append(lambda: fetch_hackernews_osint(api_query, rows=min(api_rows, 15), timeout=query.timeout))
        if src_on("wikipedia"):
            tasks.append(lambda: fetch_wikipedia_osint(api_query, rows=10, timeout=query.timeout))
        if src_on("wikidata"):
            tasks.append(lambda: fetch_wikidata_osint(api_query, rows=10, timeout=query.timeout))
        if src_on("keybase"):
            tasks.append(lambda: fetch_keybase_osint(primary_variant, rows=10, timeout=query.timeout))
        if src_on("archive_org"):
            tasks.append(lambda: fetch_archive_org_osint(api_query, rows=min(api_rows, 15), timeout=query.timeout))
        if src_on("gravatar") and parsed.get("email"):
            tasks.append(lambda: fetch_gravatar_osint(parsed["email"], timeout=query.timeout))
        if src_on("crtsh") and parsed.get("domain"):
            tasks.append(lambda: fetch_crtsh_osint(parsed["domain"], rows=min(api_rows, 20), timeout=query.timeout))

        if not tasks:
            return []

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
            hecos_logger.debug(f"[SEARCH:OSINT] Executor wait note: {exc}")

        hecos_logger.info(
            f"[SEARCH:OSINT] Aggregated {len(results)} unique OSINT profiles/mentions for '{raw_q}'"
        )
        return results

