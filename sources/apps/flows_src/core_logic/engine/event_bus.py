"""
Hecos Flows — SSE Event Bus & Thread Abort
==========================================
Manages a lightweight pub/sub bus for streaming real-time execution events
to SSE clients, and provides cooperative & forceful thread-abort primitives.
"""

import ctypes
import threading
from typing import Any, Dict, Optional

from hecos.core.logging import logger


class FlowLogger:
    def info(self, msg): logger.info("FLOWS", msg)
    def error(self, msg): logger.error("FLOWS", msg)
    def warning(self, msg): logger.debug("FLOWS", f"[WARN] {msg}")
    def debug(self, msg): logger.debug("FLOWS", msg)

log = FlowLogger()


# ── SSE Event Bus ──────────────────────────────────────────────────────────────

class FlowEventBus:
    """
    Lightweight pub/sub bus for streaming execution events to SSE clients.
    Each active run gets its own queue that the SSE endpoint consumes.
    """

    def __init__(self):
        self._queues: Dict[str, list] = {}
        self._lock = threading.Lock()

    def subscribe(self, run_id: str) -> list:
        with self._lock:
            if run_id not in self._queues:
                self._queues[run_id] = []
            return self._queues[run_id]

    def unsubscribe(self, run_id: str):
        # We no longer aggressively pop the queue here, because multiple clients 
        # (or reconnections) might need the history of the run.
        pass

    def emit(self, run_id: str, event: Dict[str, Any]):
        with self._lock:
            if run_id not in self._queues:
                self._queues[run_id] = []
            self._queues[run_id].append(event)


# Singleton bus
_bus = FlowEventBus()

def get_event_bus() -> FlowEventBus:
    return _bus


# ── Abort / active-run tracking ────────────────────────────────────────────────

class FlowAbortException(Exception):
    """Raised inside a flow thread to immediately kill execution."""
    pass


_aborted_runs: set = set()           # run_ids that should be cancelled
_active_runs: Dict[str, str] = {}    # flow_id → run_id
_active_runs_lock = threading.Lock()
_run_threads: Dict[str, int] = {}    # run_id → thread native_id
_run_threads_lock = threading.Lock()
_run_children: Dict[str, set] = {}   # parent_run_id → {child_run_ids}
_run_children_lock = threading.Lock()


def _inject_exception(thread_id: int, exc_type: type) -> bool:
    """Use ctypes to raise an exception in the target thread."""
    ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_id),
        ctypes.py_object(exc_type)
    )
    if ret == 0:
        log.warning(f"[Flows.Engine] _inject_exception: thread {thread_id} not found.")
        return False
    elif ret > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_id), None)
        log.error(f"[Flows.Engine] _inject_exception: unexpected result {ret}, reverted.")
        return False
    return True


def abort_run(run_id: str):
    """Immediately kill a running flow and all registered children (cascade stop)."""
    _aborted_runs.add(run_id)

    # ── Cascade: abort all child sub-runs first ────────────────────────────────
    with _run_children_lock:
        children = set(_run_children.get(run_id, set()))
    for child_run_id in children:
        log.info(f"[Flows.Engine] ☠️ Cascade aborting child run '{child_run_id}' (parent={run_id})")
        abort_run(child_run_id)

    # ── Kill the parent thread ─────────────────────────────────────────────────
    with _run_threads_lock:
        thread_id = _run_threads.get(run_id)
    if thread_id is not None:
        _inject_exception(thread_id, FlowAbortException)
        log.info(f"[Flows.Engine] ☠️ Injected FlowAbortException into thread {thread_id} (run={run_id})")

    # Unblock any pending input gate so the thread can exit cleanly
    from .input_gate import _cancel_pending_input
    _cancel_pending_input(run_id)


def is_run_aborted(run_id: str) -> bool:
    return run_id in _aborted_runs


def get_active_run(flow_id: str) -> Optional[str]:
    """Return the current run_id for flow_id, or None if not running."""
    with _active_runs_lock:
        return _active_runs.get(flow_id)


def _register_active_run(flow_id: str, run_id: str):
    with _active_runs_lock:
        _active_runs[flow_id] = run_id
    with _run_threads_lock:
        _run_threads[run_id] = threading.current_thread().ident


def _unregister_active_run(flow_id: str, run_id: str):
    with _active_runs_lock:
        if _active_runs.get(flow_id) == run_id:
            del _active_runs[flow_id]
    with _run_threads_lock:
        _run_threads.pop(run_id, None)
    _aborted_runs.discard(run_id)
    with _run_children_lock:
        _run_children.pop(run_id, None)
        for parent_children in _run_children.values():
            parent_children.discard(run_id)
    from .input_gate import _cancel_pending_input
    _cancel_pending_input(run_id)


def register_child_run(parent_run_id: str, child_run_id: str):
    """Link a child sub-run to its parent so abort_run() can cascade."""
    with _run_children_lock:
        if parent_run_id not in _run_children:
            _run_children[parent_run_id] = set()
        _run_children[parent_run_id].add(child_run_id)
    log.info(f"[Flows.Engine] 🔗 Registered child run '{child_run_id}' under parent '{parent_run_id}'")


def get_all_active_runs() -> Dict[str, str]:
    """Return a snapshot of all currently active {flow_id: run_id} pairs."""
    with _active_runs_lock:
        return dict(_active_runs)
