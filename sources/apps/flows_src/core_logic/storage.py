"""
Hecos Flows — Storage
=====================
CRUD operations for flow YAML files stored in workspace/flows/.
Each flow is a single .yaml file named after its flow ID (slug).
"""

import os
import re
import yaml
import datetime
import sqlite3
import json
from typing import Optional, Dict, List, Any

from hecos.core.logging import logger
class FlowLogger:
    def info(self, msg): logger.info("FLOWS", msg)
    def error(self, msg): logger.error("FLOWS", msg)
    def warning(self, msg): logger.debug("FLOWS", f"[WARN] {msg}")
    def debug(self, msg): logger.debug("FLOWS", msg)

log = FlowLogger()

# ── Locate workspace/flows directory ──────────────────────────────────────────

def _get_flows_dir() -> str:
    """Returns the absolute path to workspace/flows/, creating it if needed."""
    try:
        from hecos.core.constants import HECOS_DIR
        # ROOT_DIR is typically one level up from HECOS_DIR
        root_dir = os.path.normpath(os.path.join(HECOS_DIR, ".."))
        flows_dir = os.path.join(root_dir, "workspace", "flows")
    except Exception:
        flows_dir = os.path.join(os.getcwd(), "workspace", "flows")
    os.makedirs(flows_dir, exist_ok=True)
    return flows_dir


# ── Global Variables DB (KV Store) ──────────────────────────────────────────────

def _get_globals_db_path() -> str:
    return os.path.join(_get_flows_dir(), "flows_globals.db")

