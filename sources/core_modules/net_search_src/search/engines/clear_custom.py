"""
search/engines/clear_custom.py
Custom Clearnet Web & OpenSearch Engines runner for Hecos Deep Search.
Executes queries against imported or user-defined Clearnet endpoints supporting `{q}` / OpenSearch templates.
"""
from __future__ import annotations

import html as _html
import logging
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from bs4 import BeautifulSoup

from .base import BaseEngine
from .files_apis import infer_extension
from .. import http_client
from ..config import build_endpoint_url, get_search_config
from ..models import SearchQuery, SearchResult

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.clear_custom")


def _is_local_host(url: str) -> bool:
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        return host in ("127.0.0.1", "localhost", "::1") or host.startswith(("192.168.", "10."))
    except Exception:
        return False


def _extract_json_results(
    data: Any, eng_name: str, base_url: str, limit: int, category: str = "general", prefix: str = "clear"
) -> List[SearchResult]:
    results: List[SearchResult] = []
    eng_id = f"{prefix}_{eng_name.lower().replace(' ', '_')}"
    # MediaWiki OpenSearch JSON: [query, [titles], [descriptions], [urls]]
    if isinstance(data, list) and len(data) >= 4 and isinstance(data[1], list) and isinstance(data[3], list):
        titles = data[1]
        descs = data[2] if isinstance(data[2], list) else []
        urls = data[3]
        for idx, href in enumerate(urls[:limit]):
            if isinstance(href, str) and href.startswith(("http://", "https://")):
                title = str(titles[idx]) if idx < len(titles) else href
                snippet = str(descs[idx]) if idx < len(descs) else ""
                results.append(SearchResult(
                    url=href,
                    title=title,
                    snippet=snippet,
                    engine=eng_id,
                    category=category,
                    network="clearnet",
                ))
        return results

    items = []
    if isinstance(data, dict):
        if isinstance(data.get("results"), list):
            items = data["results"]
        elif isinstance(data.get("items"), list):
            items = data["items"]
        elif isinstance(data.get("data"), list):
            items = data["data"]
        elif isinstance(data.get("docs"), list):
            items = data["docs"]
        elif isinstance(data.get("response"), dict) and isinstance(data["response"].get("docs"), list):
            items = data["response"]["docs"]
    elif isinstance(data, list):
        items = [x for x in data if isinstance(x, dict)]

    for it in items[:limit]:
        if not isinstance(it, dict):
            continue
        oa_best = it.get("best_oa_location") if isinstance(it.get("best_oa_location"), dict) else {}
        oa_info = it.get("open_access") if isinstance(it.get("open_access"), dict) else {}
        href = str(
            oa_best.get("pdf_url")
            or oa_info.get("oa_url")
            or it.get("pdf_url")
            or it.get("download_url")
            or it.get("html_url")
            or it.get("url")
            or it.get("link")
            or it.get("href")
            or it.get("id")
            or ""
        ).strip()
        if href and not href.startswith(("http://", "https://", "/")):
            if it.get("identifier"):
                href = f"https://archive.org/details/{it['identifier']}"
            else:
                href = ""
        elif not href and it.get("identifier"):
            href = f"https://archive.org/details/{it['identifier']}"
        if not href:
            continue
        href = urllib.parse.urljoin(base_url, href)
        title = str(it.get("title") or it.get("full_name") or it.get("name") or href).strip()
        snippet = str(it.get("content") or it.get("snippet") or it.get("description") or it.get("summary") or "").strip()
        meta: Dict[str, Any] = {}
        if category == "files":
            ext = infer_extension(href, fallback="")
            if ext:
                meta["extension"] = ext
        results.append(SearchResult(
            url=href,
            title=title,
            snippet=snippet[:400],
            engine=eng_id,
            category=category,
            network="clearnet",
            metadata=meta,
        ))
    return results


