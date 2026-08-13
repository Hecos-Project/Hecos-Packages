from hecos.modules.flows.core_logic.registry import _REGISTRY, log, register_action
from typing import Any
import time

def _bootstrap_builtin_actions():
    """Register the core logic nodes that the engine handles natively."""

    builtin = [
        {
            "name": "LOGIC__if_else",
            "description": "Evaluates a list of Jinja2 logical expressions (branches). Executes the first branch that evaluates to True.",
            "params": {
                "branches": "list of strings (each a Jinja2 logical expression — use the visual Logic Builder)",
            },
            "category": "LOGIC",
            "icon": "🔀",
        },
        {
            "name": "LOGIC__switch",
            "description": "Routes execution to the branch whose key matches the evaluated expression value.",
            "params": {
                "expression": "string (Jinja2 expression that evaluates to a string key)",
                "branches":   "dict (key → action definition)",
                "default":    "dict (optional fallback action)",
            },
            "category": "LOGIC",
            "icon": "🔀",
        },
        {
            "name": "LOGIC__loop",
            "description": "Iterates over a list variable and executes the body action for each item.",
            "params": {
                "over":   "string (Jinja2 reference to a list variable, e.g. '{{ items }}')",
                "as_var": "string (loop variable name, e.g. 'item')",
                "body":   "dict (action + params executed on each iteration)",
            },
            "category": "LOGIC",
            "icon": "🔁",
        },
        {
            "name": "CONTROL__start",
            "description": "Explicit entry point for the flow. Flows containing this node will only execute nodes connected to it.",
            "params": {"priority": "integer"},
            "category": "LOGIC",
            "icon": "▶️",
        },
        {
            "name": "LOGIC__delay",
            "description": "Waits for the specified number of seconds before proceeding.",
            "params": {"seconds": "number"},
            "category": "LOGIC",
            "icon": "⏱️",
        },
        {
            "name": "LOGIC__set_variable",
            "description": "Sets or updates a flow-scoped variable. ⚠️ The 'name' field acts as the variable output name.",
            "params": {
                "name":  "string (Variable Name - REQUIRED, e.g. score)",
                "value": "any (Static value or Jinja2 expression, e.g. '{{ input_data }}')",
            },
            "category": "LOGIC",
            "icon": "📌",
        },
        {
            "name": "LOGIC__template",
            "description": "Renders a Jinja2 template string using flow variables and stores the result.",
            "params": {
                "template":  "string (Jinja2 template)",
                "output_as": "string (variable name to store result in)",
            },
            "category": "LOGIC",
            "icon": "📝",
        },

        {
            "name": "LOGIC__and_gate",
            "description": "Proceeds only if ALL listed conditions (Jinja2 boolean expressions) are True.",
            "params": {
                "conditions": "list[string] (Jinja2 boolean expressions)",
                "on_success": "dict (action to run if all conditions pass)",
                "on_fail":    "dict (optional action to run if any condition fails)",
            },
            "category": "LOGIC",
            "icon": "🔒",
        },
        {
            "name": "LOGIC__or_gate",
            "description": "Proceeds if AT LEAST ONE condition (Jinja2 boolean expression) is True.",
            "params": {
                "conditions": "list[string] (Jinja2 boolean expressions)",
                "on_success": "dict (action to run if any condition passes)",
                "on_fail":    "dict (optional action to run if all conditions fail)",
            },
            "category": "LOGIC",
            "icon": "🔓",
        },
        {
            "name": "LOGIC__http_request",
            "description": "Makes an HTTP request and stores the JSON response as a flow variable.",
            "params": {
                "method":    "string (GET, POST, PUT, DELETE)",
                "url":       "string (target URL, supports Jinja2)",
                "headers":   "dict (optional headers)",
                "body":      "dict|string (optional request body for POST/PUT)",
                "output_as": "string (variable name to store parsed JSON response)",
            },
            "category": "LOGIC",
            "icon": "🌐",
        },
        {
            "name": "LOGIC__abort",
            "description": "Immediately aborts the current flow execution.",
            "params": {
                "reason": "string (optional reason to log)"
            },
            "category": "LOGIC",
            "icon": "🛑",
        },
        {
            "name": "TRIGGER__cron",
            "description": "Schedules the flow using a cron expression (e.g. '0 7 * * *' = daily at 07:00).",
            "params": {"expression": "string (cron expression)"},
            "category": "TRIGGER",
            "icon": "🕐",
        },
        {
            "name": "TRIGGER__interval",
            "description": "Runs the flow every N seconds/minutes/hours.",
            "params": {
                "every":  "integer",
                "unit":   "string (seconds | minutes | hours)",
            },
            "category": "TRIGGER",
            "icon": "🔄",
        },
        {
            "name": "TRIGGER__manual",
            "description": "Flow runs only when explicitly triggered by the user or the FLOWS__run_flow command.",
            "params": {},
            "category": "TRIGGER",
            "icon": "▶️",
        },
    ]

    for action in builtin:
        _REGISTRY[action["name"]] = {
            "name":        action["name"],
            "description": action["description"],
            "params":      action["params"],
            "category":    action["category"],
            "icon":        action["icon"],
            "fn":          None,   # handled natively by the engine
        }



