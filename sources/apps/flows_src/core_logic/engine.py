"""
Hecos Flows — Engine (compatibility shim)
==========================================
This file is kept for backward compatibility with any import path that
references 'core_logic.engine' as a module rather than a package.

All implementation now lives in the 'engine/' sub-package.
This shim simply re-exports the full public surface so existing code
(flows_api.py, routes, etc.) continues to work without modification.
"""

# Re-export everything from the engine package
from .engine import *  # noqa: F401, F403
from .engine import (
    FlowEventBus,
    FlowAbortException,
    FlowLogger,
    get_event_bus,
    abort_run,
    is_run_aborted,
    get_active_run,
    get_all_active_runs,
    register_child_run,
    register_pending_input,
    deliver_user_input,
    get_pending_input_value,
    get_all_pending_input_runs,
    render,
    render_params,
    eval_condition,
    schedule_flow,
    unschedule_flow,
    load_all_schedules,
    run_flow,
    run_flow_async,
    _execute_step,
    # Legacy aliases
    _render,
    _render_params,
    _eval_condition,
)
