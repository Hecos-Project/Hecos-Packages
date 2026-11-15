"""
search/engines/dark_custom.py
Custom user-defined Tor onion search engines runner.
Dynamically executes searches on user-configured .onion search engines via Tor SOCKS5h.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from typing import List, Dict, Any

from .base import BaseEngine, effective_tor_timeout
from .clear_custom import _extract_json_results, _extract_rss_atom_results, _extract_html_results
from .files_apis import infer_extension
from ..models import SearchQuery, SearchResult
from .. import http_client

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.custom_onion")
logger = hecos_logger


class DarkCustomEngine(BaseEngine):
    """Dynamic runner for user-configured custom .onion search engines."""

    def __init__(self):
        super().__init__(
            engine_id="dark_custom",
            name="Custom Onion Engines",
            category="onion",
            network="tor",
            priority=75
        )

    def _active_onion_engines(self, mode: str = "") -> List[Dict[str, Any]]:
        from ..config import get_search_config
        custom_engines = get_search_config().get("endpoints", {}).get("custom_onion_engines", []) or []
        active: List[Dict[str, Any]] = []
        mode_lower = (mode or "").lower()
        for eng_cfg in custom_engines:
            if not isinstance(eng_cfg, dict) or not eng_cfg.get("enabled", True):
                continue
            eng_cat = str(eng_cfg.get("category") or "onion").strip().lower()
            if mode_lower == "files" and eng_cat not in ("files", "packages"):
                continue
            active.append(eng_cfg)
        return active

    def is_available(self) -> bool:
        from ..config import get_search_config
        cfg = get_search_config()
        if not cfg.get("tor", {}).get("enabled", False):
            return False
        return len(self._active_onion_engines()) > 0 and http_client.is_tor_online()

    def search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        if not self.is_available():
            return results

        mode_lower = (getattr(query, "mode", "") or "").lower()
        active_engines = self._active_onion_engines(mode=mode_lower)
        if not active_engines:
            return results

        encoded_q = urllib.parse.quote_plus(query.query)
        raw_q = query.query.lower().strip()
        tor_timeout = effective_tor_timeout(query.timeout, minimum=15.0)

        for eng_cfg in active_engines:
            eng_name = eng_cfg.get("name", "Custom Onion")
            eng_cat = str(eng_cfg.get("category") or "onion").strip().lower()
            res_cat = "files" if (mode_lower == "files" or eng_cat in ("files", "packages")) else eng_cat

            raw_url = str(eng_cfg.get("onion_url") or eng_cfg.get("url") or "").strip()
            if not raw_url and eng_cfg.get("host"):
                from ..config import build_endpoint_url
                raw_url = build_endpoint_url(
                    eng_cfg.get("protocol", "http"),
                    eng_cfg.get("host", ""),
                    eng_cfg.get("port", ""),
                    eng_cfg.get("path", ""),
                )
            template = str(eng_cfg.get("search_template") or "").strip()
            if not template and raw_url and ("{q}" in raw_url or "{searchTerms}" in raw_url):
                template = raw_url

            if not raw_url and not template:
                continue

            if template and ("{q}" in template or "{searchTerms}" in template):
                target_url = template.replace("{q}", encoded_q).replace("{searchTerms}", encoded_q)
            elif template:
                sep = "&" if "?" in template else "?"
                target_url = f"{template}{sep}q={encoded_q}"
            elif "{q}" in raw_url or "{searchTerms}" in raw_url:
                target_url = raw_url.replace("{q}", encoded_q).replace("{searchTerms}", encoded_q)
            else:
                target_url = f"{raw_url.rstrip('/')}/search?q={encoded_q}"

            key_val = str(eng_cfg.get("api_key") or "").strip() if eng_cfg.get("use_api_key") else ""
            if "{api_key}" in target_url:
                target_url = target_url.replace("{api_key}", urllib.parse.quote_plus(key_val))

            headers: Dict[str, str] = {}
            if key_val:
                headers["Authorization"] = f"Bearer {key_val}"
                headers["X-API-Key"] = key_val

            hecos_logger.info(
                f"[SEARCH:CUSTOM_ONION] Querying '{eng_name}' ({res_cat}) at {target_url} "
                f"(Auth={'Yes' if headers else 'No'}, timeout={tor_timeout}s)..."
            )

            try:
                resp = http_client.get(target_url, network="tor", headers=headers, timeout=tor_timeout)
                if resp.status_code != 200:
                    continue

                ctype = (resp.headers.get("Content-Type") or "").lower()
                text = resp.text or ""
                stripped = text.lstrip()
                extracted: List[SearchResult] = []

                if "json" in ctype or stripped.startswith("{") or stripped.startswith("["):
                    try:
                        data = resp.json()
                    except Exception:
                        data = json.loads(text)
                    extracted = _extract_json_results(
                        data, eng_name, target_url, query.limit, category=res_cat, prefix="dark", network="tor"
                    )
                elif "xml" in ctype or "rss" in ctype or "atom" in ctype or stripped.startswith(("<?xml", "<rss", "<feed")):
                    extracted = _extract_rss_atom_results(
                        text, eng_name, target_url, query.limit, category=res_cat, prefix="dark", network="tor"
                    )
                else:
                    extracted = _extract_html_results(
                        text, eng_name, target_url, query.limit, category=res_cat, prefix="dark", network="tor"
                    )
                    # For Open Directory (.onion Apache/Nginx 'Index of /') endpoints, prioritize files matching query tokens
                    if res_cat == "files" and raw_q and extracted:
                        tokens = [t for t in raw_q.split() if len(t) >= 2]
                        if tokens:
                            matched = [
                                r for r in extracted
                                if any(tok in r.title.lower() or tok in r.url.lower() for tok in tokens)
                            ]
                            if matched:
                                extracted = matched

                for r in extracted:
                    if not r.metadata:
                        r.metadata = {}
                    if not r.metadata.get("extension") and r.url:
                        ext = infer_extension(r.url, fallback="")
                        if ext:
                            r.metadata["extension"] = ext

                results.extend(extracted[:query.limit])
            except Exception as e:
                hecos_logger.warning(f"[SEARCH:CUSTOM_ONION] Engine '{eng_name}' query failed: {e}")

        return results
