"""
search/engines/clear_news.py
News engine for recent articles and press dispatches.
Aggregates DDGS News multi-page with Google News RSS to provide deep coverage.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import List, Set

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.news")

from .base import BaseEngine
from ..models import SearchQuery, SearchResult
from .. import http_client


class ClearNewsEngine(BaseEngine):
    """News search engine."""

    def __init__(self):
        super().__init__(
            engine_id="clear_news",
            name="Global News Feed",
            category="news",
            network="clearnet",
            priority=80
        )

    def is_available(self) -> bool:
        return True

    def search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen_urls: Set[str] = set()
        is_unlimited = (query.limit is not None and query.limit <= 0)
        target_limit = 100000 if is_unlimited else max(query.limit, 40)
        max_pages = 25 if is_unlimited else min(25, max(4, (target_limit // 25) + 1))

        # 1. Multi-page DDGS News
        try:
            from ddgs import DDGS
            hecos_logger.info(f"[SEARCH:NEWS] Querying ddgs news multi-page (target={'UNLIMITED' if is_unlimited else target_limit}, max_pages={max_pages}): '{query.query}'...")
            ddg = DDGS(timeout=query.timeout)
            for page_num in range(1, max_pages + 1):
                if len(results) >= target_limit:
                    break
                try:
                    raw = ddg.news(query.query, page=page_num, max_results=30, timelimit=query.time_range)
                    if not raw:
                        break
                    for item in raw:
                        title = item.get("title", "")
                        url = item.get("url", "")
                        body = item.get("body", "")
                        source = item.get("source", "News")
                        date = item.get("date", "")
                        if title and url and url not in seen_urls:
                            seen_urls.add(url)
                            results.append(SearchResult(
                                title=title,
                                url=url,
                                snippet=f"[{source}] {body} ({date})" if date else f"[{source}] {body}",
                                engine="ddgs:news",
                                category="news",
                                network="clearnet",
                                metadata={"source": source, "date": date}
                            ))
                            if len(results) >= target_limit:
                                break
                except Exception as p_err:
                    hecos_logger.debug(f"[SEARCH:NEWS] DDGS news page {page_num} note: {p_err}")
                    break
            hecos_logger.info(f"[SEARCH:NEWS] DDGS news returned {len(results)} articles")
        except Exception as e:
            hecos_logger.debug(f"[SEARCH:NEWS] DDGS news query failed: {e}")

        # 2. Google News RSS Feed (Aggregated to guarantee deep news coverage)
        try:
            hecos_logger.info(f"[SEARCH:NEWS] Fetching Google News RSS for '{query.query}'...")
            encoded_q = urllib.parse.quote(query.query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"
            resp = http_client.get(rss_url, network="clearnet", timeout=query.timeout)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.content, "xml")
                items = soup.find_all("item")
                for it in items:
                    if len(results) >= target_limit:
                        break
                    t = it.find("title")
                    l = it.find("link")
                    d = it.find("description")
                    pub = it.find("pubDate")
                    if t and l:
                        u = l.get_text(strip=True)
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            snippet_clean = d.get_text(strip=True) if d else ""
                            pub_clean = pub.get_text(strip=True) if pub else ""
                            results.append(SearchResult(
                                title=t.get_text(strip=True),
                                url=u,
                                snippet=f"{snippet_clean} ({pub_clean})" if pub_clean else snippet_clean,
                                engine="rss:google_news",
                                category="news",
                                network="clearnet",
                                metadata={"date": pub_clean}
                            ))
                hecos_logger.info(f"[SEARCH:NEWS] Total combined news articles: {len(results)}")
        except Exception as e:
            hecos_logger.error(f"[SEARCH:NEWS] RSS news fetch failed: {e}")

        return results
