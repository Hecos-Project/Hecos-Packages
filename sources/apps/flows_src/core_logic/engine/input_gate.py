"""
Hecos Flows — User Input Gate
==============================
Implements the pause/resume mechanism that allows running flows to block
and wait for a human response (e.g. chat input, UI button).

This is especially critical for narrative / interactive flows (Holodeck).
"""

import threading
from typing import Dict, List, Optional

from hecos.core.logging import logger


class FlowLogger:
    def info(self, msg): logger.info("FLOWS", msg)
    def error(self, msg): logger.error("FLOWS", msg)
    def warning(self, msg): logger.debug("FLOWS", f"[WARN] {msg}")
    def debug(self, msg): logger.debug("FLOWS", msg)

log = FlowLogger()


# Maps run_id → {"event": threading.Event, "value": str|None, "flow_id": str, ...}
_PENDING_INPUTS: Dict[str, Dict] = {}
_PENDING_INPUTS_LOCK = threading.Lock()


def register_pending_input(
    run_id: str,
    flow_id: str,
    intercept_mode: str = "auto",
    multi_run_priority: str = "first",
) -> threading.Event:
    """
    Register a run as waiting for user input.
    Returns the Event to block on — the calling thread should call event.wait().
    """
    event = threading.Event()
    with _PENDING_INPUTS_LOCK:
        _PENDING_INPUTS[run_id] = {
            "event":             event,
            "value":             None,
            "flow_id":           flow_id,
            "intercept_mode":    intercept_mode,
            "multi_run_priority": multi_run_priority,
        }
    log.info(f"[Flows.Engine] ⏸️ Run '{run_id}' waiting for user input (mode={intercept_mode}).")
    return event


def deliver_user_input(run_id: str, text: str) -> bool:
    """
    Called by the HTTP API when the user submits a response.
    Unblocks the waiting thread and passes the value.
    """
    with _PENDING_INPUTS_LOCK:
        entry = _PENDING_INPUTS.get(run_id)
    if entry is None:
        return False
    entry["value"] = text
    entry["event"].set()
    log.info(f"[Flows.Engine] ✅ User input delivered to run '{run_id}': {text[:60]}")
    return True


def get_pending_input_value(run_id: str) -> Optional[str]:
    """Retrieve the user's answer after the event has been set."""
    with _PENDING_INPUTS_LOCK:
        entry = _PENDING_INPUTS.get(run_id)
    return entry["value"] if entry else None


def _cancel_pending_input(run_id: str):
    """Unblock any waiting thread for this run (called on abort/finish)."""
    with _PENDING_INPUTS_LOCK:
        entry = _PENDING_INPUTS.pop(run_id, None)
    if entry:
        entry["event"].set()  # Unblock thread so it can exit cleanly


def get_all_pending_input_runs() -> List[Dict]:
    """Returns list of {run_id, flow_id} for all runs currently waiting for input."""
    with _PENDING_INPUTS_LOCK:
        return [{"run_id": rid, "flow_id": v["flow_id"]} for rid, v in _PENDING_INPUTS.items()]