def _flows_run_flow(flow_id: str, wait: bool = True, pass_context: bool = True,
                    cascade_stop: bool = True, return_output: bool = False, **kwargs):
    try:
        from hecos.modules.flows.core_logic.storage import get_flow
        from hecos.modules.flows.core_logic.engine import run_flow, is_run_aborted, register_child_run, get_event_bus
        import time
        import uuid

        target_flow = get_flow(flow_id)
        if not target_flow:
            log.error(f"FLOWS__run_flow: Flow '{flow_id}' not found.")
            return False

        # Strip internal engine keys before passing as variables
        context_vars = {k: v for k, v in kwargs.items() if not k.startswith("_")}
        if pass_context:
            target_flow["variables"] = {**(target_flow.get("variables") or {}), **context_vars}

        sub_run_id = f"sub_{uuid.uuid4().hex[:8]}"
        parent_run_id = kwargs.get("_run_id")

        # Register the child so abort on the parent cascades to it
        if cascade_stop and parent_run_id:
            register_child_run(parent_run_id, sub_run_id)

        # ── Mirror sub-flow events to parent SSE channel ───────────────────────
        # Subscribe to the sub-flow's event queue and re-emit to parent with
        # an indentation prefix so the user sees sub-flow logs inline.
        _last_output = []  # mutable container to capture last step output

        if parent_run_id:
            bus = get_event_bus()
            sub_queue = bus.subscribe(sub_run_id)

            def _mirror_events():
                """Read sub-flow queue via index and forward events to parent channel."""
                import datetime
                idx = 0
                while True:
                    while idx < len(sub_queue):
                        ev = sub_queue[idx]
                        idx += 1
                        ev_type = ev.get("type", "")

                        # Capture last successful step output for return_output
                        if ev_type == "step_ok" and ev.get("output") is not None:
                            _last_output.clear()
                            _last_output.append(ev["output"])

                        # Forward to parent with sub-flow prefix
                        mirrored = dict(ev)
                        mirrored["_subflow"] = True
                        mirrored["_subflow_id"] = flow_id
                        mirrored["_subflow_name"] = target_flow.get("name", flow_id)
                        mirrored["_sub_run_id"] = sub_run_id

                        # Prefix text events so they appear indented in the log panel
                        if ev_type in ("step_start", "step_ok", "step_error", "step_skip", "step_skipped"):
                            sid = ev.get("step_id", "")
                            mirrored["step_id"] = f"  [{flow_id}] {sid}"

                        elif ev_type == "flow_start":
                            mirrored["type"] = "subflow_start"

                        elif ev_type in ("flow_done", "flow_aborted", "flow_error"):
                            # Translate to summary events on parent — keep going
                            pass

                        elif ev_type == "stream_end":
                            bus.emit(parent_run_id, mirrored)
                            return

                        bus.emit(parent_run_id, mirrored)

                    time.sleep(0.05)

        if wait:
            if parent_run_id:
                # Start mirroring in a daemon thread, run flow synchronously
                import threading
                mirror_t = threading.Thread(target=_mirror_events, daemon=True)
                mirror_t.start()
                run_flow(target_flow, run_id=sub_run_id)
                mirror_t.join(timeout=5)  # Wait for mirror to drain
            else:
                run_flow(target_flow, run_id=sub_run_id)

            if return_output and _last_output:
                return _last_output[0]
            return True
        else:
            # Run asynchronously in a daemon thread
            import threading
            if parent_run_id:
                def _run_and_mirror():
                    mirror_t = threading.Thread(target=_mirror_events, daemon=True)
                    mirror_t.start()
                    run_flow(target_flow, run_id=sub_run_id)
                    mirror_t.join(timeout=5)
                t = threading.Thread(target=_run_and_mirror, daemon=True)
            else:
                t = threading.Thread(target=run_flow, args=(target_flow, sub_run_id), daemon=True)
            t.start()
            return True

    except Exception as e:
        log.error(f"Cannot run flow {flow_id}: {e}")
        return False

