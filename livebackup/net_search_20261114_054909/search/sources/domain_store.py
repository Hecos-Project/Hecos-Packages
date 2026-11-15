"""
search/sources/domain_store.py
High-speed SQLite index for massive bare-domain compilations (blocklists, allowlists, directories)
such as GitHub domain lists (400k+ domains) without bloating YAML/JSON configs or browser DOM.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
import urllib.parse
from typing import Any, Dict, Iterable, List, Set, Tuple

logger = logging.getLogger("browser.search.sources.domain_store")

_DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.IGNORECASE)


def _get_db_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "domain_lists.sqlite")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_get_db_path(), timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS domain_sources (
            source_id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            domain_count INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS domain_entries (
            source_id TEXT NOT NULL,
            role TEXT NOT NULL,
            domain TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            PRIMARY KEY (role, domain)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_entries_src ON domain_entries(source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_entries_dom ON domain_entries(domain)")
    return conn


def normalize_domain(raw: str) -> str:
    val = (raw or "").strip().lower()
    if not val:
        return ""
    if "://" in val:
        try:
            val = urllib.parse.urlsplit(val).hostname or ""
        except Exception:
            return ""
    val = val.split("/", 1)[0].split(":", 1)[0].strip(".")
    if val.startswith("www."):
        val = val[4:]
    if not val or "." not in val or len(val) > 253:
        return ""
    if not _DOMAIN_RE.match(val):
        return ""
    return val


def insert_domains(
    source_id: str,
    role: str,
    domains: Iterable[str],
    category: str = "general",
    dry_run: bool = False,
) -> Tuple[int, int, int]:
    """
    Bulk-inserts deduplicated domains into SQLite.
    Returns `(parsed_valid, added, skipped_duplicates)`.
    When `dry_run=True`, runs inside a rolled-back transaction so counts are exact without persisting.
    """
    eff_role = role if role in ("blocklist", "allowlist", "directory") else "blocklist"
    eff_src = source_id or "__dry_run__"
    rows: List[Tuple[str, str, str, str]] = []
    seen_batch: Set[str] = set()
    skipped_in_batch = 0

    for d in domains:
        nd = normalize_domain(d)
        if not nd:
            continue
        if nd in seen_batch:
            skipped_in_batch += 1
            continue
        seen_batch.add(nd)
        rows.append((eff_src, eff_role, nd, category))

    parsed_valid = len(seen_batch) + skipped_in_batch
    if not rows:
        return parsed_valid, 0, skipped_in_batch

    conn = _connect()
    try:
        conn.execute("BEGIN")
        if not dry_run:
            conn.execute(
                "DELETE FROM domain_entries WHERE source_id = ? AND role != ?",
                (eff_src, eff_role),
            )
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO domain_entries(source_id, role, domain, category) VALUES (?, ?, ?, ?)",
            rows,
        )
        added = conn.total_changes - before

        if dry_run:
            conn.rollback()
        else:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM domain_entries WHERE source_id = ?",
                (eff_src,),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO domain_sources(source_id, role, enabled, domain_count, updated_at)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    role = excluded.role,
                    domain_count = excluded.domain_count,
                    updated_at = excluded.updated_at
                """,
                (eff_src, eff_role, cnt, int(time.time())),
            )
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

    skipped_duplicates = (len(rows) - added) + skipped_in_batch
    logger.debug(
        f"[DomainStore] insert source={eff_src} role={eff_role} dry_run={dry_run}: "
        f"valid={parsed_valid} added={added} skipped_dups={skipped_duplicates}"
    )
    return parsed_valid, added, skipped_duplicates


def remove_domains_for_source(source_id: str) -> int:
    if not source_id:
        return 0
    conn = _connect()
    try:
        before = conn.total_changes
        conn.execute("DELETE FROM domain_entries WHERE source_id = ?", (source_id,))
        removed = conn.total_changes - before
        conn.execute("DELETE FROM domain_sources WHERE source_id = ?", (source_id,))
        conn.commit()
        logger.debug(f"[DomainStore] Removed {removed} domain entries for source={source_id}")
        return removed
    finally:
        conn.close()


def set_source_enabled(source_id: str, enabled: bool) -> int:
    if not source_id:
        return 0
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE domain_sources SET enabled = ? WHERE source_id = ?",
            (1 if enabled else 0, source_id),
        )
        cnt = conn.execute(
            "SELECT COUNT(*) FROM domain_entries WHERE source_id = ?",
            (source_id,),
        ).fetchone()[0]
        conn.commit()
        logger.debug(f"[DomainStore] Set enabled={enabled} for source={source_id} (entries={cnt})")
        return cnt if cur.rowcount else 0
    finally:
        conn.close()


def _host_candidates(host_or_url: str) -> List[str]:
    host = normalize_domain(host_or_url)
    if not host:
        return []
    parts = host.split(".")
    out = [host]
    # Also test parent domains (e.g., video.xhamster.com -> xhamster.com)
    for i in range(1, len(parts) - 1):
        out.append(".".join(parts[i:]))
    return out


