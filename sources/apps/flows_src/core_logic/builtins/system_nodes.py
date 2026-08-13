from hecos.modules.flows.core_logic.registry import _REGISTRY, log
import time

def _setup_system_wrappers():
    def _system_chat_message(text: str = "", **kwargs):
        try:
            from hecos.memory.brain_interface import save_message
            # Since flows run in background threads, default to 'admin' user
            uid = "admin"
            try:
                from flask import request
                from flask_login import current_user
                if request and current_user.is_authenticated:
                    uid = current_user.username
            except RuntimeError:
                pass  # Working outside of request context
            
            save_message(
                role="assistant",
                message=text,
                user_id=uid,
                session_id=None,   # uses privacy_manager session
                persona_name="Flows",
                broadcast_sse=True   # push to chat in real time
            )
            log.info(f"[Flows.Chat] Message written: {text}")
        except Exception as e:
            log.error(f"[Flows.Chat] Cannot write chat message: {e}")
        return text

    _REGISTRY["SYSTEM__chat_message"] = {
        "name": "SYSTEM__chat_message",
        "description": "Appends a text message to the Hecos chat history.",
        "params": {"text": "string (message to write)"},
        "category": "SYSTEM",
        "icon": "💬",
        "fn": _system_chat_message,
    }

    def _system_speak_and_chat(text: str = "", **kwargs):
        # First send to chat
        _system_chat_message(text)
        # Then speak aloud
        try:
            from hecos.core.audio import voice
            voice.speak(text)
        except Exception as e:
            log.error(f"[Flows.Audio] Cannot speak: {e}")
        return text

    _REGISTRY["SYSTEM__speak_and_chat"] = {
        "name": "SYSTEM__speak_and_chat",
        "description": "Appends a message to the chat AND speaks it aloud.",
        "params": {"text": "string (message to speak and write)"},
        "category": "SYSTEM",
        "icon": "🗣️",
        "fn": _system_speak_and_chat,
    }