_REGISTRY["FLOWS__run_flow"] = {
    "name": "FLOWS__run_flow",
    "description": "Executes another flow as a sub-flow. Sub-flow logs appear inline in the parent log. cascade_stop ensures stopping the parent also stops this sub-flow.",
    "params": {
        "flow_id":       "string (ID of the target flow to run — select from the dropdown)",
        "wait":          "boolean (true=wait for sub-flow to finish before proceeding, false=fire-and-forget)",
        "pass_context":  "boolean (true=pass current flow variables to the sub-flow)",
        "cascade_stop":  "boolean (true=stopping the parent also stops this sub-flow — default: true)",
        "return_output": "boolean (true=return the last step output of the sub-flow as the result of this node)",
    },
    "category": "FLOWS",
    "icon": "🔄",
    "fn": _flows_run_flow,
}


# ── Global Variables ───────────────────────────────────────────────────────────

@register_action(
    name="LOGIC__set_global",
    description="Sets a persistent global variable that survives flow restarts.",
    params={
        "key": "string (the variable name)",
        "value": "any (the value to store)"
    },
    category="LOGIC",
    icon="💾"
)
def _logic_set_global(key: str, value: Any, **kwargs):
    from hecos.modules.flows.core_logic.storage import set_global_variable
    if not key:
        return False
    return set_global_variable(key, value)


@register_action(
    name="LOGIC__get_global",
    description="Gets a persistent global variable.",
    params={
        "key": "string (the variable name)",
        "default": "any (value if not found)"
    },
    category="LOGIC",
    icon="📂"
)
def _logic_get_global(key: str, default: Any = None, **kwargs):
    from hecos.modules.flows.core_logic.storage import get_global_variable
    if not key:
        return default
    return get_global_variable(key, default)



# ── USER__ask_input ────────────────────────────────────────────────────────────

