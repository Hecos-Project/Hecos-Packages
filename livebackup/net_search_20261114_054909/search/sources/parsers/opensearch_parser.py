"""
search/sources/parsers/opensearch_parser.py
Parser for OpenSearch XML Description (<OpenSearchDescription>) documents
and HTML pages exposing <link rel="search" type="application/opensearchdescription+xml">.
"""
from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1].lower() if "}" in tag else tag.lower()


def discover_opensearch_links_from_html(html_text: str, base_url: str = "") -> List[str]:
    """Extracts OpenSearch XML descriptor URLs embedded in an HTML document."""
    links: List[str] = []
    if not html_text:
        return links
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html_text, "lxml")
        for tag in soup.find_all("link", href=True):
            rel = " ".join(tag.get("rel", [])) if isinstance(tag.get("rel"), list) else str(tag.get("rel", ""))
            ltype = str(tag.get("type", "")).lower()
            if "search" in rel.lower() or "opensearchdescription" in ltype:
                href = str(tag["href"]).strip()
                if href:
                    links.append(urllib.parse.urljoin(base_url, href) if base_url else href)
    else:
        for m in re.finditer(r'<link[^>]+opensearchdescription\+xml[^>]+href=["\']([^"\']+)["\']', html_text, re.I):
            href = m.group(1).strip()
            links.append(urllib.parse.urljoin(base_url, href) if base_url else href)
    return list(dict.fromkeys(links))


def parse_opensearch(raw_bytes: bytes, source_url: str = "") -> List[Dict[str, Any]]:
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        return []

    root = ET.fromstring(text)
    if _local_tag(root.tag) != "opensearchdescription":
        raise ValueError("XML root is not OpenSearchDescription.")

    short_name = ""
    description = ""
    urls: List[Dict[str, str]] = []

    for child in root:
        tag = _local_tag(child.tag)
        if tag == "shortname" and child.text:
            short_name = child.text.strip()
        elif tag == "description" and child.text:
            description = child.text.strip()
        elif tag == "url":
            tmpl = (child.attrib.get("template") or "").strip()
            utype = (child.attrib.get("type") or "text/html").strip().lower()
            rel = (child.attrib.get("rel") or "results").strip().lower()
            if tmpl:
                urls.append({"template": tmpl, "type": utype, "rel": rel})

    # Prefer results URLs (text/html or application/json), ignore suggestions/self
    result_urls = [u for u in urls if "suggestions" not in u["type"] and u["rel"] in ("results", "")]
    if not result_urls:
        result_urls = [u for u in urls if "suggestions" not in u["type"]]
    if not result_urls:
        return []

    # Pick JSON first if available, else text/html, else first
    chosen = next((u for u in result_urls if "json" in u["type"]), None) or next(
        (u for u in result_urls if "html" in u["type"]), result_urls[0]
    )

    template = chosen["template"]
    if source_url and template.startswith("/"):
        template = urllib.parse.urljoin(source_url, template)

    is_onion = ".onion" in template.lower()
    return [
        {
            "name": short_name or description or urllib.parse.urlsplit(template).hostname or "OpenSearch Engine",
            "url": template.split("?", 1)[0],
            "search_template": template,
            "kind": "onion" if is_onion else "opensearch",
            "target_pool": "custom_onion_engines" if is_onion else "custom_clear_engines",
            "category": "onion" if is_onion else "general",
            "enabled": True,
        }
    ]