def _extract_rss_atom_results(
    xml_text: str, eng_name: str, base_url: str, limit: int, category: str = "general", prefix: str = "clear"
) -> List[SearchResult]:
    """Parses RSS 2.0 (<item>) or Atom (<entry>) XML search feeds."""
    results: List[SearchResult] = []
    eng_id = f"{prefix}_{eng_name.lower().replace(' ', '_')}"
    try:
        root = ET.fromstring(xml_text.strip())
    except Exception:
        return results

    def _strip_ns(tag: str) -> str:
        return tag.split("}", 1)[-1].lower()

    entries = [el for el in root.iter() if _strip_ns(el.tag) in ("item", "entry")]
    for entry in entries[:limit]:
        title = ""
        link = ""
        desc = ""
        for child in entry:
            ctag = _strip_ns(child.tag)
            if ctag == "title" and not title:
                title = (child.text or "").strip()
            elif ctag == "link":
                href_attr = (child.attrib.get("href") or "").strip()
                txt_link = (child.text or "").strip()
                cand = href_attr or txt_link
                if cand and (not link or child.attrib.get("rel", "alternate") == "alternate"):
                    link = cand
            elif ctag == "id" and not link:
                cand_id = (child.text or "").strip()
                if cand_id.startswith(("http://", "https://")):
                    link = cand_id
            elif ctag in ("description", "summary", "content") and not desc:
                desc = (child.text or "").strip()
        if not link:
            continue
        full_url = urllib.parse.urljoin(base_url, link)
        if not full_url.startswith(("http://", "https://")):
            continue
        clean_desc = _html.unescape(BeautifulSoup(desc, "lxml").get_text(" ", strip=True)) if desc else ""
        results.append(SearchResult(
            url=full_url,
            title=(_html.unescape(title) or full_url)[:200],
            snippet=clean_desc[:400],
            engine=eng_id,
            category=category,
            network="clearnet",
        ))
    return results


def _extract_html_results(
    html_text: str, eng_name: str, base_url: str, limit: int, category: str = "general", prefix: str = "clear"
) -> List[SearchResult]:
    results: List[SearchResult] = []
    seen: set[str] = set()
    eng_id = f"{prefix}_{eng_name.lower().replace(' ', '_')}"
    soup = BeautifulSoup(html_text, "lxml")

    # 1. Common structured result containers (including MediaWiki & generic search pages)
    containers = soup.find_all(
        ["div", "li", "article"],
        class_=lambda c: c and any(k in str(c).lower() for k in ["result", "mw-search-result", "search-item", "gsc-webresult"]),
    )
    for box in containers:
        a_tag = box.find("a", href=True)
        if not a_tag:
            continue
        href = urllib.parse.urljoin(base_url, str(a_tag["href"]).strip())
        if not href.startswith(("http://", "https://")) or href in seen:
            continue
        title = a_tag.get_text(" ", strip=True)
        if not title or len(title) < 2:
            continue
        p_tag = box.find(["p", "div", "span"], class_=lambda c: c and any(k in str(c).lower() for k in ["snippet", "desc", "searchresult", "summary"]))
        snippet = p_tag.get_text(" ", strip=True) if p_tag else ""
        seen.add(href)
        results.append(SearchResult(
            url=href,
            title=title[:200],
            snippet=snippet[:400],
            engine=eng_id,
            category=category,
            network="clearnet",
        ))
        if len(results) >= limit:
            return results

    # 2. Fallback to meaningful external or article links inside <main>/<article>/body
    root = soup.find("main") or soup.find("article") or soup.body or soup
    base_host = (urllib.parse.urlsplit(base_url).hostname or "").lower()
    for a in root.find_all("a", href=True):
        href = urllib.parse.urljoin(base_url, str(a["href"]).strip())
        if not href.startswith(("http://", "https://")) or href in seen:
            continue
        parsed = urllib.parse.urlsplit(href)
        if not parsed.path or parsed.path in ("/", "/search"):
            continue
        txt = a.get_text(" ", strip=True)
        if len(txt) < 6:
            continue
        # Avoid navigation boilerplate links without query relevance
        if parsed.hostname and parsed.hostname.lower() == base_host and len(parsed.path) < 4:
            continue
        seen.add(href)
        results.append(SearchResult(
            url=href,
            title=txt[:200],
            snippet="",
            engine=eng_id,
            category=category,
            network="clearnet",
        ))
        if len(results) >= limit:
            break

    return results


