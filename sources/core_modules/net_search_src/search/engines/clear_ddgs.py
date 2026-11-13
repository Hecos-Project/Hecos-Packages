"""
search/engines/clear_ddgs.py
Multi-backend Clear Web metasearch engine with multi-page pagination.
Paginates through search providers (Startpage/Google, Bing, Yahoo, DuckDuckGo)
to retrieve abundant results (50-100+) without artificial limits.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import List, Set

from .base import BaseEngine
from .osint_apis import classify_osint_group
from ..models import SearchQuery, SearchResult
from .. import http_client

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.ddgs")


class ClearDdgsEngine(BaseEngine):
    """Multi-backend clearnet search engine with multi-page pagination."""

    def __init__(self):
        super().__init__(
            engine_id="clear_ddgs",
            name="Multi-Engine ClearWeb (Google/Bing/Brave)",
            category="general",
            network="clearnet",
            priority=100
        )

    def is_available(self) -> bool:
        return True

    def search(self, query: SearchQuery) -> List[SearchResult]:
        import time
        t0 = time.time()
        results: List[SearchResult] = []
        seen_urls: Set[str] = set()
        is_unlimited = (query.limit is not None and query.limit <= 0)
        target_limit = 100000 if is_unlimited else max(query.limit, 40)
        is_files_mode = (getattr(query, "mode", "") or "").lower() == "files"
        is_osint_mode = (getattr(query, "mode", "") or "").lower() == "osint"
        res_category = "files" if is_files_mode else ("osint" if is_osint_mode else "general")
        raw_q = (query.query or "").strip()
        ddg_search_q = raw_q
        if is_files_mode and raw_q and "filetype:" not in raw_q.lower() and "ext:" not in raw_q.lower():
            file_types = [str(ft).strip().lstrip(".").lower() for ft in (getattr(query, "file_types", None) or []) if str(ft).strip()]
            if file_types:
                ext_clause = " OR ".join(f"filetype:{ft}" for ft in file_types[:6])
            else:
                ext_clause = "filetype:pdf OR filetype:zip OR filetype:csv OR filetype:sql OR filetype:docx OR filetype:py"
            ddg_search_q = f"{raw_q} ({ext_clause})"

        hecos_logger.info(f"[SEARCH:DDGS] Starting multi-backend clear search ({'files' if is_files_mode else 'general'}): '{ddg_search_q}' (target={target_limit}, safe={query.safe_search})")
        safesearch_val = "off" if not query.safe_search else "moderate"
        per_timeout = min(query.timeout, 6.0)

        # 1. Multi-Page querying via ddgs library (bounded to max 3 pages / 8s to prevent UI freeze)
        try:
            from ddgs import DDGS
            ddg = DDGS(timeout=per_timeout)
            start_page = max(1, getattr(query, "page", 1))
            pages_to_fetch = 5 if start_page == 1 else 3
            hecos_logger.info(f"[SEARCH:DDGS] Querying via ddgs multi-page (start={start_page}, pages={pages_to_fetch}, timeout={per_timeout}s): '{ddg_search_q}'...")

            for page_num in range(start_page, start_page + pages_to_fetch):
                if len(results) >= target_limit or (time.time() - t0 > 15.0):
                    break
                try:
                    raw = ddg.text(
                        ddg_search_q,
                        page=page_num,
                        max_results=50,
                        safesearch=safesearch_val,
                        timelimit=query.time_range
                    )
                    if not raw:
                        break
                    page_added = 0
                    for item in raw:
                        title = item.get("title", "")
                        href = item.get("href", "") or item.get("url", "")
                        body = item.get("body", "") or item.get("snippet", "")
                        if title and href and href not in seen_urls:
                            seen_urls.add(href)
                            results.append(SearchResult(
                                title=title,
                                url=href,
                                snippet=body,
                                engine="ddgs",
                                category=res_category,
                                network="clearnet",
                                metadata={"osint_group": classify_osint_group(href, "ddgs", title)} if is_osint_mode else {}
                            ))
                            page_added += 1
                            if len(results) >= target_limit:
                                break
                    hecos_logger.debug(f"[SEARCH:DDGS] Page {page_num} yielded {page_added} new results (total: {len(results)})")
                    if page_added == 0:
                        break
                except Exception as p_err:
                    hecos_logger.debug(f"[SEARCH:DDGS] Page {page_num} stopped: {p_err}")
                    break

            if results:
                hecos_logger.info(f"[SEARCH:DDGS] Multi-page ddgs returned {len(results)} results")
                return results
        except ImportError:
            hecos_logger.debug("[SEARCH:DDGS] ddgs package not installed, using autonomous HTTP fallback.")
        except Exception as e:
            hecos_logger.warning(f"[SEARCH:DDGS] ddgs query failed: {e}. Falling back to direct HTTP.")

        # 2. Autonomous HTTP Fallback with multi-page loop
        try:
            hecos_logger.info(f"[SEARCH:DDGS] Querying via direct HTTP scraper: '{ddg_search_q}'...")
            url = "https://html.duckduckgo.com/html/"
            data = {"q": ddg_search_q, "b": ""}
            if not query.safe_search:
                data["kp"] = "-2"  # SafeSearch off

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0",
                "Referer": "https://html.duckduckgo.com/",
                "Origin": "https://html.duckduckgo.com",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            if results: return results
            for _page in range(1, 4):
                if len(results) >= target_limit:
                    break
                resp = http_client.post(url, network="clearnet", data=data, headers=headers, timeout=min(query.timeout, 3.5))
                if resp.status_code != 200:
                    break

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")
                result_nodes = soup.find_all("div", class_="result")
                page_added = 0

                for node in result_nodes:
                    if len(results) >= target_limit:
                        break
                    if "result--ad" in node.get("class", []):
                        continue

                    title_tag = node.find("a", class_="result__a")
                    snippet_tag = node.find("a", class_="result__snippet")

                    if title_tag:
                        raw_href = title_tag.get("href", "")
                        if "uddg=" in raw_href:
                            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                            final_url = parsed.get("uddg", [raw_href])[0]
                        else:
                            final_url = raw_href

                        title = title_tag.get_text(strip=True)
                        snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

                        if title and final_url.startswith("http") and final_url not in seen_urls:
                            seen_urls.add(final_url)
                            results.append(SearchResult(
                                title=title,
                                url=final_url,
                                snippet=snippet,
                                engine="clearnet_http",
                                category=res_category,
                                network="clearnet",
                                metadata={"osint_group": classify_osint_group(final_url, "ddgs", title)} if is_osint_mode else {}
                            ))
                            page_added += 1

                # Form pagination for next page
                next_form = None
                for f in soup.find_all("form"):
                    if f.get("action") == "/html/":
                        inps = {i.get("name"): i.get("value") for i in f.find_all("input") if i.get("name")}
                        if "s" in inps and "vqd" in inps:
                            next_form = inps
                            break
                if not next_form or page_added == 0:
                    break
                data = next_form

            hecos_logger.info(f"[SEARCH:DDGS] Direct HTTP scraper returned {len(results)} results")
        except Exception as e:
            hecos_logger.error(f"[SEARCH:DDGS] HTTP fallback failed: {e}")

        hecos_logger.info(f"[SEARCH:DDGS] Completed: {len(results)} results for '{query.query}'")
        return results
