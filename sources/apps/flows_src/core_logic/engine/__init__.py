"""
Hecos Flows — Engine Package
=============================
Public facade that re-exports all symbols previously found in engine.py.

Any other module that did `from .engine import X` continues to work unchanged.
The actual implementations now live in dedicated sub-modules:

  event_bus.py      — SSE pub/sub, thread abort & active-run tracking
  input_gate.py     — Human-in-the-loop pause/resume gate
  evaluator.py      — Jinja2 rendering & boolean condition evaluation
  logic_handlers.py — Native LOGIC__ / CONTROL__ node implementations
  scheduler.py      — APScheduler cron/interval job management
  runner.py         — Topological sort, step executor, flow orchestrator
"""

# ── Re-export: event bus & abort ──────────────────────────────────────────────
from .event_bus import (
    FlowEventBus,
    FlowAbortException,
    FlowLogger,
    get_event_bus,
    abort_run,
    is_run_aborted,
    get_active_run,
    get_all_active_runs,
    register_child_run,
    _register_active_run,
    _unregister_active_run,
)

# ── Re-export: input gate ─────────────────────────────────────────────────────
from .input_gate import (
    register_pending_input,
    deliver_user_input,
    get_pending_input_value,
    get_all_pending_input_runs,
    _cancel_pending_input,
)

# ── Re-export: template evaluator ─────────────────────────────────────────────
from .evaluator import render, render_params, eval_condition

# ── Re-export: scheduler ──────────────────────────────────────────────────────
from .scheduler import schedule_flow, unschedule_flow, load_all_schedules

# ── Re-export: runner ─────────────────────────────────────────────────────────
from .runner import run_flow, run_flow_async, _execute_step

# ── Legacy aliases (used in some older call sites) ────────────────────────────
_render        = render
_render_params = render_params
_eval_condition = eval_condition

__all__ = [
    # event_bus
    "FlowEventBus", "FlowAbortException", "FlowLogger",
    "get_event_bus", "abort_run", "is_run_aborted",
    "get_active_run", "get_all_active_runs", "register_child_run",
    # input_gate
    "register_pending_input", "deliver_user_input",
    "get_pending_input_value", "get_all_pending_input_runs",
    # evaluator
    "render", "render_params", "eval_condition",
    # scheduler
    "schedule_flow", "unschedule_flow", "load_all_schedules",
    # runner
    "run_flow", "run_flow_async", "_execute_step",
]
