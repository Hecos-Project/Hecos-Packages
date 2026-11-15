"""
search/engines/osint_apis.py
Structured zero-key OSINT API adapters for Hecos Deep Search.
Provides person, username, email, and domain intelligence across open registries:
GitHub, GitLab, Reddit, HackerNews, Wikipedia, Wikidata, Gravatar, Keybase,
Internet Archive, and Certificate Transparency (crt.sh).
"""
from __future__ import annotations

import hashlib
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from .. import http_client
from ..models import SearchResult

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.osint_apis")

_UA = "HecosDeepSearch-OSINT/1.0 (+https://github.com/hecos)"

_EMAIL_RE = re.compile(r"^[^@\s]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})$")
_DOMAIN_RE = re.compile(r"^(?:https?://)?(?:www\.)?([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)(?:[/?#].*)?$")


def classify_osint_group(url: str = "", platform: str = "", title: str = "") -> str:
    """Classify an OSINT result into one of the UI subtabs: social | dev | media | records."""
    blob = f"{url} {platform} {title}".lower()
    if any(k in blob for k in (
        "github.com", "gitlab.com", "dev.to", "news.ycombinator", "hackernews",
        "keybase.io", "stackoverflow.com", "pypi.org", "hub.docker.com", "huggingface.co",
        "bitbucket.org", "codepen.io", "kaggle.com", "crt.sh", "npmjs.com", "replit.com",
    )):
        return "dev"
    if any(k in blob for k in (
        "youtube.com", "youtu.be", "twitch.tv", "spotify.com", "soundcloud.com",
        "steamcommunity.com", "steam", "vimeo.com", "flickr.com", "medium.com",
        "substack.com", "patreon.com", "bandcamp.com", "deviantart.com", "roblox.com",
    )):
        return "media"
    if any(k in blob for k in (
        "linkedin.com", "facebook.com", "instagram.com", "x.com/", "twitter.com",
        "tiktok.com", "threads.net", "bsky.app", "mastodon", "reddit.com",
        "t.me/", "telegram", "pinterest.com", "producthunt.com", "linktr.ee",
        "about.me", "vk.com", "snapchat.com",
    )):
        return "social"
    if any(k in blob for k in (
        "wikipedia.org", "wikidata.org", "archive.org", "gravatar.com",
        "imdb.com", "scholar.google", "orcid.org",
    )):
        return "records"
    return "social"


def parse_osint_input(raw_query: str) -> Dict[str, Any]:
    """Analyze query type (email, domain, handle, or multi-word person name) and extract handle variants."""
    q = (raw_query or "").strip()
    clean = q.lstrip("@").strip()
    email_match = _EMAIL_RE.match(q)
    if email_match:
        local_part, dom = q.split("@", 1)
        variants = _dedupe_variants([local_part, re.sub(r"[._-]+", "", local_part)])
        return {
            "kind": "email",
            "raw": q,
            "clean": q,
            "email": q,
            "domain": dom.lower(),
            "variants": variants,
        }

    dom_match = _DOMAIN_RE.match(clean)
    if dom_match and " " not in clean and "@" not in clean:
        domain = dom_match.group(1).lower()
        root_tok = domain.split(".")[0]
        return {
            "kind": "domain",
            "raw": q,
            "clean": domain,
            "email": None,
            "domain": domain,
            "variants": _dedupe_variants([root_tok]),
        }

    words = [re.sub(r"[^\w.-]", "", w) for w in clean.split() if re.sub(r"[^\w.-]", "", w)]
    if len(words) >= 2:
        joined_plain = "".join(words).lower()
        joined_dot = ".".join(words[:2]).lower()
        joined_under = "_".join(words[:2]).lower()
        joined_dash = "-".join(words[:2]).lower()
        return {
            "kind": "person",
            "raw": q,
            "clean": clean,
            "email": None,
            "domain": None,
            "variants": _dedupe_variants([joined_plain, joined_dot, joined_under, joined_dash]),
        }

    handle = words[0] if words else re.sub(r"\s+", "", clean)
    return {
        "kind": "handle",
        "raw": q,
        "clean": handle,
        "email": None,
        "domain": None,
        "variants": _dedupe_variants([handle, handle.lower()]),
    }


