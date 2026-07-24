"""
MODULE: Remote Triggers
PACKAGE: remote_triggers
DESCRIPTION: Experimental module to activate Hecos PTT from remote sources:
             smartwatch hardware button (F24 HID), Bluetooth media keys,
             HTTP webhooks (Arduino, ESP32), and custom hotkeys.

             All signals are forwarded to hecos.core.audio.ptt_bus.
             The core audio pipeline is NOT modified by this module.

STATUS: Experimental — Not fully functional.
"""

from hecos.core.logging import logger


class RemoteTriggersTools:
    def __init__(self):
        self.tag = "REMOTE_TRIGGERS"

    def status(self) -> str:
        """Returns the current status of the Remote Triggers module and PTT bus."""
        try:
            from hecos.core.audio import ptt_bus
            s = ptt_bus.get_status()
            active = s.get("ptt_active", False)
            source = s.get("last_source", "none")
            return (
                f"[REMOTE_TRIGGERS] PTT {'ACTIVE ▶' if active else 'idle'}. "
                f"Last source: {source}."
            )
        except Exception as e:
            logger.warning(f"[REMOTE_TRIGGERS] status() error: {e}")
            return f"[REMOTE_TRIGGERS] Could not read PTT bus status: {e}"


tools = RemoteTriggersTools()


def on_load(full_cfg: dict):
    """
    Hook called by the HPM Loader when the package is loaded.
    Starts the experimental smartwatch bus if watch_button is enabled in config.
    """
    try:
        from hecos.core.audio.device_manager import get_audio_config
        cfg = get_audio_config()
        if cfg.get("ptt_sources", {}).get("watch_button", False):
            from . import smartwatch_bus
            smartwatch_bus.start()
            logger.info("[REMOTE_TRIGGERS] Smartwatch Bus started via on_load hook.")
        else:
            logger.debug("[REMOTE_TRIGGERS] Smartwatch Bus not started (watch_button disabled).")
    except Exception as e:
        logger.warning(f"[REMOTE_TRIGGERS] on_load: smartwatch bus could not start: {e}")