def _init_globals_db():
    db_path = _get_globals_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS global_vars (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def set_global_variable(key: str, value: Any) -> bool:
    """Save a global variable (auto-serialized to JSON)."""
    _init_globals_db()
    try:
        val_str = json.dumps(value)
        now = datetime.datetime.now().isoformat()
        conn = sqlite3.connect(_get_globals_db_path())
        c = conn.cursor()
        c.execute('''
            INSERT INTO global_vars (key, value, updated_at) 
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        ''', (key, val_str, now))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log.error(f"Failed to set global variable '{key}': {e}")
        return False

def get_global_variable(key: str, default: Any = None) -> Any:
    """Retrieve a global variable."""
    _init_globals_db()
    try:
        conn = sqlite3.connect(_get_globals_db_path())
        c = conn.cursor()
        c.execute('SELECT value FROM global_vars WHERE key = ?', (key,))
        row = c.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception as e:
        log.error(f"Failed to get global variable '{key}': {e}")
    return default


# ── Log Archive DB ──────────────────────────────────────────────────────────────

def _get_archive_db_path() -> str:
    return os.path.join(_get_flows_dir(), "flows_archive.db")

def _init_archive_db():
    db_path = _get_archive_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS log_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            flow_id TEXT NOT NULL,
            flow_name TEXT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            outcome TEXT,
            events TEXT,
            step_count INTEGER,
            error_msg TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_run_to_archive(run_id: str, flow_id: str, flow_name: str, started_at: str, ended_at: str, outcome: str, events: list, step_count: int, error_msg: str):
    """Save a run to the archive, keeping only the last 500 runs."""
    _init_archive_db()
    try:
        events_str = json.dumps(events)
        conn = sqlite3.connect(_get_archive_db_path())
        c = conn.cursor()
        c.execute('''
            INSERT INTO log_archive (run_id, flow_id, flow_name, started_at, ended_at, outcome, events, step_count, error_msg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (run_id, flow_id, flow_name, started_at, ended_at, outcome, events_str, step_count, error_msg))
        
        # Enforce max 500 retention
        c.execute('''
            DELETE FROM log_archive 
            WHERE id NOT IN (
                SELECT id FROM log_archive ORDER BY id DESC LIMIT 500
            )
        ''')
        
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"Failed to save run '{run_id}' to archive: {e}")

def list_archived_runs(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """List archived runs, sorted by newest first."""
    _init_archive_db()
    try:
        conn = sqlite3.connect(_get_archive_db_path())
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT id, run_id, flow_id, flow_name, started_at, ended_at, outcome, step_count, error_msg 
            FROM log_archive 
            ORDER BY id DESC LIMIT ? OFFSET ?
        ''', (limit, offset))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error(f"Failed to list archived runs: {e}")
        return []

def get_archived_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Get full details (including events) for a specific run."""
    _init_archive_db()
    try:
        conn = sqlite3.connect(_get_archive_db_path())
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM log_archive WHERE run_id = ?', (run_id,))
        row = c.fetchone()
        conn.close()
        if row:
            res = dict(row)
            if res.get("events"):
                try:
                    res["events"] = json.loads(res["events"])
                except Exception:
                    res["events"] = []
            return res
    except Exception as e:
        log.error(f"Failed to get archived run '{run_id}': {e}")
    return None



# ── Slug utilities ─────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert a display name to a safe file/ID slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:64]


def _path_for(flow_id: str) -> str:
    return os.path.join(_get_flows_dir(), f"{flow_id}.yaml")


# ── CRUD ───────────────────────────────────────────────────────────────────────

def list_flows() -> List[Dict[str, Any]]:
    """
    Returns a summary list of all flows.
    Each item: { id, name, description, enabled, trigger_type, last_run, version }
    """
    flows_dir = _get_flows_dir()
    result = []
    for fname in sorted(os.listdir(flows_dir)):
        if not fname.endswith(".yaml"):
            continue
        flow_id = fname[:-5]
        try:
            data = _load_yaml_file(os.path.join(flows_dir, fname))
            result.append({
                "id":           data.get("id", flow_id),
                "name":         data.get("name", flow_id),
                "description":  data.get("description", ""),
                "enabled":      data.get("enabled", True),
                "trigger_type": data.get("trigger", {}).get("type", "manual"),
                "trigger_expr": data.get("trigger", {}).get("expression", ""),
                "step_count":   len(data.get("pipeline", [])),
                "version":      data.get("version", 1),
                "last_run":     data.get("_meta", {}).get("last_run", None),
                "created_at":   data.get("_meta", {}).get("created_at", None),
                "updated_at":   data.get("_meta", {}).get("updated_at", None),
                "tags":         data.get("tags", []),
                "group":        data.get("group", "General"),
            })
        except Exception as e:
            log.warning(f"[Flows.Storage] Could not read {fname}: {e}")
    return result


def get_flow(flow_id: str) -> Optional[Dict[str, Any]]:
    """Load a single flow by ID. Returns None if not found."""
    path = _path_for(flow_id)
    if not os.path.exists(path):
        return None
    return _load_yaml_file(path)


def get_flow_yaml(flow_id: str) -> Optional[str]:
    """Return raw YAML string for a flow."""
    path = _path_for(flow_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_flow(flow_data: Dict[str, Any], raw_yaml: Optional[str] = None) -> str:
    """
    Save a flow to disk. Accepts either a dict (will be serialized) or a raw YAML string.
    Returns the flow_id.
    """
    if not flow_data.get("id"):
        name = flow_data.get("name", "unnamed_flow")
        flow_data["id"] = slugify(name)

    flow_id = flow_data["id"]
    path = _path_for(flow_id)

    # Update metadata
    now = datetime.datetime.now().isoformat()
    meta = flow_data.get("_meta", {})
    if not meta.get("created_at"):
        meta["created_at"] = now
    meta["updated_at"] = now
    flow_data["_meta"] = meta

    if raw_yaml:
        # Parse the YAML, inject only _meta (never touch pipeline), then re-serialize.
        # IMPORTANT: Do NOT call validate_flow here — it mutates depends_on in-place
        # which would corrupt the pipeline and cause nodes to disappear on disk.
        try:
            parsed = yaml.safe_load(raw_yaml)
            if isinstance(parsed, dict):
                parsed["_meta"] = meta
                parsed["id"] = flow_id
                with open(path, "w", encoding="utf-8") as f:
                    yaml.dump(parsed, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(raw_yaml)
        except Exception:
            # If YAML parsing fails, write the raw string as-is
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw_yaml)
    else:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(flow_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    log.debug(f"[Flows.Storage] Saved flow: {flow_id}")
    return flow_id


def delete_flow(flow_id: str) -> bool:
    """Delete a flow file. Returns True on success."""
    path = _path_for(flow_id)
    if os.path.exists(path):
        os.remove(path)
        log.info(f"[Flows.Storage] Deleted flow: {flow_id}")
        return True
    return False


def update_flow_field(flow_id: str, field: str, value: Any) -> bool:
    """Update a single top-level field (e.g. enabled, _meta.last_run)."""
    data = get_flow(flow_id)
    if data is None:
        return False
    if "." in field:
        parts = field.split(".", 1)
        sub = data.setdefault(parts[0], {})
        sub[parts[1]] = value
    else:
        data[field] = value
    save_flow(data)
    return True


# ── Internal helpers ────────────────────────────────────────────────────────────

def _load_yaml_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
        return yaml.load(f, Loader=loader) or {}