def _dedupe_variants(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        s = (item or "").strip()
        if s and len(s) >= 2 and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def fetch_github_osint(query: str, rows: int = 15, timeout: float = 7.0) -> List[SearchResult]:
    out: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://api.github.com/search/users",
            network="clearnet",
            params={"q": query, "per_page": min(max(rows, 5), 25)},
            headers={"Accept": "application/vnd.github+json", "User-Agent": _UA},
            timeout=min(timeout, 7.0),
        )
        if resp.status_code != 200:
            return out
        for u in resp.json().get("items") or []:
            login = u.get("login") or ""
            html_url = u.get("html_url") or ""
            if not (login and html_url):
                continue
            utype = u.get("type") or "User"
            out.append(SearchResult(
                title=f"GitHub ({utype}): {login}",
                url=html_url,
                snippet=f"GitHub {utype.lower()} account '{login}' (score={u.get('score', 0):.1f})",
                engine="osint:github",
                category="osint",
                network="clearnet",
                score=1.35,
                thumbnail_url=u.get("avatar_url") or None,
                metadata={"platform": "GitHub", "username": login, "osint_group": "dev"},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[OSINT:GITHUB] {exc}")
    return out


def fetch_gitlab_osint(query: str, rows: int = 12, timeout: float = 7.0) -> List[SearchResult]:
    out: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://gitlab.com/api/v4/users",
            network="clearnet",
            params={"search": query, "per_page": min(max(rows, 5), 20)},
            headers={"Accept": "application/json", "User-Agent": _UA},
            timeout=min(timeout, 7.0),
        )
        if resp.status_code != 200 or not isinstance(resp.json(), list):
            return out
        for u in resp.json():
            uname = u.get("username") or ""
            name = u.get("name") or uname
            web_url = u.get("web_url") or (f"https://gitlab.com/{uname}" if uname else "")
            if not web_url:
                continue
            out.append(SearchResult(
                title=f"GitLab: {name} (@{uname})" if name != uname else f"GitLab: @{uname}",
                url=web_url,
                snippet=f"GitLab profile ({u.get('state', 'active')}) for {name}",
                engine="osint:gitlab",
                category="osint",
                network="clearnet",
                score=1.25,
                thumbnail_url=u.get("avatar_url") or None,
                metadata={"platform": "GitLab", "username": uname, "osint_group": "dev"},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[OSINT:GITLAB] {exc}")
    return out


def fetch_reddit_osint(query: str, rows: int = 12, timeout: float = 7.0) -> List[SearchResult]:
    out: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://www.reddit.com/search.json",
            network="clearnet",
            params={"q": query, "type": "user", "limit": min(max(rows, 5), 20)},
            headers={"User-Agent": _UA},
            timeout=min(timeout, 7.0),
        )
        if resp.status_code != 200:
            return out
        children = resp.json().get("data", {}).get("children", []) or []
        for child in children:
            d = child.get("data") or {}
            name = d.get("name") or ""
            if not name:
                continue
            sub = d.get("subreddit") or {}
            bio = (sub.get("public_description") or "").strip()
            karma = (d.get("link_karma") or 0) + (d.get("comment_karma") or 0)
            out.append(SearchResult(
                title=f"Reddit: u/{name}",
                url=f"https://www.reddit.com/user/{urllib.parse.quote(name)}/",
                snippet=bio or f"Reddit user profile u/{name} (karma: {karma})",
                engine="osint:reddit",
                category="osint",
                network="clearnet",
                score=1.2,
                thumbnail_url=(d.get("icon_img") or "").split("?")[0] or None,
                metadata={"platform": "Reddit", "username": name, "osint_group": "social"},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[OSINT:REDDIT] {exc}")
    return out


def fetch_hackernews_osint(query: str, rows: int = 12, timeout: float = 7.0) -> List[SearchResult]:
    out: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://hn.algolia.com/api/v1/search",
            network="clearnet",
            params={"query": query, "hitsPerPage": min(max(rows, 5), 20)},
            headers={"User-Agent": _UA},
            timeout=min(timeout, 7.0),
        )
        if resp.status_code != 200:
            return out
        for h in resp.json().get("hits") or []:
            oid = h.get("objectID")
            author = h.get("author") or ""
            title = h.get("title") or h.get("story_title") or (f"HN User: {author}" if author else "")
            url = h.get("url") or h.get("story_url") or (f"https://news.ycombinator.com/item?id={oid}" if oid else "")
            if not (title and url):
                continue
            out.append(SearchResult(
                title=f"[HN] {title}",
                url=url,
                snippet=f"HackerNews author: {author} | points: {h.get('points', 0)} | comments: {h.get('num_comments', 0)}",
                engine="osint:hackernews",
                category="osint",
                network="clearnet",
                score=1.1,
                metadata={"platform": "HackerNews", "username": author, "osint_group": "dev"},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[OSINT:HN] {exc}")
    return out


def fetch_wikipedia_osint(query: str, rows: int = 8, timeout: float = 7.0) -> List[SearchResult]:
    out: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://en.wikipedia.org/w/api.php",
            network="clearnet",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": min(max(rows, 5), 15),
                "format": "json",
            },
            headers={"User-Agent": _UA},
            timeout=min(timeout, 7.0),
        )
        if resp.status_code != 200:
            return out
        for item in resp.json().get("query", {}).get("search", []) or []:
            title = item.get("title") or ""
            if not title:
                continue
            slug = urllib.parse.quote(title.replace(" ", "_"))
            snip = re.sub(r"<[^>]+>", "", item.get("snippet") or "").strip()
            out.append(SearchResult(
                title=f"Wikipedia: {title}",
                url=f"https://en.wikipedia.org/wiki/{slug}",
                snippet=snip,
                engine="osint:wikipedia",
                category="osint",
                network="clearnet",
                score=1.25,
                metadata={"platform": "Wikipedia", "osint_group": "records"},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[OSINT:WIKIPEDIA] {exc}")
    return out


def fetch_wikidata_osint(query: str, rows: int = 8, timeout: float = 7.0) -> List[SearchResult]:
    out: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://www.wikidata.org/w/api.php",
            network="clearnet",
            params={
                "action": "wbsearchentities",
                "search": query,
                "language": "en",
                "limit": min(max(rows, 5), 15),
                "format": "json",
            },
            headers={"User-Agent": _UA},
            timeout=min(timeout, 7.0),
        )
        if resp.status_code != 200:
            return out
        for item in resp.json().get("search", []) or []:
            qid = item.get("id") or ""
            label = item.get("label") or qid
            url = item.get("concepturi") or (f"https://www.wikidata.org/wiki/{qid}" if qid else "")
            if not url:
                continue
            desc = item.get("description") or "Wikidata structured entity record"
            out.append(SearchResult(
                title=f"Wikidata ({qid}): {label}",
                url=url,
                snippet=desc,
                engine="osint:wikidata",
                category="osint",
                network="clearnet",
                score=1.15,
                metadata={"platform": "Wikidata", "osint_group": "records"},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[OSINT:WIKIDATA] {exc}")
    return out


def fetch_gravatar_osint(email_or_query: str, timeout: float = 5.0) -> List[SearchResult]:
    out: List[SearchResult] = []
    if "@" not in (email_or_query or ""):
        return out
    try:
        norm_email = email_or_query.strip().lower()
        md5_hash = hashlib.md5(norm_email.encode("utf-8")).hexdigest()
        resp = http_client.get(
            f"https://en.gravatar.com/{md5_hash}.json",
            network="clearnet",
            headers={"User-Agent": _UA},
            timeout=min(timeout, 5.0),
        )
        if resp.status_code != 200:
            return out
        entries = resp.json().get("entry") or []
        for entry in entries[:3]:
            profile_url = entry.get("profileUrl") or f"https://gravatar.com/{md5_hash}"
            display_name = entry.get("displayName") or entry.get("preferredUsername") or norm_email
            about = entry.get("aboutMe") or entry.get("currentLocation") or "Verified Gravatar identity profile"
            out.append(SearchResult(
                title=f"Gravatar Identity: {display_name}",
                url=profile_url,
                snippet=about,
                engine="osint:gravatar",
                category="osint",
                network="clearnet",
                score=1.5,
                thumbnail_url=entry.get("thumbnailUrl") or None,
                metadata={"platform": "Gravatar", "username": entry.get("preferredUsername") or "", "osint_group": "records"},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[OSINT:GRAVATAR] {exc}")
    return out


def fetch_keybase_osint(query: str, rows: int = 10, timeout: float = 6.0) -> List[SearchResult]:
    out: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://keybase.io/_/api/1.0/user/autocomplete.json",
            network="clearnet",
            params={"q": query},
            headers={"User-Agent": _UA},
            timeout=min(timeout, 6.0),
        )
        if resp.status_code != 200:
            return out
        for comp in (resp.json().get("completions") or [])[:rows]:
            uname = (comp.get("components") or {}).get("username", {}).get("val")
            if not uname:
                continue
            full_name = (comp.get("components") or {}).get("full_name", {}).get("val") or ""
            proofs = []
            for k in ("twitter", "github", "reddit", "hackernews", "websites"):
                val = (comp.get("components") or {}).get(k, {}).get("val")
                if val:
                    proofs.append(f"{k}:{val}")
            out.append(SearchResult(
                title=f"Keybase: {uname}" + (f" ({full_name})" if full_name else ""),
                url=f"https://keybase.io/{urllib.parse.quote(uname)}",
                snippet=("Verified proofs: " + ", ".join(proofs)) if proofs else "Keybase cryptographic identity",
                engine="osint:keybase",
                category="osint",
                network="clearnet",
                score=1.35,
                thumbnail_url=comp.get("thumbnail") or None,
                metadata={"platform": "Keybase", "username": uname, "osint_group": "dev"},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[OSINT:KEYBASE] {exc}")
    return out


def fetch_archive_org_osint(query: str, rows: int = 12, timeout: float = 7.0) -> List[SearchResult]:
    out: List[SearchResult] = []
    try:
        safe_q = re.sub(r'[()":]+', " ", query).strip()
        if not safe_q:
            return out
        resp = http_client.get(
            "https://archive.org/advancedsearch.php",
            network="clearnet",
            params={
                "q": f'creator:("{safe_q}") OR title:("{safe_q}") OR subject:("{safe_q}")',
                "fl[]": ["identifier", "title", "creator", "mediatype", "description"],
                "rows": min(max(rows, 5), 20),
                "page": 1,
                "output": "json",
            },
            headers={"User-Agent": _UA},
            timeout=min(timeout, 7.0),
        )
        if resp.status_code != 200:
            return out
        for doc in resp.json().get("response", {}).get("docs", []) or []:
            ident = doc.get("identifier") or ""
            if not ident:
                continue
            title = doc.get("title") or ident
            creator = doc.get("creator")
            if isinstance(creator, list):
                creator = ", ".join(str(c) for c in creator[:2])
            desc = doc.get("description") or ""
            if isinstance(desc, list):
                desc = " ".join(str(d) for d in desc[:2])
            out.append(SearchResult(
                title=f"Archive.org: {title}",
                url=f"https://archive.org/details/{urllib.parse.quote(ident)}",
                snippet=f"Creator: {creator or 'n/a'} | {str(desc)[:180]}",
                engine="osint:archive_org",
                category="osint",
                network="clearnet",
                score=1.05,
                metadata={"platform": "Archive.org", "osint_group": "records"},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[OSINT:ARCHIVE] {exc}")
    return out


def fetch_crtsh_osint(domain: str, rows: int = 20, timeout: float = 8.0) -> List[SearchResult]:
    out: List[SearchResult] = []
    dom = (domain or "").strip().lower().lstrip("*.")
    if not dom or "." not in dom or " " in dom:
        return out
    try:
        resp = http_client.get(
            "https://crt.sh/",
            network="clearnet",
            params={"q": f"%.{dom}", "output": "json"},
            headers={"User-Agent": _UA},
            timeout=min(timeout, 8.0),
        )
        if resp.status_code != 200:
            return out
        seen_names = set()
        for entry in resp.json():
            raw_names = str(entry.get("name_value") or "").splitlines()
            issuer = str(entry.get("issuer_name") or "").split(",")[0]
            for name in raw_names:
                sub = name.strip().lower()
                if not sub or sub in seen_names or "*" in sub:
                    continue
                seen_names.add(sub)
                out.append(SearchResult(
                    title=f"CT Subdomain: {sub}",
                    url=f"https://{sub}",
                    snippet=f"Certificate Transparency record for {dom} (issuer: {issuer or 'CA'})",
                    engine="osint:crtsh",
                    category="osint",
                    network="clearnet",
                    score=1.2,
                    metadata={"platform": "crt.sh", "domain": dom, "osint_group": "dev"},
                ))
                if len(out) >= rows:
                    return out
    except Exception as exc:
        hecos_logger.debug(f"[OSINT:CRTSH] {exc}")
    return out

