"""
Hecos Flows — Flow Runner & Step Executor
==========================================
Orchestrates end-to-end execution of a flow pipeline:
  1. Topological sort of steps (respects depends_on relationships).
  2. Per-step execution with timeout, continue_on_error, and branch tracking.
  3. Cooperative and forceful abort via event_bus.
  4. SSE event emission throughout the run lifecycle.

Public API:
  run_flow(flow_data, run_id=None)  → synchronous blocking execution
  run_flow_async(flow_data)         → starts flow in a daemon thread, returns run_id immediately
"""

import concurrent.futures
import datetime
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional

from hecos.core.logging import logger
from .evaluator import render_params
from .event_bus import (
    FlowAbortException,
    _bus,
    _register_active_run,
    _unregister_active_run,
    is_run_aborted,
    get_event_bus,
)
from .logic_handlers import LOGIC_HANDLERS


class FlowLogger:
    def info(self, msg): logger.info("FLOWS", msg)
    def error(self, msg): logger.error("FLOWS", msg)
    def warning(self, msg): logger.debug("FLOWS", f"[WARN] {msg}")
    def debug(self, msg): logger.debug("FLOWS", msg)

log = FlowLogger()


# ── Topological sort ──────────────────────────────────────────────────────────

def _topological_sort(steps: List[Dict]) -> List[Dict]:
    """
    Sort pipeline steps by their depends_on relationships using DFS.
    Steps with no dependencies run first; dependent steps run after all parents.
    """
    step_map = {s["id"]: s for s in steps}
    visited  = set()
    order    = []

    def visit(step_id: str):
        if step_id in visited:
            return
        step = step_map.get(step_id)
        if step is None:
            return
        for dep in step.get("depends_on", []):
            dep_id = dep if isinstance(dep, str) else dep.get("node")
            if dep_id:
                visit(dep_id)
        visited.add(step_id)
        order.append(step)

    for step in steps:
        visit(step["id"])

    return order


# ── Step executor ─────────────────────────────────────────────────────────────

def _execute_step(
    step: Dict[str, Any],
    context: Dict[str, Any],
    run_id: str,
    emit: Callable,
) -> Any:
    """
    Execute a single pipeline step.

    Handles:
    - Disabled steps (skip or stop modes).
    - Timeout enforcement via ThreadPoolExecutor.
    - output_as context assignment.
    - continue_on_error flag.
    - SSE event emission (step_start, step_ok, step_error, step_skip).
    """
    action    = step.get("action", "")
    params    = render_params(step.get("params", {}), context)
    output_as = step.get("output_as")

    emit(run_id, {
        "type":    "step_start",
        "run_id":  run_id,
        "step_id": step["id"],
        "action":  action,
        "ts":      datetime.datetime.now().isoformat(),
    })

    # ── Disabled step handling ─────────────────────────────────────────────────
    if step.get("disabled", False):
        disable_mode = step.get("disable_mode", "skip")
        log.info(f"[Flows.Engine] ⏭️ Step '{step['id']}' bypassed (disabled). Mode: {disable_mode}")

        if step.get("action") == "CONTROL__start" and disable_mode == "stop":
            emit(run_id, {
                "type":    "step_error",
                "run_id":  run_id,
                "step_id": step["id"],
                "action":  action,
                "error":   "Start node is disabled! Please enable the start node to run the flow.",
                "ts":      datetime.datetime.now().isoformat(),
            })
        else:
            emit(run_id, {
                "type":    "step_skip",
                "run_id":  run_id,
                "step_id": step["id"],
                "action":  action,
                "ts":      datetime.datetime.now().isoformat(),
            })
        return "_BRANCH_STOPPED" if disable_mode == "stop" else None

    # ── Muted step handling (Audio nodes only) ─────────────────────────────────
    is_muted = step.get("muted", False) or step.get("params", {}).get("muted", False)
    is_muted = str(is_muted).lower() in ["true", "1", "yes"]
    is_audio = action.startswith("AUDIO__") or action.startswith("tts__") or action == "USER__ask_input"

    if is_audio and is_muted:
        log.info(f"[Flows.Engine] 🔇 Step '{step['id']}' is muted, skipping audio playback.")
        emit(run_id, {
            "type":    "step_ok", # Emit ok so it continues normally in UI, just without sound
            "run_id":  run_id,
            "step_id": step["id"],
            "action":  action,
            "output":  "[Muted]",
            "ts":      datetime.datetime.now().isoformat(),
        })
        return None

    # ── Normal execution ───────────────────────────────────────────────────────
    try:
        raw_params = step.get("params", {})
        timeout_val = params.get("timeout_seconds", raw_params.get("timeout_seconds", 0))
        timeout_seconds = int(timeout_val) if str(timeout_val).isdigit() else 0

        on_timeout_cont    = params.get("on_timeout_continue", raw_params.get("on_timeout_continue", False))
        on_timeout_continue = str(on_timeout_cont).lower() in ["true", "1", "yes"]

        def _run_action():
            if action in LOGIC_HANDLERS:
                handler   = LOGIC_HANDLERS[action]
                sig_args  = handler.__code__.co_varnames[:handler.__code__.co_argcount]
                kwargs    = {"step": step, "context": context}
                if "run_id" in sig_args: kwargs["run_id"] = run_id
                if "emit"   in sig_args: kwargs["emit"]   = emit
                return handler(**kwargs)
            else:
                import time
