"""
Hecos Flows — APScheduler Integration
=======================================
Manages cron and interval-based flow triggers using APScheduler.

Responsibilities:
- Lazily initialise a single BackgroundScheduler (singleton).
- Register / unregister flow jobs when flows are saved or enabled/disabled.
- Re-register all persisted schedules at application startup.
"""

import threading
from typing import Any, Dict

from hecos.core.logging import logger


class FlowLogger:
    def info(self, msg): logger.info("FLOWS", msg)
    def error(self, msg): logger.error("FLOWS", msg)
    def warning(self, msg): logger.debug("FLOWS", f"[WARN] {msg}")
    def debug(self, msg): logger.debug("FLOWS", msg)

log = FlowLogger()


# ── Scheduler singleton ───────────────────────────────────────────────────────

_scheduler = None
_scheduler_lock = threading.Lock()


def _get_scheduler():
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            try:
                from apscheduler.schedulers.background import BackgroundScheduler

                # Fetch timezone from config if possible
                tz = "local"
                try:
                    from hecos.app.config import ConfigManager
                    cfg_mgr = ConfigManager()
                    tz = cfg_mgr.config.get("plugins", {}).get("FLOWS", {}).get("scheduler_timezone", "local")
                except Exception:
                    pass

                kwargs = {}
                if tz and tz != "local":
                    kwargs["timezone"] = tz

                _scheduler = BackgroundScheduler(**kwargs)
                _scheduler.start()
                log.info("[Flows.Scheduler] APScheduler started.")
            except ImportError:
                log.warning("[Flows.Scheduler] APScheduler not installed — cron/interval triggers disabled.")
        return _scheduler


# ── Public API ────────────────────────────────────────────────────────────────

def schedule_flow(flow_data: Dict[str, Any]) -> bool:
    """
    Register the flow's trigger with APScheduler.
    Call this whenever a flow is saved or enabled.
    Returns True on success.
    """
    scheduler = _get_scheduler()
    if scheduler is None:
        return False

    flow_id = flow_data.get("id", "")
    trigger  = flow_data.get("trigger", {})
    t_type   = trigger.get("type", "manual")

    # Remove existing job first (idempotent re-registration)
    unschedule_flow(flow_id)

    if not flow_data.get("enabled", True):
        return False

    if t_type == "manual":
        return True  # No automatic scheduling needed

    def _job():
        from ..storage import get_flow
        from .runner import run_flow_async
        fresh = get_flow(flow_id)
        if fresh and fresh.get("enabled", True):
            run_flow_async(fresh)

    try:
        if t_type == "cron":
            expr  = trigger.get("expression", "")
            parts = expr.strip().split()
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts
                scheduler.add_job(
                    _job, "cron",
                    id=f"flow_{flow_id}",
                    minute=minute, hour=hour, day=day,
                    month=month, day_of_week=day_of_week,
                    replace_existing=True,
                )
                log.info(f"[Flows.Scheduler] Scheduled '{flow_id}' as cron: {expr}")

        elif t_type == "interval":
            every  = int(trigger.get("every", 60))
            unit   = trigger.get("unit", "seconds")
            kwargs = {unit: every}
            scheduler.add_job(
                _job, "interval",
                id=f"flow_{flow_id}",
                replace_existing=True,
                **kwargs,
            )
            log.info(f"[Flows.Scheduler] Scheduled '{flow_id}' as interval: {every} {unit}")

        return True
    except Exception as e:
        log.error(f"[Flows.Scheduler] Could not schedule flow '{flow_id}': {e}")
        return False


def unschedule_flow(flow_id: str):
    """Remove a flow's scheduled job from APScheduler."""
    scheduler = _get_scheduler()
    if scheduler:
        try:
            scheduler.remove_job(f"flow_{flow_id}")
        except Exception:
            pass


def load_all_schedules():
    """Called at startup to re-register all enabled flows with their triggers."""
    try:
        from ..storage import list_flows, get_flow
        for flow_summary in list_flows():
            if flow_summary.get("enabled", True) and flow_summary.get("trigger_type") != "manual":
                flow_data = get_flow(flow_summary["id"])
                if flow_data:
                    schedule_flow(flow_data)
        log.info("[Flows.Scheduler] All persisted schedules loaded.")
    except Exception as e:
        log.warning(f"[Flows.Scheduler] Could not load schedules: {e}")
