import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict

try:
    from hecos.core.logging import logger
except ImportError:
    import logging
    logger = logging.getLogger("NotificationsHistory")

# DB is stored in data folder to survive package updates
_DATA_DIR = Path("C:/Hecos/hecos/data").resolve()
_DB_PATH = _DATA_DIR / "notifications_history.db"

def _get_db():
    # Ensure data dir exists
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    try:
        with _get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    subject TEXT,
                    status TEXT NOT NULL,
                    error_msg TEXT
                )
            """)
    except Exception as e:
        logger.error(f"[NOTIFICATIONS] Failed to initialize history DB: {e}")

# Initialize on import
_init_db()

def log_notification(event_type: str, destination: str, subject: str, status: str, error_msg: str = None):
    """
    Log a notification attempt.
    status should be 'SUCCESS' or 'ERROR'.
    """
    try:
        now_str = datetime.now().isoformat()
        with _get_db() as conn:
            conn.execute(
                "INSERT INTO history (timestamp, event_type, destination, subject, status, error_msg) VALUES (?, ?, ?, ?, ?, ?)",
                (now_str, event_type, destination, subject, status, error_msg)
            )
    except Exception as e:
        logger.error(f"[NOTIFICATIONS] Failed to log history: {e}")

def get_history(limit: int = 100) -> List[Dict]:
    """Retrieve the most recent notification history."""
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT id, timestamp, event_type, destination, subject, status, error_msg FROM history ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"[NOTIFICATIONS] Failed to get history: {e}")
        return []

def clear_history():
    """Clear all notification history."""
    try:
        with _get_db() as conn:
            conn.execute("DELETE FROM history")
    except Exception as e:
        logger.error(f"[NOTIFICATIONS] Failed to clear history: {e}")
