"""
search/engines/files_apis.py
Direct open-API file & repository adapters for File Hunter (`mode="files"`).
Covers Documents/PDFs (Internet Archive, OpenAlex, arXiv, Wikimedia Commons),
Datasets (Hugging Face, Internet Archive Data), and Code/Packages (GitHub, npm, Archive Software).
All network calls route through `http_client` so proxies, retries, and TLS rules apply uniformly.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Optional, Set

from .. import http_client
from ..endpoints_config import get_archive_endpoint
from ..models import SearchResult

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.files_apis")


KNOWN_FILE_EXTS: Set[str] = {
    # Documents
    "pdf", "docx", "doc", "epub", "odt", "txt", "rtf", "djvu", "mobi", "md",
    # Data & Sheets
    "xlsx", "xls", "csv", "sql", "json", "jsonl", "xml", "sqlite", "db", "tsv", "parquet",
    # Archives & Images
    "zip", "rar", "7z", "tar", "gz", "tgz", "iso", "bz2", "xz", "img", "dmg",
    # Code & Config
    "py", "js", "ts", "sh", "bat", "c", "cpp", "h", "html", "css", "yaml", "yml",
    "env", "rs", "go", "php", "toml", "ini", "whl", "jar",
}

DOC_EXTS: Set[str] = {"pdf", "docx", "doc", "epub", "odt", "txt", "rtf", "djvu", "mobi", "md"}
DATA_EXTS: Set[str] = {"xlsx", "xls", "csv", "sql", "json", "jsonl", "xml", "sqlite", "db", "tsv", "parquet"}
ARCHIVE_EXTS: Set[str] = {"zip", "rar", "7z", "tar", "gz", "tgz", "iso", "bz2", "xz", "img", "dmg"}
CODE_EXTS: Set[str] = {"py", "js", "ts", "sh", "bat", "c", "cpp", "h", "html", "css", "yaml", "yml", "env", "rs", "go", "php", "toml", "ini", "whl", "jar"}

_LANG_TO_EXT = {
    "python": "py",
    "javascript": "js",
    "typescript": "ts",
    "shell": "sh",
    "bash": "sh",
    "rust": "rs",
    "go": "go",
    "c": "c",
    "c++": "cpp",
    "php": "php",
    "html": "html",
    "css": "css",
    "yaml": "yaml",
    "json": "json",
    "sql": "sql",
}


def infer_extension(url: str, fallback: str = "") -> str:
    """Extracts a normalized known file extension from a URL or filename."""
    clean = (url or "").split("?")[0].split("#")[0].strip().lower()
    if clean.endswith(".tar.gz"):
        return "gz"
    if "." in clean.rsplit("/", 1)[-1]:
        cand = clean.rsplit(".", 1)[-1]
        if cand in KNOWN_FILE_EXTS:
            return cand
    fb = (fallback or "").strip().lower().lstrip(".")
    return fb if fb in KNOWN_FILE_EXTS else ""


def _archive_ext_from_formats(formats: object, mediatype: str) -> str:
    fmt_list = formats if isinstance(formats, list) else ([str(formats)] if formats else [])
    joined = " ".join(str(x).lower() for x in fmt_list)
    for token, ext in (
        ("pdf", "pdf"),
        ("epub", "epub"),
        ("comma-separated", "csv"),
        ("csv", "csv"),
        ("json", "json"),
        ("xml", "xml"),
        ("sqlite", "sqlite"),
        ("iso", "iso"),
        ("7z", "7z"),
        ("zip", "zip"),
        ("tar", "tar"),
        ("gzip", "gz"),
        ("djvu", "djvu"),
        ("text", "txt"),
    ):
        if token in joined:
            return ext
    if mediatype == "data":
        return "csv"
    if mediatype == "software":
        return "zip"
    return "pdf"


def fetch_archive_org_files(
    query_str: str,
    rows: int = 30,
    timeout: float = 7.0,
    file_types: Optional[List[str]] = None,
) -> List[SearchResult]:
    """Queries Internet Archive across texts, datasets, and software archives."""
    items: List[SearchResult] = []
    enabled, url, auth_headers = get_archive_endpoint("archive_org")
    if not enabled or not url:
        return items

    req_exts = {e.lower().lstrip(".") for e in (file_types or []) if e}
    mediatypes = ["texts", "data", "software"]
    if req_exts:
        selected = []
        if req_exts & DOC_EXTS:
            selected.append("texts")
        if req_exts & DATA_EXTS:
            selected.append("data")
        if req_exts & (ARCHIVE_EXTS | CODE_EXTS):
            selected.append("software")
        if selected:
            mediatypes = selected

    mt_clause = " OR ".join(f"mediatype:{mt}" for mt in mediatypes)
    params = {
        "q": f"({query_str}) AND ({mt_clause})",
        "fl[]": ["identifier", "title", "description", "format", "mediatype"],
        "rows": min(max(rows, 10), 80),
        "output": "json",
    }
    headers = {"User-Agent": "HecosDeepSearch/1.0", **auth_headers}
    try:
        resp = http_client.get(url, network="clearnet", params=params, headers=headers, timeout=min(timeout, 7.0))
        if resp.status_code != 200:
            return items
        docs = resp.json().get("response", {}).get("docs", [])
        for d in docs:
            ident = str(d.get("identifier") or "").strip()
            if not ident:
                continue
            title = d.get("title") or ident
            if isinstance(title, list):
                title = title[0] if title else ident
            desc = d.get("description") or ""
            if isinstance(desc, list):
                desc = " ".join(str(x) for x in desc)
            mediatype = str(d.get("mediatype") or "texts").lower()
            ext = _archive_ext_from_formats(d.get("format"), mediatype)
            page_url = f"https://archive.org/details/{ident}"
            items.append(SearchResult(
                title=f"[{ext.upper()}] {str(title).strip()}",
                url=page_url,
                snippet=(str(desc).strip()[:180] or f"Archive.org ({mediatype}): {ident}"),
                engine=f"archive_org:{mediatype}",
                category="files",
                network="clearnet",
                score=1.2,
                metadata={"extension": ext, "identifier": ident, "mediatype": mediatype},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:FILES_APIS] Archive.org note: {exc}")
    return items


def fetch_openalex_pdfs(query_str: str, rows: int = 20, timeout: float = 6.0) -> List[SearchResult]:
    """Fetches direct open-access academic/technical PDF links from OpenAlex."""
    items: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://api.openalex.org/works",
            network="clearnet",
            params={
                "search": query_str,
                "filter": "is_oa:true",
                "per-page": min(max(rows, 5), 30),
                "select": "id,title,publication_year,best_oa_location,open_access,primary_location",
            },
            headers={"User-Agent": "HecosDeepSearch/1.0 (mailto:search@hecos.local)"},
            timeout=min(timeout, 6.0),
        )
        if resp.status_code != 200:
            return items
        for work in resp.json().get("results", []):
            if not isinstance(work, dict):
                continue
            best = work.get("best_oa_location") or {}
            prim = work.get("primary_location") or {}
            oa = work.get("open_access") or {}
            pdf_url = best.get("pdf_url") or prim.get("pdf_url") or oa.get("oa_url") or best.get("landing_page_url") or ""
            title = str(work.get("title") or "").strip()
            if not (pdf_url and title and pdf_url.startswith(("http://", "https://"))):
                continue
            yr = work.get("publication_year") or ""
            ext = infer_extension(pdf_url, fallback="pdf")
            items.append(SearchResult(
                title=f"[{ext.upper()}] {title}",
                url=pdf_url,
                snippet=f"OpenAlex Open-Access Document ({yr}) — direct research file." if yr else "OpenAlex Open-Access Document.",
                engine="openalex:pdf",
                category="files",
                network="clearnet",
                score=1.4,
                metadata={"extension": ext, "date": str(yr) if yr else ""},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:FILES_APIS] OpenAlex note: {exc}")
    return items


def fetch_arxiv_pdfs(query_str: str, rows: int = 15, timeout: float = 6.0) -> List[SearchResult]:
    """Fetches direct arXiv PDF papers via Atom API."""
    items: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://export.arxiv.org/api/query",
            network="clearnet",
            params={"search_query": f"all:{query_str}", "start": 0, "max_results": min(max(rows, 5), 25)},
            headers={"User-Agent": "HecosDeepSearch/1.0"},
            timeout=min(timeout, 6.0),
        )
        if resp.status_code != 200 or not resp.text:
            return items
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            pub_el = entry.find("atom:published", ns)
            title = re.sub(r"\s+", " ", (title_el.text or "")).strip() if title_el is not None else ""
            summary = re.sub(r"\s+", " ", (summary_el.text or "")).strip() if summary_el is not None else ""
            pdf_url = ""
            for lnk in entry.findall("atom:link", ns):
                if lnk.attrib.get("title") == "pdf" or lnk.attrib.get("type") == "application/pdf":
                    pdf_url = lnk.attrib.get("href", "").strip()
                    break
            if not pdf_url:
                id_el = entry.find("atom:id", ns)
                if id_el is not None and id_el.text and "/abs/" in id_el.text:
                    pdf_url = id_el.text.strip().replace("/abs/", "/pdf/") + ".pdf"
            if title and pdf_url:
                items.append(SearchResult(
                    title=f"[PDF] {title}",
                    url=pdf_url,
                    snippet=summary[:200] or "arXiv Preprint PDF",
                    engine="arxiv:pdf",
                    category="files",
                    network="clearnet",
                    score=1.3,
                    metadata={"extension": "pdf", "date": (pub_el.text or "")[:10] if pub_el is not None else ""},
                ))
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:FILES_APIS] arXiv note: {exc}")
    return items


def fetch_huggingface_datasets(query_str: str, rows: int = 15, timeout: float = 6.0) -> List[SearchResult]:
    """Fetches open datasets (CSV/JSON/Parquet) from Hugging Face Datasets API."""
    items: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://huggingface.co/api/datasets",
            network="clearnet",
            params={"search": query_str, "limit": min(max(rows, 5), 25)},
            headers={"User-Agent": "HecosDeepSearch/1.0"},
            timeout=min(timeout, 6.0),
        )
        if resp.status_code != 200:
            return items
        data = resp.json()
        if not isinstance(data, list):
            return items
        for ds in data:
            ds_id = str(ds.get("id") or "").strip()
            if not ds_id:
                continue
            tags = [str(t).lower() for t in (ds.get("tags") or [])]
            ext = "csv" if any("csv" in t for t in tags) else ("parquet" if any("parquet" in t for t in tags) else "json")
            downloads = ds.get("downloads", 0)
            likes = ds.get("likes", 0)
            desc = str(ds.get("description") or "").replace("\n", " ").strip()
            snippet = desc[:160] if desc else f"Hugging Face Dataset — {downloads} downloads, {likes} likes."
            items.append(SearchResult(
                title=f"[{ext.upper()}] {ds_id}",
                url=f"https://huggingface.co/datasets/{ds_id}/tree/main",
                snippet=snippet,
                engine="huggingface:data",
                category="files",
                network="clearnet",
                score=1.25,
                metadata={"extension": ext, "downloads": downloads},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:FILES_APIS] HuggingFace note: {exc}")
    return items


def fetch_github_repos(query_str: str, rows: int = 15, timeout: float = 6.0) -> List[SearchResult]:
    """Fetches code repositories & release archives from GitHub Search API."""
    items: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://api.github.com/search/repositories",
            network="clearnet",
            params={"q": query_str, "sort": "stars", "order": "desc", "per_page": min(max(rows, 5), 25)},
            headers={"Accept": "application/vnd.github+json", "User-Agent": "HecosDeepSearch/1.0"},
            timeout=min(timeout, 6.0),
        )
        if resp.status_code != 200:
            return items
        for repo in resp.json().get("items", []):
            full_name = str(repo.get("full_name") or "").strip()
            html_url = str(repo.get("html_url") or "").strip()
            if not (full_name and html_url):
                continue
            lang = str(repo.get("language") or "").strip()
            ext = _LANG_TO_EXT.get(lang.lower(), "zip")
            stars = repo.get("stargazers_count", 0)
            desc = str(repo.get("description") or "").strip()
            items.append(SearchResult(
                title=f"[{ext.upper()}] {full_name}",
                url=html_url,
                snippet=f"{desc[:150]} (★ {stars}, {lang or 'Archive'})".strip() if desc else f"GitHub Repository (★ {stars}, {lang or 'Code'}).",
                engine="github:code",
                category="files",
                network="clearnet",
                score=1.35,
                metadata={"extension": ext, "language": lang, "stars": stars},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:FILES_APIS] GitHub note: {exc}")
    return items


def fetch_npm_packages(query_str: str, rows: int = 10, timeout: float = 5.0) -> List[SearchResult]:
    """Fetches JavaScript/TypeScript packages from npm Registry API."""
    items: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://registry.npmjs.org/-/v1/search",
            network="clearnet",
            params={"text": query_str, "size": min(max(rows, 5), 20)},
            headers={"User-Agent": "HecosDeepSearch/1.0"},
            timeout=min(timeout, 5.0),
        )
        if resp.status_code != 200:
            return items
        for obj in resp.json().get("objects", []):
            pkg = obj.get("package") or {}
            name = str(pkg.get("name") or "").strip()
            links = pkg.get("links") or {}
            url = str(links.get("npm") or (f"https://www.npmjs.com/package/{urllib.parse.quote(name)}" if name else "")).strip()
            if not (name and url):
                continue
            ver = pkg.get("version") or ""
            desc = str(pkg.get("description") or "").strip()
            items.append(SearchResult(
                title=f"[JS] {name} v{ver}" if ver else f"[JS] {name}",
                url=url,
                snippet=desc[:170] or f"npm package {name}",
                engine="npm:pkg",
                category="files",
                network="clearnet",
                score=1.1,
                metadata={"extension": "js", "version": ver},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:FILES_APIS] npm note: {exc}")
    return items


def fetch_wikimedia_files(query_str: str, rows: int = 15, timeout: float = 6.0) -> List[SearchResult]:
    """Searches Wikimedia Commons File namespace (namespace 6) for documents & media files."""
    items: List[SearchResult] = []
    enabled, url, auth_headers = get_archive_endpoint("wikimedia_commons")
    if not enabled or not url:
        return items
    try:
        resp = http_client.get(
            url,
            network="clearnet",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query_str,
                "srnamespace": 6,
                "srlimit": min(max(rows, 5), 25),
                "format": "json",
            },
            headers={"User-Agent": "HecosDeepSearch/1.0", **auth_headers},
            timeout=min(timeout, 6.0),
        )
        if resp.status_code != 200:
            return items
        for hit in resp.json().get("query", {}).get("search", []):
            title = str(hit.get("title") or "").strip()
            if not title:
                continue
            clean_name = title.replace(" ", "_")
            page_url = f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(clean_name, safe=':/_()-')}"
            ext = infer_extension(clean_name, fallback="")
            if not ext:
                continue
            raw_snip = re.sub(r"<[^>]+>", "", str(hit.get("snippet") or "")).strip()
            items.append(SearchResult(
                title=f"[{ext.upper()}] {title.removeprefix('File:')}",
                url=page_url,
                snippet=raw_snip[:170] or "Wikimedia Commons File",
                engine="wikimedia:files",
                category="files",
                network="clearnet",
                score=1.05,
                metadata={"extension": ext},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:FILES_APIS] Wikimedia files note: {exc}")
    return items


def fetch_zenodo_files(query_str: str, rows: int = 15, timeout: float = 7.0) -> List[SearchResult]:
    """Searches CERN Zenodo open repository for downloadable PDFs, datasets (CSV/ZIP/JSON), and code archives."""
    items: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://zenodo.org/api/records",
            network="clearnet",
            params={"q": query_str, "size": min(max(rows, 5), 25)},
            headers={"User-Agent": "HecosDeepSearch/1.0"},
            timeout=min(timeout, 7.0),
        )
        if resp.status_code != 200:
            return items
        hits = resp.json().get("hits", {}).get("hits", [])
        for rec in hits:
            meta = rec.get("metadata") or {}
            title = str(meta.get("title") or "").strip()
            files_list = rec.get("files") or []
            rec_url = (rec.get("links") or {}).get("html") or ""
            dl_url = ""
            ext = ""
            if files_list and isinstance(files_list[0], dict):
                f0 = files_list[0]
                dl_url = (f0.get("links") or {}).get("self") or rec_url
                ext = infer_extension(str(f0.get("key") or dl_url), fallback="")
            target_url = dl_url or rec_url
            if not (title and target_url):
                continue
            ext = ext or infer_extension(target_url, fallback="zip")
            raw_desc = re.sub(r"<[^>]+>", "", str(meta.get("description") or "")).strip()
            items.append(SearchResult(
                title=f"[{ext.upper()}] {title}",
                url=target_url,
                snippet=raw_desc[:170] or "Zenodo Open File & Dataset Repository",
                engine="zenodo:files",
                category="files",
                network="clearnet",
                score=1.22,
                metadata={"extension": ext},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:FILES_APIS] Zenodo note: {exc}")
    return items


def fetch_openlibrary_files(query_str: str, rows: int = 15, timeout: float = 6.0) -> List[SearchResult]:
    """Searches OpenLibrary for books & Archive.org downloadable texts/PDF/EPUB editions."""
    items: List[SearchResult] = []
    try:
        resp = http_client.get(
            "https://openlibrary.org/search.json",
            network="clearnet",
            params={"q": query_str, "limit": min(max(rows, 5), 25), "fields": "key,title,author_name,first_publish_year,ia"},
            headers={"User-Agent": "HecosDeepSearch/1.0"},
            timeout=min(timeout, 6.0),
        )
        if resp.status_code != 200:
            return items
        for doc in resp.json().get("docs", []):
            title = str(doc.get("title") or "").strip()
            key = str(doc.get("key") or "").strip()
            ia_list = doc.get("ia") or []
            if not title:
                continue
            if ia_list and isinstance(ia_list, list):
                url = f"https://archive.org/details/{urllib.parse.quote(str(ia_list[0]))}"
                ext = "pdf"
            elif key:
                url = f"https://openlibrary.org{key}"
                ext = "epub"
            else:
                continue
            authors = ", ".join(doc.get("author_name") or [])[:80]
            yr = doc.get("first_publish_year") or ""
            items.append(SearchResult(
                title=f"[{ext.upper()}] {title}",
                url=url,
                snippet=f"{authors} ({yr})".strip(" ()") or "OpenLibrary Ebook / Digital Edition",
                engine="openlibrary:docs",
                category="files",
                network="clearnet",
                score=1.1,
                metadata={"extension": ext},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:FILES_APIS] OpenLibrary note: {exc}")
    return items


def fetch_doaj_pdfs(query_str: str, rows: int = 15, timeout: float = 6.0) -> List[SearchResult]:
    """Searches Directory of Open Access Journals (DOAJ) for free full-text PDF articles."""
    items: List[SearchResult] = []
    try:
        q_enc = urllib.parse.quote(query_str, safe="")
        resp = http_client.get(
            f"https://doaj.org/api/search/articles/{q_enc}",
            network="clearnet",
            params={"pageSize": min(max(rows, 5), 25)},
            headers={"User-Agent": "HecosDeepSearch/1.0"},
            timeout=min(timeout, 6.0),
        )
        if resp.status_code != 200:
            return items
        for hit in resp.json().get("results", []):
            bib = hit.get("bibjson") or {}
            title = str(bib.get("title") or "").strip()
            links = bib.get("link") or []
            full_url = ""
            for ln in links:
                if isinstance(ln, dict) and ln.get("url"):
                    full_url = str(ln["url"]).strip()
                    if str(ln.get("content_type") or "").lower() == "pdf" or ".pdf" in full_url.lower():
                        break
            if not (title and full_url.startswith(("http://", "https://"))):
                continue
            ext = infer_extension(full_url, fallback="pdf")
            items.append(SearchResult(
                title=f"[{ext.upper()}] {title}",
                url=full_url,
                snippet=str(bib.get("abstract") or "DOAJ Open Access Article")[:170],
                engine="doaj:pdf",
                category="files",
                network="clearnet",
                score=1.15,
                metadata={"extension": ext},
            ))
    except Exception as exc:
        hecos_logger.debug(f"[SEARCH:FILES_APIS] DOAJ note: {exc}")
    return items


