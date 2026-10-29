"""
search/sessions.py
SQLite-backed search history and session persistence for Hecos Deep Search.
Stores queries, timing, engine statistics, and result payloads.
"""
from __future__ import annotations

import os
import json
import sqlite3
import threading
import logging
from typing import List, Dict, Any, Optional

from .models import SearchSession, SearchResult

logger = logging.getLogger("browser.search.sessions")


def _resolve_db_path() -> str:
    # Look for hecos/data
    here = os.path.dirname(os.path.abspath(__file__))
    hecos_root = os.path.normpath(os.path.join(here, "..", "..", ".."))
    data_dir = os.path.join(hecos_root, "data")
    if not os.path.isdir(data_dir):
        # Fallback to local package data
        data_dir = os.path.join(here, "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "search_history.db")


class SearchSessionStore:
    """Thread-safe SQLite store for Deep Search sessions."""

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
                    CREATE TABLE IF NOT EXISTS search_sessions (
                        id               TEXT PRIMARY KEY,
                        query            TEXT NOT NULL,
                        mode             TEXT NOT NULL,
                        engines_queried  TEXT,
                        total_results    INTEGER DEFAULT 0,
                        duration_ms      INTEGER DEFAULT 0,
                        created_at       TEXT NOT NULL,
                        results_json     TEXT,
                        is_favorite      INTEGER DEFAULT 0,
                        error            TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_search_created ON search_sessions(created_at DESC)")
                conn.commit()
        except Exception as e:
            logger.error(f"Error initializing search_history.db: {e}")

    def save_session(self, session: SearchSession) -> bool:
        """Persists a SearchSession into the database."""
        try:
            results_dicts = [r.to_dict() if isinstance(r, SearchResult) else r for r in session.results]
            results_json = json.dumps(results_dicts, ensure_ascii=False)
            engines_json = json.dumps(session.engines_queried)

            with self._lock, self._connect() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO search_sessions 
                    (id, query, mode, engines_queried, total_results, duration_ms, created_at, results_json, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session.id,
                    session.query,
                    session.mode,
                    engines_json,
                    len(session.results),
                    session.duration_ms,
                    session.created_at,
                    results_json,
                    session.error
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save search session {session.id}: {e}")
            return False

    def get_session(self, session_id: str) -> Optional[SearchSession]:
        """Loads a session by ID."""
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute("SELECT * FROM search_sessions WHERE id = ?", (session_id,)).fetchone()
                if not row:
                    return None

                results_raw = json.loads(row["results_json"] or "[]")
                results = [SearchResult.from_dict(r) for r in results_raw]
                engines = json.loads(row["engines_queried"] or "[]")

                session = SearchSession(
                    id=row["id"],
                    query=row["query"],
                    mode=row["mode"],
                    engines_queried=engines,
                    total_results=row["total_results"],
                    duration_ms=row["duration_ms"],
                    created_at=row["created_at"],
                    results=results,
                    error=row["error"]
                )
                return session
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    def list_sessions(self, limit: int = 50, favorite_only: bool = False) -> List[Dict[str, Any]]:
        """Returns list of sessions without large results blob for fast UI rendering."""
        try:
            with self._lock, self._connect() as conn:
                sql = """
                    SELECT id, query, mode, engines_queried, total_results, duration_ms, created_at, is_favorite, error 
                    FROM search_sessions
                """
                params = []
                if favorite_only:
                    sql += " WHERE is_favorite = 1"
                sql += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)

                rows = conn.execute(sql, params).fetchall()
                result = []
                for r in rows:
                    result.append({
                        "id": r["id"],
                        "query": r["query"],
                        "mode": r["mode"],
                        "engines_queried": json.loads(r["engines_queried"] or "[]"),
                        "total_results": r["total_results"],
                        "duration_ms": r["duration_ms"],
                        "created_at": r["created_at"],
                        "is_favorite": bool(r["is_favorite"]),
                        "error": r["error"]
                    })
                return result
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        try:
            with self._lock, self._connect() as conn:
                conn.execute("DELETE FROM search_sessions WHERE id = ?", (session_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    def clear_all(self) -> bool:
        try:
            with self._lock, self._connect() as conn:
                conn.execute("DELETE FROM search_sessions")
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to clear search sessions: {e}")
            return False

    def toggle_favorite(self, session_id: str) -> bool:
        try:
            with self._lock, self._connect() as conn:
                conn.execute("UPDATE search_sessions SET is_favorite = ((is_favorite | 1) - (is_favorite & 1)) WHERE id = ?", (session_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to toggle favorite for {session_id}: {e}")
            return False


_global_store: Optional[SearchSessionStore] = None
_store_lock = threading.Lock()

def get_session_store() -> SearchSessionStore:
    global _global_store
    if _global_store is None:
        with _store_lock:
            if _global_store is None:
                _global_store = SearchSessionStore()
    return _global_store