import sys as _time
                from ..registry import execute_action
                clean_params = {k: v for k, v in params.items()
                                if k not in ("timeout_seconds", "on_timeout_continue")}
                clean_params["_run_id"]           = run_id
                clean_params["_timeout_seconds"]  = timeout_seconds
                clean_params["_start_time"]       = _time.time()
                return execute_action(action, clean_params, context)

        if is_audio and not is_muted:
            emit(run_id, {
                "type": "audio_start",
                "run_id": run_id,
                "step_id": step["id"],
                "ts": datetime.datetime.now().isoformat(),
            })

        try:
            if timeout_seconds > 0:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(_run_action)
                    try:
                        result = future.result(timeout=timeout_seconds)
                    except concurrent.futures.TimeoutError:
                        log.warning(f"[Flows.Engine] Step '{step['id']}' timed out after {timeout_seconds}s.")
                        if on_timeout_continue:
                            log.info("[Flows.Engine] on_timeout_continue=True — proceeding gracefully.")
                            result = "[Timeout]"
                        else:
                            raise TimeoutError(f"Step '{step['id']}' timed out after {timeout_seconds} seconds.")
            else:
                result = _run_action()
        finally:
            if is_audio and not is_muted:
                emit(run_id, {
                    "type": "audio_stop",
                    "run_id": run_id,
                    "step_id": step["id"],
                    "ts": datetime.datetime.now().isoformat(),
                })

        if output_as and result is not None:
            context[output_as] = result

        emit(run_id, {
            "type":    "step_ok",
            "run_id":  run_id,
            "step_id": step["id"],
            "action":  action,
            "output":  str(result)[:512] if result is not None else None,
            "ts":      datetime.datetime.now().isoformat(),
        })
        return result

    except Exception as e:
        err_msg = str(e)
        log.error(f"[Flows.Engine] Step '{step['id']}' ({action}) failed: {err_msg}")

        continue_on_error = params.get("continue_on_error", step.get("params", {}).get("continue_on_error", False))
        continue_on_error = str(continue_on_error).lower() in ["true", "1", "yes"]

        emit(run_id, {
            "type":    "step_error",
            "run_id":  run_id,
            "step_id": step["id"],
            "action":  action,
            "error":   err_msg,
            "ts":      datetime.datetime.now().isoformat(),
        })

        if continue_on_error:
            log.warning(f"[Flows.Engine] continue_on_error=True — bypassing failure for '{step['id']}'.")
            if output_as:
                context[output_as] = f"[Error] {err_msg}"
            return f"[Error] {err_msg}"
        else:
            raise


# ── Flow orchestrator ─────────────────────────────────────────────────────────

