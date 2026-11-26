# Messenger Plugin v2.2 for Hecos

Modular messaging plugin enabling Hecos and its AI personas to send and receive messages, AI-generated photos, and documents across **WhatsApp** and **Telegram**, with native contact resolution via **Hecos Contacts**.

## Architecture

- **`core/`**: Platform-agnostic contracts (`BaseMessengerProvider`), dynamic `ProviderRegistry`, smart contact/target `resolver.py`, smart media & binary-image `media_resolver.py`, turn-aware follow-up & anti-burst memory (`session_memory.py`), transparent AI routing defaults (`defaults.py`), `templates_bridge.py`, and `inbound_router.py`.
- **`providers/whatsapp/`**: Modern 2026 Lexical/WDS WhatsApp Web driver with deterministic chat opening, real `#main [data-id]` + WDS SVG stanza delivery verification, media/document upload, and two explicit user-selectable delivery methods (`cdp` vs `persistent_profile`).
- **`providers/telegram/`**: Multi-bot Official Telegram Bot API integration with **Persona/Soul-aware automatic bot selection** (e.g. speaking with Urania sends from `Urania` bot; speaking with Hecos sends from `hecos` bot), fuzzy bot matching, active event-loop reuse, automatic photo-to-document fallback, and voice-note transcription.
- **Contextual AI Overrides & Safety**:
  - Dedicated user-editable AI Routing Overrides for **WhatsApp**, **Telegram** (with dynamic bot roster injection), and **General Messenger**, automatically composed into `routing_override.yaml`.
  - **15-Minute Follow-up Memory** + explicit `CLARIFICATION_REQUIRED` guardrails + per-turn duplicate protection.
  - Configurable **Anti-Hallucination Guard** preventing simulated plain-text delivery claims.

## Slash Commands
- `/msg whatsapp:Rowena Hello Rowena!`
- `/msg whatsapp:+393331234567 Hello!`
- `/msg telegram:Urania:1292135505 Hello!`
