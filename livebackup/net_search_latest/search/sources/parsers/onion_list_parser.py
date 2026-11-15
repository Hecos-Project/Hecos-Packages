"""
search/sources/parsers/onion_list_parser.py
Parser for plain-text, Markdown, or HTML compilations containing .onion or clearnet search URLs.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


_MD_LINK_RE = re.compile(r"\[([^\]]{1,120})\]\((https?://[^\s\)]+)\)")
_URL_RE = re.compile(r"(https?://[a-zA-Z0-9._:/?=&%{}+~\-]+)")
_BARE_ONION_RE = re.compile(r"\b([a-z2-7]{16,56}\.onion(?::\d+)?(?:/[^\s\"'<>]*)?)\b", re.IGNORECASE)


def parse_onion_or_text_list(raw_bytes: bytes, source_url: str = "") -> List[Dict[str, Any]]:
    text = raw_bytes.decode("utf-8", errors="replace")
    if not text.strip():
        return []

    candidates: List[Dict[str, Any]] = []
    seen_raw: set[str] = set()

    def _add(url: str, name: str = ""):
        u = url.strip().rstrip(".,;\"')")
        if not u:
            return
        if not u.startswith(("http://", "https://", "socks5://", "socks5h://")):
            u = ("http://" if ".onion" in u.lower() else "https://") + u
        if u.lower() in seen_raw:
            return
        seen_raw.add(u.lower())
        is_onion = ".onion" in u.lower()
        candidates.append({
            "name": name.strip() if name else "",
            "url": u,
            "kind": "onion" if is_onion else "clear_engine",
            "enabled": True,
        })

    # 1. HTML anchors if markup looks like HTML
    lowered = text.lstrip()[:512].lower()
    if ("<html" in lowered or "<a " in text.lower()) and BeautifulSoup is not None:
        soup = BeautifulSoup(text, "lxml")
        for a in soup.find_all("a", href=True):
            href = str(a["href"]).strip()
            if ".onion" in href.lower() or href.startswith(("http://", "https://")) and "{q}" in href:
                _add(href, a.get_text(" ", strip=True)[:80])
        if candidates:
            return candidates

    # 2. Line-by-line parsing (Markdown links, pipe/tab delimited, comments, bare .onion)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        md_matches = _MD_LINK_RE.findall(line)
        if md_matches:
            for label, url in md_matches:
                _add(url, label)
            continue

        # "Name | http://...onion" or "http://... | Name"
        if "|" in line and "://" in line:
            parts = [p.strip(" -*\t") for p in line.split("|") if p.strip()]
            url_part = next((p for p in parts if "://" in p or ".onion" in p.lower()), "")
            name_part = next((p for p in parts if p != url_part), "")
            if url_part:
                _add(url_part, name_part)
                continue

        urls = _URL_RE.findall(line)
        if urls:
            for u in urls:
                _add(u)
            continue

        for onion in _BARE_ONION_RE.findall(line):
            _add(onion)

    return candidates