def run_flow(flow_data: Dict[str, Any], run_id: Optional[str] = None) -> str:
    """
    Execute a flow dictionary synchronously (blocking).
    Emits SSE events to the global event bus throughout execution.

    Returns:
        run_id (str) — unique identifier for this execution.
    """
    if run_id is None:
        run_id = str(uuid.uuid4())[:8]

    flow_id   = flow_data.get("id", "unknown")
    pipeline  = flow_data.get("pipeline", [])
    variables = dict(flow_data.get("variables", {}))

    emit = _bus.emit
    _register_active_run(flow_id, run_id)

    emit(run_id, {
        "type":    "flow_start",
        "run_id":  run_id,
        "flow_id": flow_id,
        "ts":      datetime.datetime.now().isoformat(),
    })

    log.info(f"[Flows.Engine] ▶ Starting flow '{flow_id}' (run={run_id})")

    context = dict(variables)
    context["_run_id"]         = run_id
    context["_flow_id"]        = flow_id
    context["_branch_results"] = {}

    try:
        # Sort start nodes by priority, then apply topological sort
        pipeline.sort(
            key=lambda x: int(x.get("params", {}).get("priority", 0))
            if x.get("action") == "CONTROL__start" else 999
        )
        sorted_steps = _topological_sort(pipeline)
        skipped_nodes: set = set()

        has_start_nodes = any(s.get("action") == "CONTROL__start" for s in sorted_steps)

        if not has_start_nodes and len(sorted_steps) > 0:
            emit(run_id, {
                "type":    "toast",
                "level":   "warning",
                "message": "Start node is missing. Floating nodes will be ignored.",
            })

        # ── Group steps into parallel batches ───────────────────────────────────
        # A "batch" = all steps whose entire dependency set is already completed.
        # Within each batch, steps that don't depend on each other run concurrently.

        def _get_dep_ids(step):
            deps = []
            for dep in step.get("depends_on", []):
                if isinstance(dep, str):
                    deps.append(dep)
                elif isinstance(dep, dict):
                    deps.append(dep.get("node", ""))
            return deps

        completed: set = set()

        # Build execution batches (wave-by-wave parallelism)
        remaining = list(sorted_steps)
        while remaining:
            if is_run_aborted(run_id):
                log.info(f"[Flows.Engine] ⛔ Flow '{flow_id}' aborted (run={run_id})")
                emit(run_id, {
                    "type":    "flow_aborted",
                    "run_id":  run_id,
                    "flow_id": flow_id,
                    "ts":      datetime.datetime.now().isoformat(),
                })
                return run_id

            # Pick all steps whose deps are all completed/skipped
            ready = []
            not_ready = []
            all_done_and_skipped = completed | skipped_nodes
            for step in remaining:
                dep_ids = _get_dep_ids(step)
                if all(d in all_done_and_skipped for d in dep_ids):
                    ready.append(step)
                else:
                    not_ready.append(step)

            if not ready:
                # Deadlock guard: no progress possible, break
                log.warning(f"[Flows.Engine] ⚠ Deadlock guard: {[s['id'] for s in not_ready]} have unresolvable deps")
                break

            remaining = not_ready

            # Evaluate which ready steps should be skipped
            batch_to_run = []
            for step in ready:
                step_id    = step["id"]
                should_skip = False

                if not step.get("depends_on") and step.get("action") != "CONTROL__start":
                    should_skip = True

                for dep in step.get("depends_on", []):
                    if isinstance(dep, str):
                        if dep in skipped_nodes:
                            should_skip = True; break
                    elif isinstance(dep, dict):
                        parent_id  = dep.get("node")
                        req_branch = dep.get("branch")
                        if parent_id in skipped_nodes:
                            should_skip = True; break
                        actual_branch = context["_branch_results"].get(parent_id)
                        if actual_branch and req_branch and actual_branch != req_branch:
                            should_skip = True; break

                if should_skip:
                    skipped_nodes.add(step_id)
                    emit(run_id, {
                        "type":    "step_skipped",
                        "run_id":  run_id,
                        "step_id": step_id,
                        "action":  step.get("action", ""),
                        "ts":      datetime.datetime.now().isoformat(),
                    })
                    completed.add(step_id)
                else:
                    batch_to_run.append(step)

            if not batch_to_run:
                continue

            if len(batch_to_run) == 1:
                # Single step — run directly (no thread overhead)
                step = batch_to_run[0]
                res = _execute_step(step, context, run_id, emit)
                if res == "_BRANCH_STOPPED":
                    skipped_nodes.add(step["id"])
                completed.add(step["id"])
            else:
                # Multiple parallel steps — run them in threads
                log.info(f"[Flows.Engine] ⚡ Running {len(batch_to_run)} steps in parallel: {[s['id'] for s in batch_to_run]}")
                results_map: dict = {}
                exceptions_map: dict = {}

                def _run_parallel_step(s, ctx_snapshot):
                    try:
                        r = _execute_step(s, ctx_snapshot, run_id, emit)
                        results_map[s["id"]] = r
                    except Exception as ex:
                        exceptions_map[s["id"]] = ex

                # Use a shared context (thread-safe read, best-effort write)
                threads = []
                for s in batch_to_run:
                    t = threading.Thread(
                        target=_run_parallel_step,
                        args=(s, context),
                        daemon=True,
                        name=f"HecosFlow-{run_id}-{s['id']}",
                    )
                    threads.append(t)
                    t.start()

                for t in threads:
                    t.join()

                for step in batch_to_run:
                    sid = step["id"]
                    if sid in exceptions_map:
                        # Re-raise first exception (already emitted step_error in _execute_step)
                        raise exceptions_map[sid]
                    res = results_map.get(sid)
                    if res == "_BRANCH_STOPPED":
                        skipped_nodes.add(sid)
                    completed.add(sid)

        emit(run_id, {
            "type":    "flow_done",
            "run_id":  run_id,
            "flow_id": flow_id,
            "ts":      datetime.datetime.now().isoformat(),
        })
        log.info(f"[Flows.Engine] ✅ Flow '{flow_id}' completed (run={run_id})")

        # Persist last_run metadata
        try:
            from ..storage import update_flow_field
            update_flow_field(flow_id, "_meta.last_run", datetime.datetime.now().isoformat())
        except Exception:
            pass

    except FlowAbortException:
        log.info(f"[Flows.Engine] ☠️ Flow '{flow_id}' killed immediately (run={run_id})")
        emit(run_id, {
            "type":    "flow_aborted",
            "run_id":  run_id,
            "flow_id": flow_id,
            "ts":      datetime.datetime.now().isoformat(),
        })

    except Exception as e:
        emit(run_id, {
            "type":    "flow_error",
            "run_id":  run_id,
            "flow_id": flow_id,
            "error":   str(e),
            "ts":      datetime.datetime.now().isoformat(),
        })
        log.error(f"[Flows.Engine] ❌ Flow '{flow_id}' failed: {e}")

    finally:
        _unregister_active_run(flow_id, run_id)
        
        # Save to archive
        try:
            from ..storage import save_run_to_archive
            events = get_event_bus().subscribe(run_id)
            
            # Find outcome
            outcome = "done"
            error_msg = ""
            if is_run_aborted(run_id):
                outcome = "aborted"
            for ev in events:
                if ev.get("type") == "flow_error":
                    outcome = "error"
                    error_msg = ev.get("error", "")
            
            # Find times
            started_at = events[0].get("ts", "") if events else datetime.datetime.now().isoformat()
            ended_at = datetime.datetime.now().isoformat()
            
            # Count steps
            step_count = sum(1 for ev in events if ev.get("type") == "step_ok")
            
            save_run_to_archive(run_id, flow_id, flow_data.get("name", flow_id), started_at, ended_at, outcome, events, step_count, error_msg)
        except Exception as e:
            log.error(f"[Flows.Engine] Failed to save run to archive: {e}")

        emit(run_id, {"type": "stream_end", "run_id": run_id})

    return run_id


def run_flow_async(flow_data: Dict[str, Any]) -> str:
    """Start a flow in a background daemon thread. Returns the run_id immediately."""
    run_id = str(uuid.uuid4())[:8]
    t = threading.Thread(
        target=run_flow,
        args=(flow_data, run_id),
        daemon=True,
        name=f"HecosFlow-{run_id}",
    )
    t.start()
    return run_id
