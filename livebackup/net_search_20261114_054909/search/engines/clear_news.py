"""
search/engines/clear_news.py
News engine for recent articles and press dispatches.
Aggregates DDGS News (multi-page), Google News RSS, HackerNews RSS, and Reddit RSS
to provide broad, uncensored news coverage from diverse independent sources.
"""
from __future__ import annotations

import time
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
        t_start = time.time()
        results: List[SearchResult] = []
        seen_urls: Set[str] = set()
        is_unlimited = (query.limit is not None and query.limit <= 0)
        target_limit = 100000 if is_unlimited else max(query.limit, 40)
        max_pages = 10 if is_unlimited else min(6, max(2, (target_limit // 25) + 1))

        hecos_logger.info(
            f"[SEARCH:NEWS] Starting news search: '{query.query}' "
            f"(target={'UNLIMITED' if is_unlimited else target_limit}, "
            f"max_pages={max_pages}, safe={query.safe_search})"
        )

        # 1. Multi-page DDGS News (bounded wall-clock budget so slow upstreams never stall search)
        try:
            from ddgs import DDGS
            hecos_logger.info(f"[SEARCH:NEWS] Querying ddgs news multi-page (target={'UNLIMITED' if is_unlimited else target_limit}, max_pages={max_pages}): '{query.query}'...")
            ddg = DDGS(timeout=min(float(query.timeout or 15.0), 8.0))
            start_page = max(1, getattr(query, "page", 1))
            pages_to_fetch = max_pages if start_page == 1 else 2
            empty_pages = 0
            for page_num in range(start_page, start_page + pages_to_fetch):
                if len(results) >= target_limit or (time.time() - t_start) > 14.0:
                    hecos_logger.debug(f"[SEARCH:NEWS] Stopping DDGS news pagination at page {page_num} (elapsed={time.time() - t_start:.1f}s, count={len(results)})")
                    break
                try:
                    raw = ddg.news(query.query, page=page_num, max_results=30, timelimit=query.time_range)
                    if not raw:
                        break
                    added_in_page = 0
                    for item in raw:
                        title = item.get("title", "")
                        url = item.get("url", "")
                        body = item.get("body", "")
                        source = item.get("source", "News")
                        date = item.get("date", "")
                        if title and url and url not in seen_urls:
                            seen_urls.add(url)
                            added_in_page += 1
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
                    if added_in_page == 0:
                        empty_pages += 1
                        if empty_pages >= 2:
                            break
                    else:
                        empty_pages = 0
                except Exception as p_err:
                    hecos_logger.debug(f"[SEARCH:NEWS] DDGS news page {page_num} note: {p_err}")
                    break
            hecos_logger.info(f"[SEARCH:NEWS] DDGS news returned {len(results)} articles in {time.time() - t_start:.2f}s")
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

        # 3. HackerNews RSS (excellent for tech, programming, science topics)
        try:
            encoded_q_hn = urllib.parse.quote(query.query)
            hn_url = f"https://hnrss.org/newest?q={encoded_q_hn}&count=20"
            hecos_logger.debug(f"[SEARCH:NEWS] Fetching HackerNews RSS for '{query.query}'...")
            resp_hn = http_client.get(hn_url, network="clearnet", timeout=min(query.timeout, 5.0))
            if resp_hn.status_code == 200:
                from bs4 import BeautifulSoup
                soup_hn = BeautifulSoup(resp_hn.content, "xml")
                hn_added = 0
                for it in soup_hn.find_all("item"):
                    if len(results) >= target_limit:
                        break
                    t_tag = it.find("title")
                    l_tag = it.find("link")
                    d_tag = it.find("description")
                    pub_tag = it.find("pubDate")
                    if t_tag and l_tag:
                        u = l_tag.get_text(strip=True)
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            results.append(SearchResult(
                                title=t_tag.get_text(strip=True),
                                url=u,
                                snippet=f"[HackerNews] {d_tag.get_text(strip=True)[:300] if d_tag else ''}",
                                engine="rss:hackernews",
                                category="news",
                                network="clearnet",
                                metadata={"date": pub_tag.get_text(strip=True) if pub_tag else "", "source": "HackerNews"}
                            ))
                            hn_added += 1
                hecos_logger.debug(f"[SEARCH:NEWS] HackerNews RSS added {hn_added} articles")
        except Exception as e:
            hecos_logger.debug(f"[SEARCH:NEWS] HackerNews RSS failed: {e}")

        # 4. Reddit RSS (community discussions and breaking news)
        try:
            encoded_q_rd = urllib.parse.quote(query.query)
            rd_url = f"https://www.reddit.com/search.rss?q={encoded_q_rd}&sort=new&limit=25"
            hecos_logger.debug(f"[SEARCH:NEWS] Fetching Reddit RSS for '{query.query}'...")
            resp_rd = http_client.get(rd_url, network="clearnet", timeout=min(query.timeout, 5.0))
            if resp_rd.status_code == 200:
                from bs4 import BeautifulSoup
                soup_rd = BeautifulSoup(resp_rd.content, "xml")
                rd_added = 0
                for entry in soup_rd.find_all("entry"):
                    if len(results) >= target_limit:
                        break
                    title_tag = entry.find("title")
                    link_tag = entry.find("link")
                    summary_tag = entry.find("summary") or entry.find("content")
                    updated_tag = entry.find("updated")
                    if title_tag and link_tag:
                        u = link_tag.get("href", "") or link_tag.get_text(strip=True)
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            snippet_text = summary_tag.get_text(strip=True)[:300] if summary_tag else ""
                            results.append(SearchResult(
                                title=title_tag.get_text(strip=True),
                                url=u,
                                snippet=f"[Reddit] {snippet_text}",
                                engine="rss:reddit",
                                category="news",
                                network="clearnet",
                                metadata={
                                    "date": updated_tag.get_text(strip=True) if updated_tag else "",
                                    "source": "Reddit"
                                }
                            ))
                            rd_added += 1
                hecos_logger.debug(f"[SEARCH:NEWS] Reddit RSS added {rd_added} posts")
        except Exception as e:
            hecos_logger.debug(f"[SEARCH:NEWS] Reddit RSS failed: {e}")

        hecos_logger.info(f"[SEARCH:NEWS] FINAL: {len(results)} total news articles for '{query.query}'")
        return results