class ClearCustomEngine(BaseEngine):
    """Dynamic runner for custom & OpenSearch-imported clearnet engines and custom open archives."""

    def __init__(self):
        super().__init__(
            engine_id="clear_custom",
            name="Custom Web & OpenSearch Engines",
            category="general",
            network="clearnet",
            priority=72,
        )

    def _active_engines(self, mode: str = "") -> List[Dict[str, Any]]:
        cfg = get_search_config()
        local_only = bool(cfg.get("local_only", False))
        endpoints = cfg.get("endpoints", {})
        clear_entries = endpoints.get("custom_clear_engines", [])
        archive_entries = endpoints.get("archives", {}).get("custom_archives", [])

        combined: List[Dict[str, Any]] = []
        if isinstance(clear_entries, list):
            for eng in clear_entries:
                if isinstance(eng, dict):
                    combined.append(eng)
        if isinstance(archive_entries, list):
            for arch in archive_entries:
                if isinstance(arch, dict):
                    item = dict(arch)
                    item["_is_archive"] = True
                    combined.append(item)

        active: List[Dict[str, Any]] = []
        mode_low = (mode or "").strip().lower()
        for eng in combined:
            if eng.get("enabled", True) is False:
                continue
            target = str(eng.get("search_template") or eng.get("url") or "").strip()
            if not target and not eng.get("host"):
                continue
            if local_only and target and not _is_local_host(target):
                continue
            if mode_low == "files":
                cat = str(eng.get("category") or "general").strip().lower()
                if cat not in ("files", "packages"):
                    continue
            active.append(eng)
        return active

    def is_available(self) -> bool:
        return len(self._active_engines()) > 0

    def _query_one(self, eng_cfg: Dict[str, Any], query: SearchQuery) -> List[SearchResult]:
        eng_name = str(eng_cfg.get("name") or eng_cfg.get("host") or "Custom Web").strip()
        prefix = "archive" if eng_cfg.get("_is_archive") else "clear"
        eng_cat = str(eng_cfg.get("category") or "general").strip().lower()
        if eng_cat == "music":
            eng_cat = "audio"
        if eng_cat not in ("general", "videos", "images", "audio", "files", "news"):
            eng_cat = "general"

        raw_url = str(eng_cfg.get("url") or "").strip()
        if not raw_url and eng_cfg.get("host"):
            raw_url = build_endpoint_url(
                eng_cfg.get("protocol", "https"),
                eng_cfg.get("host", ""),
                eng_cfg.get("port", ""),
                eng_cfg.get("path", ""),
            )
        template = str(eng_cfg.get("search_template") or raw_url).strip()
        encoded_q = urllib.parse.quote_plus(query.query)

        if template:
            if "{q}" in template:
                target_url = template.replace("{q}", encoded_q)
            elif "{searchTerms}" in template:
                target_url = template.replace("{searchTerms}", encoded_q)
            elif raw_url and template == raw_url:
                base = raw_url.rstrip("/")
                if "?" in base:
                    target_url = f"{base}&q={encoded_q}"
                else:
                    target_url = f"{base}/search?q={encoded_q}" if not base.endswith("/search") else f"{base}?q={encoded_q}"
            else:
                sep = "&" if "?" in template else "?"
                target_url = f"{template}{sep}q={encoded_q}"
        else:
            return []

        headers: Dict[str, str] = {}
        if eng_cfg.get("use_api_key") and eng_cfg.get("api_key"):
            key_val = str(eng_cfg["api_key"]).strip()
            if key_val:
                if "{api_key}" in target_url:
                    target_url = target_url.replace("{api_key}", urllib.parse.quote_plus(key_val))
                else:
                    headers["Authorization"] = f"Bearer {key_val}"
                    headers["X-API-Key"] = key_val

        per_limit = min(max(int(query.limit or 25), 5), 40)
        try:
            resp = http_client.get(
                target_url,
                network="clearnet",
                headers=headers,
                timeout=min(float(query.timeout or 12.0), 12.0),
            )
            if resp.status_code != 200:
                return []
            ct = (resp.headers.get("Content-Type") or "").lower()
            head = resp.text.lstrip()[:200].lower()
            parsed_items: List[SearchResult] = []
            if "json" in ct or head[:1] in ("{", "["):
                try:
                    parsed_items = _extract_json_results(resp.json(), eng_name, target_url, per_limit, category=eng_cat, prefix=prefix)
                except Exception:
                    parsed_items = []
            if not parsed_items and (any(k in ct for k in ("rss", "atom", "xml")) or "<rss" in head or "<feed" in head):
                parsed_items = _extract_rss_atom_results(resp.text, eng_name, target_url, per_limit, category=eng_cat, prefix=prefix)
            if not parsed_items:
                parsed_items = _extract_html_results(resp.text, eng_name, target_url, per_limit, category=eng_cat, prefix=prefix)
            if eng_cat == "files":
                for r in parsed_items:
                    if not (r.metadata or {}).get("extension"):
                        ext = infer_extension(r.url, fallback="")
                        if ext:
                            r.metadata["extension"] = ext
            return parsed_items
        except Exception as e:
            hecos_logger.debug(f"[SEARCH:CLEAR_CUSTOM] '{eng_name}' failed: {e}")
            return []

    def search(self, query: SearchQuery) -> List[SearchResult]:
        engines = self._active_engines(mode=query.mode)
        if not engines:
            return []

        results: List[SearchResult] = []
        max_workers = min(len(engines), 6)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(self._query_one, eng, query) for eng in engines]
            for fut in as_completed(futures):
                try:
                    results.extend(fut.result())
                except Exception:
                    pass
        return results

