"""
Hecos Flows — Action Registry
==============================
Central catalog of all actions available inside a Flow pipeline.

Usage:
    from hecos.modules.flows.core_logic.registry import register_action, get_catalog, execute_action

To register an action from any module:
    @register_action(
        name="AUDIO__speak",
        description="Make Hecos speak a message aloud via TTS.",
        params={"text": "string"},
    )
    def _speak(text: str): ...

The engine calls execute_action("AUDIO__speak", {"text": "..."}) at runtime.
"""

from typing import Any, Callable, Dict, List, Optional
from hecos.core.logging import logger

class FlowLogger:
    def info(self, msg): logger.info("FLOWS", msg)
    def error(self, msg): logger.error("FLOWS", msg)
    def warning(self, msg): logger.debug("FLOWS", f"[WARN] {msg}")
    def debug(self, msg): logger.debug("FLOWS", msg)

log = FlowLogger()

# ── Internal store ─────────────────────────────────────────────────────────────

_REGISTRY: Dict[str, Dict[str, Any]] = {}


# ── Decorator ──────────────────────────────────────────────────────────────────

def register_action(
    name: str,
    description: str = "",
    params: Optional[Dict[str, str]] = None,
    category: str = "GENERAL",
    icon: str = "⚡",
):
    """
    Decorator to register a Python callable as a Hecos Flow action.

    Args:
        name:        Unique action identifier in MODULE__method format (e.g. AUDIO__speak).
        description: Human-readable description shown in the canvas & YAML autocompletion.
        params:      Dict of {param_name: type_hint_string} for documentation purposes.
        category:    Visual grouping in the node palette (e.g. "AUDIO", "LOGIC", "MAIL").
        icon:        Emoji icon shown on the node card.
    """
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[name] = {
            "name":        name,
            "description": description,
            "params":      params or {},
            "category":    category,
            "icon":        icon,
            "fn":          fn,
        }
        log.debug(f"[Flows.Registry] Registered action: {name}")
        return fn
    return decorator


# ── Bootstrap built-in LOGIC actions ──────────────────────────────────────────

# ── Public API ─────────────────────────────────────────────────────────────────

def get_catalog() -> List[Dict[str, Any]]:
    """Return all registered actions grouped by category (serializable, no fn)."""
    catalog: Dict[str, List] = {}
    for action in _REGISTRY.values():
        cat = action["category"]
        entry = {k: v for k, v in action.items() if k != "fn"}
        
        # Automatically inject execution-level parameters for non-trigger actions
        if cat != "TRIGGER":
            params_copy = dict(entry.get("params", {}))
            if "timeout_seconds" not in params_copy:
                params_copy["timeout_seconds"] = "integer (0 to disable)"
            if "on_timeout_continue" not in params_copy:
                params_copy["on_timeout_continue"] = "boolean (skip error and continue)"
            entry["params"] = params_copy
            
        catalog.setdefault(cat, []).append(entry)
    return catalog


def get_action(name: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single action definition by name."""
    return _REGISTRY.get(name)


def execute_action(name: str, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
    """
    Execute a registered action with the given parameters.
    Falls back to dynamic module_loader lookup for Hecos plugin actions.

    Priority for class-based plugins:
      1. module.tools.<method>(**params)   [class-based singleton e.g. REMINDER, MAIL]
      2. module.<method>(**params)         [legacy/module-level functions]
    """
    import inspect

    def _call_with_filtered_params(method, params_dict):
        sig = inspect.signature(method)
        has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        if has_kwargs:
            return method(**params_dict)
        filtered = {k: v for k, v in params_dict.items() if k in sig.parameters}
        return method(**filtered)

    entry = _REGISTRY.get(name)

    if entry and entry.get("fn"):
        # Directly registered Python callable
        return _call_with_filtered_params(entry["fn"], params)

    # Dynamic dispatch via module_loader
    if "__" in name:
        module_tag, method_name = name.split("__", 1)
        try:
            from hecos.core.system.module_loader import get_plugin_module
            plugin_mod = get_plugin_module(module_tag, legacy=False)
            if plugin_mod is None:
                plugin_mod = get_plugin_module(module_tag, legacy=True)

            if plugin_mod:
                # Priority 1: class-based plugin — try module.tools.<method>
                tools_instance = getattr(plugin_mod, "tools", None)
                if tools_instance is not None:
                    method = getattr(tools_instance, method_name, None)
                    if callable(method):
                        log.debug(f"[Flows] Dispatching {name} via module.tools")
                        return _call_with_filtered_params(method, params)

                # Priority 2: module-level function (legacy / free-function plugins)
                method = getattr(plugin_mod, method_name, None)
                if callable(method):
                    log.debug(f"[Flows] Dispatching {name} via module-level function")
                    return _call_with_filtered_params(method, params)

                # Nothing found — emit a helpful error
                available = [m for m in dir(tools_instance or plugin_mod) if not m.startswith("_")]
                log.error(
                    f"[Flows] Plugin '{module_tag}' loaded but method '{method_name}' not found. "
                    f"Available: {available}"
                )
                raise AttributeError(
                    f"[Flows] '{module_tag}' has no method '{method_name}'. "
                    f"Available: {available}"
                )
            else:
                log.error(f"[Flows] Plugin '{module_tag}' is not loaded and could not be lazy-loaded.")

        except (AttributeError, KeyError) as e:
            raise RuntimeError(f"[Flows] Cannot dispatch {name}: {e}") from e
        except Exception as e:
            raise RuntimeError(f"[Flows] Failed to execute {name}: {e}") from e

    raise KeyError(f"[Flows] Unknown action: '{name}'. Check the action catalog.")

# ── Initialize Builtin Nodes ───────────────────────────────────────────────────

from .builtins.core_nodes import _bootstrap_builtin_actions
from .builtins.audio_nodes import _setup_audio_wrappers
from .builtins.system_nodes import _setup_system_wrappers
from .builtins.ai_nodes import _setup_ai_wrappers
from .builtins.auto_discovery import _auto_register_hecos_modules

_bootstrap_builtin_actions()
_setup_audio_wrappers()
_setup_system_wrappers()
_setup_ai_wrappers()
_auto_register_hecos_modules()