def filter_blocked_hosts(urls_or_hosts: Iterable[str]) -> Set[str]:
    """
    Given an iterable of URLs or hostnames, returns the subset of input strings
    whose domain (or parent domain) matches an active `blocklist` entry and is not allowlisted.
    """
    items = list(urls_or_hosts)
    if not items or not os.path.isfile(_get_db_path()):
        return set()

    item_to_cands: Dict[str, List[str]] = {}
    all_cands: Set[str] = set()
    for raw in items:
        cands = _host_candidates(raw)
        if cands:
            item_to_cands[raw] = cands
            all_cands.update(cands)

    if not all_cands:
        return set()

    conn = _connect()
    try:
        cand_list = list(all_cands)
        blocked_domains: Set[str] = set()
        allowed_domains: Set[str] = set()

        # Chunk IN queries below SQLite 999-parameter limit
        chunk_size = 450
        for idx in range(0, len(cand_list), chunk_size):
            chunk = cand_list[idx : idx + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT de.domain, de.role
                FROM domain_entries de
                LEFT JOIN domain_sources ds ON ds.source_id = de.source_id
                WHERE de.domain IN ({placeholders})
                  AND COALESCE(ds.enabled, 1) = 1
                  AND de.role IN ('blocklist', 'allowlist')
                """,
                chunk,
            ).fetchall()
            for dom, role in rows:
                if role == "blocklist":
                    blocked_domains.add(dom)
                elif role == "allowlist":
                    allowed_domains.add(dom)
    finally:
        conn.close()

    if not blocked_domains:
        return set()

    blocked_inputs: Set[str] = set()
    for raw, cands in item_to_cands.items():
        if any(c in allowed_domains for c in cands):
            continue
        if any(c in blocked_domains for c in cands):
            blocked_inputs.add(raw)
    return blocked_inputs


def search_domains(keyword: str, role: str = "all", limit: int = 50) -> List[Dict[str, str]]:
    kw = (keyword or "").strip().lower()
    if not kw or not os.path.isfile(_get_db_path()):
        return []
    conn = _connect()
    try:
        if role in ("blocklist", "allowlist", "directory"):
            rows = conn.execute(
                """
                SELECT de.domain, de.role, de.category, de.source_id
                FROM domain_entries de
                LEFT JOIN domain_sources ds ON ds.source_id = de.source_id
                WHERE COALESCE(ds.enabled, 1) = 1 AND de.role = ? AND de.domain LIKE ?
                LIMIT ?
                """,
                (role, f"%{kw}%", max(1, min(int(limit), 200))),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT de.domain, de.role, de.category, de.source_id
                FROM domain_entries de
                LEFT JOIN domain_sources ds ON ds.source_id = de.source_id
                WHERE COALESCE(ds.enabled, 1) = 1 AND de.domain LIKE ?
                LIMIT ?
                """,
                (f"%{kw}%", max(1, min(int(limit), 200))),
            ).fetchall()
        return [{"domain": r[0], "role": r[1], "category": r[2], "source_id": r[3]} for r in rows]
    finally:
        conn.close()


def set_source_role(source_id: str, new_role: str) -> int:
    """Switches an indexed source's role ('blocklist' | 'allowlist' | 'directory') in SQLite without re-downloading."""
    eff_role = new_role if new_role in ("blocklist", "allowlist", "directory") else ""
    if not source_id or not eff_role or not os.path.isfile(_get_db_path()):
        return 0
    conn = _connect()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE OR IGNORE domain_entries SET role = ? WHERE source_id = ? AND role != ?",
            (eff_role, source_id, eff_role),
        )
        conn.execute(
            "DELETE FROM domain_entries WHERE source_id = ? AND role != ?",
            (source_id, eff_role),
        )
        cnt = conn.execute(
            "SELECT COUNT(*) FROM domain_entries WHERE source_id = ? AND role = ?",
            (source_id, eff_role),
        ).fetchone()[0]
        conn.execute(
            "UPDATE domain_sources SET role = ?, domain_count = ?, updated_at = ? WHERE source_id = ?",
            (eff_role, cnt, int(time.time()), source_id),
        )
        conn.commit()
        return cnt
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        conn.close()


_NOISE_TOKENS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "you", "your",
    "are", "not", "all", "new", "hot", "top", "best", "free", "full",
    "online", "watch", "video", "videos", "movie", "movies", "site", "sites",
})
_PREFERRED_TLDS = (".com", ".net", ".org", ".tv", ".xxx", ".tube", ".porn", ".live", ".io")
_LOW_SIGNAL_HOSTS = (".pages.dev", ".blogspot.", ".wordpress.", ".github.io", ".netlify.app", ".vercel.app", ".tumblr.com")


