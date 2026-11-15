"""
search/sources/fetcher.py
Resilient source fetcher supporting HTTP/HTTPS, GitHub raw normalization,
Tor (.onion via socks5h), OpenSearch HTML auto-discovery, and local files.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Dict, Optional

try:
    from hecos.modules.net_search.search import http_client
except (ImportError, ValueError):
    from .. import http_client

from .parsers import discover_opensearch_links_from_html


MAX_SOURCE_BYTES = 30 * 1024 * 1024  # 30 MB safety cap


@dataclass
class FetchResult:
    ok: bool
    content: bytes = b""
    not_modified: bool = False
    tor_offline: bool = False
    resolved_url: str = ""
    file_path: str = ""
    content_type: str = ""
    etag: str = ""
    last_modified: str = ""
    sha256: str = ""
    error: str = ""


def _resolve_github_repo_raw(url: str, timeout: float = 10.0) -> str:
    """
    If `url` points to a GitHub repository root (e.g. `https://github.com/owner/repo`),
    discovers the main compilation file via `meta.json` or GitHub Contents API.
    """
    m = re.match(r"^https?://github\.com/([^/]+)/([^/?#]+?)(?:\.git)?(?:/tree/([^/?#]+))?/?$", (url or "").strip(), re.IGNORECASE)
    if not m:
        return url
    owner, repo, branch = m.groups()
    branches = [branch] if branch else ["main", "master"]

    # 1. Fast path: check meta.json (used by Bon-Appetit/porn-domains and similar automated repos)
    for br in branches:
        meta_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{br}/meta.json"
        try:
            r = http_client.request("GET", meta_url, network="clearnet", timeout=min(timeout, 8.0))
            if r.status_code == 200:
                meta = r.json()
                if isinstance(meta, dict):
                    for key in ("blocklist", "list", "domains", "allowlist"):
                        sub = meta.get(key)
                        if isinstance(sub, dict) and isinstance(sub.get("raw_url"), str) and sub["raw_url"].startswith("http"):
                            return sub["raw_url"]
                    if isinstance(meta.get("raw_url"), str) and meta["raw_url"].startswith("http"):
                        return meta["raw_url"]
        except Exception:
            pass

    # 2. Fallback: GitHub Contents API
    try:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
        if branch:
            api_url += f"?ref={urllib.parse.quote(branch)}"
        r = http_client.request(
            "GET",
            api_url,
            network="clearnet",
            timeout=min(timeout, 10.0),
            headers={"Accept": "application/vnd.github+json"},
        )
        if r.status_code == 200 and isinstance(r.json(), list):
            ignored_names = {"readme.md", "license", "license.md", "license.txt", ".gitignore", ".gitattributes", ".editorconfig"}
            files = [
                x for x in r.json()
                if isinstance(x, dict)
                and x.get("type") == "file"
                and x.get("download_url")
                and str(x.get("name", "")).lower() not in ignored_names
                and not str(x.get("name", "")).startswith(".")
            ]
            # Prefer structured/compilation files or largest .txt blocklist
            def _score(f):
                name = str(f.get("name", "")).lower()
                ext = os.path.splitext(name)[1]
                size = int(f.get("size") or 0)
                prio = 0
                if "block" in name or "engines" in name or "onion" in name or "instances" in name:
                    prio += 100
                if ext in (".json", ".yaml", ".yml", ".csv", ".sqlite", ".db", ".osd", ".xml"):
                    prio += 50
                elif ext == ".txt":
                    prio += 30
                return (prio, size)

            if files:
                best = max(files, key=_score)
                return str(best["download_url"])
    except Exception:
        pass

    return url


def normalize_source_url(url: str) -> str:
    """Converts GitHub blob/gist URLs into raw.githubusercontent.com URLs automatically."""
    u = (url or "").strip()
    if not u:
        return ""
    m = re.match(r"^https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)$", u, re.IGNORECASE)
    if m:
        owner, repo, branch, path = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    # GitHub gist page -> /raw
    gm = re.match(r"^https?://gist\.github\.com/([^/]+)/([a-f0-9]+)$", u, re.IGNORECASE)
    if gm:
        return f"{u.rstrip('/')}/raw"
    return u


def fetch_source(
    location: str,
    use_tor: bool = False,
    etag: str = "",
    last_modified: str = "",
    timeout: float = 15.0,
    prefer_opensearch: bool = False,
    retries: int = 2,
) -> FetchResult:
    """
    Fetches bytes from a local path or remote URL (Clearnet / GitHub / Tor .onion).
    Uses conditional HTTP headers when `etag` / `last_modified` are provided.
    """
    loc = (location or "").strip()
    if not loc:
        return FetchResult(ok=False, error="Empty source location.")

    # 1. Local filesystem path or file:// URI
    if loc.startswith("file://") or (not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", loc)):
        path = urllib.parse.unquote(loc[7:]) if loc.startswith("file://") else loc
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        if not os.path.isfile(path):
            return FetchResult(ok=False, error=f"Local file not found: {path}")
        size = os.path.getsize(path)
        if size > MAX_SOURCE_BYTES:
            return FetchResult(ok=False, error=f"File exceeds {MAX_SOURCE_BYTES // (1024 * 1024)} MB limit.")
        with open(path, "rb") as f:
            data = f.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            return FetchResult(ok=False, error="File exceeds safety size limit.")
        digest = hashlib.sha256(data).hexdigest()
        return FetchResult(
            ok=True,
            content=data,
            resolved_url=loc,
            file_path=path,
            sha256=digest,
        )

    # 2. Remote URL
    resolved = normalize_source_url(loc)
    if "github.com/" in resolved.lower() and "/blob/" not in resolved.lower():
        resolved = _resolve_github_repo_raw(resolved, timeout=timeout)
    needs_tor = bool(use_tor) or (".onion" in resolved.lower())
    if needs_tor and not http_client.is_tor_online():
        return FetchResult(
            ok=False,
            tor_offline=True,
            resolved_url=resolved,
            error="Tor proxy is offline; cannot fetch .onion/Tor source safely.",
        )

    headers: Dict[str, str] = {"Accept": "*/*"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    eff_timeout = max(timeout, 25.0) if needs_tor else timeout
    last_err = ""
    for attempt in range(max(1, retries + 1)):
        try:
            resp = http_client.request(
                "GET",
                resolved,
                network="tor" if needs_tor else "clearnet",
                timeout=eff_timeout,
                headers=headers,
            )
            if resp.status_code == 304:
                return FetchResult(
                    ok=True,
                    not_modified=True,
                    resolved_url=resolved,
                    etag=resp.headers.get("ETag", etag),
                    last_modified=resp.headers.get("Last-Modified", last_modified),
                )
            if resp.status_code >= 400:
                last_err = f"HTTP {resp.status_code}"
                if resp.status_code in (404, 403, 401):
                    break
                time.sleep(0.4 * (attempt + 1))
                continue

            data = resp.content[: MAX_SOURCE_BYTES + 1]
            if len(data) > MAX_SOURCE_BYTES:
                return FetchResult(ok=False, resolved_url=resolved, error="Remote response exceeds 15 MB limit.")

            ct = (resp.headers.get("Content-Type") or "").lower()
            # HTML OpenSearch auto-discovery when pointing directly to a site homepage/HTML
            if (prefer_opensearch or "text/html" in ct) and b"<opensearchdescription" not in data[:2048].lower():
                if "text/html" in ct:
                    osd_links = discover_opensearch_links_from_html(
                        data.decode("utf-8", errors="ignore"),
                        base_url=resp.url or resolved,
                    )
                    if osd_links:
                        sub_url = osd_links[0]
                        sub_tor = needs_tor or (".onion" in sub_url.lower())
                        sub_resp = http_client.request(
                            "GET",
                            sub_url,
                            network="tor" if sub_tor else "clearnet",
                            timeout=eff_timeout,
                            headers={"Accept": "application/opensearchdescription+xml, application/xml, text/xml"},
                        )
                        if sub_resp.status_code < 400 and sub_resp.content:
                            sub_data = sub_resp.content[:MAX_SOURCE_BYTES]
                            return FetchResult(
                                ok=True,
                                content=sub_data,
                                resolved_url=sub_url,
                                content_type=sub_resp.headers.get("Content-Type", "application/opensearchdescription+xml"),
                                etag=sub_resp.headers.get("ETag", ""),
                                last_modified=sub_resp.headers.get("Last-Modified", ""),
                                sha256=hashlib.sha256(sub_data).hexdigest(),
                            )

            return FetchResult(
                ok=True,
                content=data,
                resolved_url=resp.url or resolved,
                content_type=ct,
                etag=resp.headers.get("ETag", ""),
                last_modified=resp.headers.get("Last-Modified", ""),
                sha256=hashlib.sha256(data).hexdigest(),
            )
        except Exception as e:
            last_err = str(e)
            if attempt < retries:
                time.sleep(0.4 * (attempt + 1))

    return FetchResult(ok=False, resolved_url=resolved, error=last_err or "Fetch failed.")

