"""
search/bookmarks.py
Dedicated SQLite storage and management for Hecos Deep Search saved links and bookmarks.
Stores individual search results with full metadata, network tags, and timestamps.
"""
from __future__ import annotations

import os
import json
import uuid
import sqlite3
import threading
import logging
from typing import List, Dict, Any, Optional, Set

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.bookmarks")
logger = hecos_logger


def _resolve_db_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    hecos_root = os.path.normpath(os.path.join(here, "..", "..", ".."))
    data_dir = os.path.join(hecos_root, "data")
    if not os.path.isdir(data_dir):
        data_dir = os.path.join(here, "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "search_history.db")


class SearchBookmarkStore:
    """Thread-safe SQLite store for saved links and bookmarks."""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _resolve_db_path()
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._lock, self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS search_bookmarks (
                        id          TEXT PRIMARY KEY,
                        url         TEXT UNIQUE NOT NULL,
                        title       TEXT,
                        snippet     TEXT,
                        engine      TEXT,
                        network     TEXT DEFAULT 'clear',
                        category    TEXT DEFAULT 'web',
                        created_at  TEXT NOT NULL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_url ON search_bookmarks(url)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_created ON search_bookmarks(created_at DESC)")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize search_bookmarks table: {e}")

    def add_bookmark(self, url: str, title: str = "", snippet: str = "",
                     engine: str = "web", network: str = "clear",
                     category: str = "web") -> Dict[str, Any]:
        """Adds a bookmark or returns existing one."""
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        bookmark_id = str(uuid.uuid4())[:8]

        try:
            with self._lock, self._connect() as conn:
                # Upsert
                conn.execute("""
                    INSERT INTO search_bookmarks (id, url, title, snippet, engine, network, category, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        title = excluded.title,
                        snippet = excluded.snippet,
                        engine = excluded.engine,
                        network = excluded.network,
                        category = excluded.category
                """, (bookmark_id, url.strip(), title.strip(), snippet.strip(), engine, network, category, now))
                conn.commit()

            return {
                "id": bookmark_id,
                "url": url,
                "title": title,
                "snippet": snippet,
                "engine": engine,
                "network": network,
                "category": category,
                "created_at": now,
                "bookmarked": True
            }
        except Exception as e:
            logger.error(f"Failed to add bookmark {url}: {e}")
            return {"url": url, "bookmarked": False, "error": str(e)}

    def remove_bookmark(self, url: str) -> bool:
        """Removes a bookmark by its URL."""
        try:
            with self._lock, self._connect() as conn:
                conn.execute("DELETE FROM search_bookmarks WHERE url = ?", (url.strip(),))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to remove bookmark {url}: {e}")
            return False

    def remove_bookmark_by_id(self, bookmark_id: str) -> bool:
        """Removes a bookmark by its ID."""
        try:
            with self._lock, self._connect() as conn:
                conn.execute("DELETE FROM search_bookmarks WHERE id = ?", (bookmark_id.strip(),))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to remove bookmark by ID {bookmark_id}: {e}")
            return False

    def toggle_bookmark(self, url: str, title: str = "", snippet: str = "",
                        engine: str = "web", network: str = "clear",
                        category: str = "web") -> Dict[str, Any]:
        """Toggles bookmark status: removes if exists, adds if doesn't."""
        url = url.strip()
        if self.is_bookmarked(url):
            self.remove_bookmark(url)
            return {"url": url, "bookmarked": False}
        else:
            return self.add_bookmark(url, title, snippet, engine, network, category)

    def is_bookmarked(self, url: str) -> bool:
        """Checks if a URL is bookmarked."""
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute("SELECT 1 FROM search_bookmarks WHERE url = ? LIMIT 1", (url.strip(),)).fetchone()
                return bool(row)
        except Exception:
            return False

    def get_all_bookmarked_urls(self) -> Set[str]:
        """Returns set of all bookmarked URLs for quick UI lookup."""
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute("SELECT url FROM search_bookmarks").fetchall()
                return {r["url"] for r in rows}
        except Exception as e:
            logger.error(f"Failed to get bookmarked URLs: {e}")
            return set()

    def list_bookmarks(self, network: Optional[str] = None,
                       category: Optional[str] = None,
                       search_term: Optional[str] = None,
                       limit: int = 200) -> List[Dict[str, Any]]:
        """Lists bookmarks with optional network/category filtering."""
        try:
            with self._lock, self._connect() as conn:
                sql = "SELECT id, url, title, snippet, engine, network, category, created_at FROM search_bookmarks WHERE 1=1"
                params = []
                if network:
                    sql += " AND network = ?"
                    params.append(network)
                if category:
                    sql += " AND category = ?"
                    params.append(category)
                if search_term:
                    sql += " AND (title LIKE ? OR snippet LIKE ? OR url LIKE ?)"
                    q = f"%{search_term}%"
                    params.extend([q, q, q])

                sql += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)

                rows = conn.execute(sql, params).fetchall()
                result = []
                for r in rows:
                    result.append({
                        "id": r["id"],
                        "url": r["url"],
                        "title": r["title"] or r["url"],
                        "snippet": r["snippet"] or "",
                        "engine": r["engine"] or "web",
                        "network": r["network"] or "clear",
                        "category": r["category"] or "web",
                        "created_at": r["created_at"]
                    })
                return result
        except Exception as e:
            logger.error(f"Failed to list bookmarks: {e}")
            return []

    def get_count(self) -> int:
        """Returns total number of bookmarks."""
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) AS c FROM search_bookmarks").fetchone()
                return row["c"] if row else 0
        except Exception:
            return 0


_global_store: Optional[SearchBookmarkStore] = None
_store_lock = threading.Lock()


def get_bookmark_store() -> SearchBookmarkStore:
    global _global_store
    if _global_store is None:
        with _store_lock:
            if _global_store is None:
                _global_store = SearchBookmarkStore()
    return _global_store