def query_matching_domains(
    tokens: Iterable[str],
    role: str = "directory",
    limit: int = 35,
) -> List[Dict[str, Any]]:
    """
    Fast indexed search for active domains matching query tokens.
    Scores multi-token matches, short clean TLDs, and penalizes digit-prefixed / subdomain spam.
    """
    if not os.path.isfile(_get_db_path()):
        return []

    eff_role = role if role in ("blocklist", "allowlist", "directory") else "directory"
    clean_tokens: List[str] = []
    seen_tok: Set[str] = set()
    for raw in tokens:
        t = re.sub(r"[^a-z0-9]", "", (raw or "").strip().lower())
        if len(t) < 3 or t in _NOISE_TOKENS or t in seen_tok:
            continue
        seen_tok.add(t)
        clean_tokens.append(t)
        if len(clean_tokens) >= 6:
            break

    if not clean_tokens:
        return []

    conn = _connect()
    try:
        has_any = conn.execute(
            """
            SELECT 1 FROM domain_entries de
            LEFT JOIN domain_sources ds ON ds.source_id = de.source_id
            WHERE de.role = ? AND COALESCE(ds.enabled, 1) = 1
            LIMIT 1
            """,
            (eff_role,),
        ).fetchone()
        if not has_any:
            return []

        candidates: Dict[str, Dict[str, Any]] = {}
        for tok in clean_tokens:
            rows = conn.execute(
                """
                SELECT de.domain, de.category, de.source_id
                FROM domain_entries de
                LEFT JOIN domain_sources ds ON ds.source_id = de.source_id
                WHERE de.role = ?
                  AND COALESCE(ds.enabled, 1) = 1
                  AND de.domain LIKE ?
                LIMIT 250
                """,
                (eff_role, f"%{tok}%"),
            ).fetchall()
            for dom, cat, src_id in rows:
                entry = candidates.get(dom)
                if entry is None:
                    candidates[dom] = {
                        "domain": dom,
                        "category": cat or "general",
                        "source_id": src_id or "",
                        "matched_tokens": [tok],
                    }
                elif tok not in entry["matched_tokens"]:
                    entry["matched_tokens"].append(tok)

        # Also gather a handful of clean, short flagship domains from the directory to broaden site: fan-out
        if len(candidates) < max(limit * 2, 40):
            hub_rows = conn.execute(
                """
                SELECT de.domain, de.category, de.source_id
                FROM domain_entries de
                LEFT JOIN domain_sources ds ON ds.source_id = de.source_id
                WHERE de.role = ?
                  AND COALESCE(ds.enabled, 1) = 1
                  AND length(de.domain) BETWEEN 6 AND 15
                  AND de.domain GLOB '[a-z]*.com'
                LIMIT 40
                """,
                (eff_role,),
            ).fetchall()
            for dom, cat, src_id in hub_rows:
                if dom not in candidates and "-" not in dom and dom.count(".") == 1:
                    candidates[dom] = {
                        "domain": dom,
                        "category": cat or "general",
                        "source_id": src_id or "",
                        "matched_tokens": [],
                    }
    finally:
        conn.close()

    scored: List[Dict[str, Any]] = []
    for item in candidates.values():
        dom = item["domain"]
        stem = dom.split(".", 1)[0]
        mt = item["matched_tokens"]
        score = len(mt) * 50.0
        for tok in mt:
            score += min(len(tok), 12) * 1.5
            if stem.startswith(tok) or tok == stem:
                score += 12.0

        if any(dom.endswith(tld) for tld in _PREFERRED_TLDS):
            score += 14.0
        if dom.count(".") == 1 and stem.isalpha() and len(stem) <= 18:
            score += 12.0
        elif len(dom) <= 22:
            score += 5.0

        if stem[:3].isdigit() or dom[0].isdigit():
            score -= 28.0
        if dom.count("-") >= 2:
            score -= 18.0
        if dom.count(".") >= 2 or len(dom) > 32:
            score -= 20.0
        if any(bad in dom for bad in _LOW_SIGNAL_HOSTS):
            score -= 40.0

        item["score"] = round(score, 2)
        scored.append(item)

    scored.sort(key=lambda x: (x["score"], -len(x["domain"])), reverse=True)
    return scored[:max(1, int(limit))]


def get_summary() -> Dict[str, Any]:
    if not os.path.isfile(_get_db_path()):
        return {"total_domains": 0, "by_role": {}, "by_source": {}}
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT role, COUNT(*) FROM domain_entries GROUP BY role"
        ).fetchall()
        by_role = {r[0]: r[1] for r in rows}
        src_rows = conn.execute(
            "SELECT source_id, role, domain_count, enabled FROM domain_sources"
        ).fetchall()
        by_source = {
            r[0]: {"role": r[1], "count": int(r[2] or 0), "enabled": bool(r[3])}
            for r in src_rows
        }
        return {"total_domains": sum(by_role.values()), "by_role": by_role, "by_source": by_source}
    finally:
        conn.close()