def _user_ask_input(
    prompt: str = "Please respond:",
    speak: bool = True,
    intercept_mode: str = "auto",   # "auto" | "explicit" | "api_only"
    multi_run_priority: str = "first",  # "first" | "all"
    **kwargs
):
    """
    Pauses the flow and waits for a user response via chat or voice.

    intercept_mode:
      - "auto"      → any chat message while this run is waiting is treated as the answer
      - "explicit"  → user must prefix with @flow (e.g. "@flow yes")
      - "api_only"  → only /api/flows/<run_id>/input endpoint counts (manual or programmatic)

    multi_run_priority:
      - "first"  → if multiple flows are waiting, the oldest (first) one gets the reply
      - "all"    → broadcast the same reply to all waiting flows simultaneously
    """
    import time

    run_id = kwargs.get("_run_id", "unknown")
    timeout_seconds = int(kwargs.get("_timeout_seconds", 0))
    start_time = kwargs.get("_start_time", time.time())

    try:
        from hecos.modules.flows.core_logic.engine import (
            register_pending_input,
            get_pending_input_value,
            is_run_aborted,
            get_event_bus,
        )

        # 1. Post the prompt to chat
        try:
            from hecos.memory.brain_interface import save_message
            save_message(
                role="assistant",
                message=prompt,
                user_id="admin",
                session_id=None,
                persona_name="Flows",
                broadcast_sse=True,
            )
        except Exception as e:
            log.warning(f"[USER__ask_input] Could not write to chat: {e}")

        # 2. Speak aloud if requested
        if speak:
            try:
                from hecos.core.audio import voice
                voice.speak(prompt)
            except Exception as e:
                log.warning(f"[USER__ask_input] TTS failed: {e}")

        # 3. Register this run as waiting for input + emit SSE event
        event = register_pending_input(
            run_id,
            kwargs.get("_flow_id", "unknown"),
            intercept_mode=intercept_mode,
            multi_run_priority=multi_run_priority
        )
        bus = get_event_bus()
        bus.emit(run_id, {
            "type":           "step_waiting_input",
            "run_id":         run_id,
            "prompt":         prompt,
            "intercept_mode": intercept_mode,
            "ts":             __import__("datetime").datetime.now().isoformat(),
        })

        # 4. Block the thread until answer arrives or timeout
        effective_timeout = None
        if timeout_seconds and timeout_seconds > 0:
            elapsed = time.time() - start_time
            remaining = timeout_seconds - elapsed
            if remaining > 0:
                effective_timeout = remaining
            else:
                effective_timeout = 0.1  # already expired

        answered = event.wait(timeout=effective_timeout)

        # 5. If aborted during wait, raise
        if is_run_aborted(run_id):
            from hecos.modules.flows.core_logic.engine import FlowAbortException
            raise FlowAbortException("Flow aborted while waiting for user input.")

        # 6. Retrieve the value
        value = get_pending_input_value(run_id)

        if not answered or value is None:
            log.warning(f"[USER__ask_input] Timed out waiting for input on run '{run_id}'.")
            return ""

        # 7. Echo reply into chat as a user message
        try:
            from hecos.memory.brain_interface import save_message
            save_message(
                role="user",
                message=value,
                user_id="admin",
                session_id=None,
                persona_name=None,
                broadcast_sse=True,
            )
        except Exception:
            pass

        log.info(f"[USER__ask_input] Got answer for run '{run_id}': {value[:80]}")
        return value

    except Exception as e:
        log.error(f"[USER__ask_input] Error: {e}")
        raise


_REGISTRY["USER__ask_input"] = {
    "name": "USER__ask_input",
    "description": (
        "Pauses the flow and waits for a user response (typed or spoken). "
        "The answer is stored in the output variable and can be used by LOGIC__if_else. "
        "intercept_mode controls how the answer is captured from chat."
    ),
    "params": {
        "prompt":             "string (Question to ask the user — shown in chat and spoken aloud)",
        "speak":              "boolean (Speak the prompt via TTS — default: true)",
        "intercept_mode":     "select:auto|explicit|api_only (How to capture the user reply from chat)",
        "multi_run_priority": "select:first|all (If multiple flows wait at once: answer only the first, or all)",
        "timeout_seconds":    "integer (Seconds to wait before giving up — 0 = wait forever)",
        "on_timeout_continue":"boolean (Continue with empty string on timeout instead of failing)",
    },
    "category": "USER",
    "icon": "🎤",
    "fn": _user_ask_input,
}


