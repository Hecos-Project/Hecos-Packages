"""
Hecos Flows — Template Evaluator
==================================
Jinja2-based rendering and boolean condition evaluation for flow contexts.

All dynamic {{ variable }} expressions and {% if %} conditions in the YAML
pipeline pass through this module.
"""

from typing import Any, Dict

from hecos.core.logging import logger


class FlowLogger:
    def info(self, msg): logger.info("FLOWS", msg)
    def error(self, msg): logger.error("FLOWS", msg)
    def warning(self, msg): logger.debug("FLOWS", f"[WARN] {msg}")
    def debug(self, msg): logger.debug("FLOWS", msg)

log = FlowLogger()


def render(template_str: str, context: Dict[str, Any]) -> Any:
    """
    Render a Jinja2 template string against the flow context.
    Passes through non-string values and strings without Jinja2 markers unchanged.
    """
    if not isinstance(template_str, str):
        return template_str
    if "{{" not in template_str and "{%" not in template_str:
        return template_str
    try:
        from jinja2 import Environment, Undefined
        env = Environment(undefined=Undefined)
        tmpl = env.from_string(template_str)
        return tmpl.render(**context)
    except Exception as e:
        log.warning(f"[Flows.Engine] Jinja2 render error: {e}")
        return template_str


def render_params(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively render all string values in a params dict.
    Lists and nested dicts are traversed depth-first.
    """
    result = {}
    for k, v in params.items():
        if isinstance(v, str):
            result[k] = render(v, context)
        elif isinstance(v, dict):
            result[k] = render_params(v, context)
        elif isinstance(v, list):
            result[k] = [render(i, context) if isinstance(i, str) else i for i in v]
        else:
            result[k] = v
    return result


def eval_condition(condition: str, context: Dict[str, Any]) -> bool:
    """
    Evaluate a Jinja2 boolean condition against the flow context.

    The condition string may or may not be wrapped in {{ }}; both forms
    are accepted. Numeric strings in the context are auto-coerced for
    loose comparisons (e.g. "10" > 5 works as expected).
    """
    # Strip any accidental brackets the user might have typed
    clean_cond = condition.replace("{{", "").replace("}}", "")

    # Auto-coerce types in context to allow loose comparisons
    eval_ctx = {}
    for k, v in context.items():
        if isinstance(v, str):
            v_lower = v.lower()
            if v_lower in ["true", "false"]:
                eval_ctx[k] = (v_lower == "true")
            else:
                try:
                    eval_ctx[k] = float(v) if "." in v else int(v)
                except ValueError:
                    eval_ctx[k] = v
        else:
            eval_ctx[k] = v

    rendered = render(f"{{% if {clean_cond} %}}true{{% else %}}false{{% endif %}}", eval_ctx)
    return rendered.strip() == "true"
