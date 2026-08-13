from hecos.modules.flows.core_logic.registry import _REGISTRY, log
from typing import Optional
import time

def _setup_ai_wrappers():
    def _ai_prompt(prompt: str = "", save_to_chat: bool = True, **kwargs):
        """
        Sends a prompt directly to the Hecos AI brain (AgentExecutor) and
        returns the full response text. The flow blocks here until the AI
        has finished thinking — the response is then available via output_as.
        """
        if not prompt:
            log.warning("[Flows.AI] AI__prompt called with empty prompt.")
            return ""
        try:
            from hecos.modules.web_ui.server import get_state_manager
            from hecos.core.agent.loop import AgentExecutor

            sm = get_state_manager()            # Retrieve config_manager stored on the Flask app at startup
            cfg_mgr = None
            try:
                from flask import current_app
                cfg_mgr = getattr(current_app._get_current_object(), "hecos_config_manager", None)
            except RuntimeError:
                pass  # Working outside Flask request context (flow background thread)

            # Fallback: stored on sys by the main application
            if cfg_mgr is None:
                import sys
                cfg_mgr = getattr(sys, "hecos_config_manager", None)

            # Final fallback: create a fresh ConfigManager from disk
            if cfg_mgr is None:
                try:
                    from hecos.app.config import ConfigManager
                    cfg_mgr = ConfigManager()
                except Exception as e:
                    log.error(f"[Flows.AI] Could not instantiate ConfigManager: {e}")

            if cfg_mgr is None:
                log.error("[Flows.AI] Config manager not available — cannot call AI.")
                return "[AI__prompt error: config_manager not found]"

            agent = AgentExecutor(
                config=cfg_mgr.config,
                config_manager=cfg_mgr,
                state_manager=sm,
                trace_callback=lambda msg, level="info": log.debug(f"[Flows.AI.trace] {msg}"),
                current_user_id="admin",  # flows run outside HTTP context
            )

            log.info(f"[Flows.AI] Sending prompt to AI: {prompt[:80]}...")
            
            full_text, _voice = agent.run_agentic_loop(prompt, voice_status=False)
                
            log.info(f"[Flows.AI] AI response received ({len(full_text)} chars).")

            # Optionally persist the exchange to chat history so user can review it
            if save_to_chat:
                try:
                    from hecos.memory.brain_interface import save_message
                    save_message(role="user",      message=f"[Flow] {prompt}", user_id="admin", session_id=None, persona_name="Flows", broadcast_sse=True)
                    save_message(role="assistant", message=full_text,          user_id="admin", session_id=None, persona_name="Flows", broadcast_sse=True)
                except Exception as e:
                    log.warning(f"[Flows.AI] Could not save chat history: {e}")

            return full_text

        except TimeoutError:
            raise
        except Exception as e:
            log.error(f"[Flows.AI] Error calling AgentExecutor: {e}")
            return f"[AI__prompt error: {e}]"

    _REGISTRY["AI__prompt"] = {
        "name": "AI__prompt",
        "description": (
            "Send a natural-language prompt to the Hecos AI brain and capture the response. "
            "The flow blocks until the AI finishes. Use output_as to store the response as "
            "a variable for subsequent nodes."
        ),
        "params": {
            "prompt":              "string — the question or instruction to send to the AI",
            "save_to_chat":        "bool (optional, default true) — whether to write the prompt+response to the chat history",
            "timeout_seconds":     "integer (optional) — max time to wait before aborting the flow. 0 = infinite.",
            "on_timeout_continue": "bool (optional, default false) — if true, proceeds returning '[AI Timeout]' instead of stopping the flow",
        },
        "category": "AI",
        "icon": "🧠",
        "fn": _ai_prompt,
    }

# ── Auto-registration from Hecos modules ──────────────────────────────────────

