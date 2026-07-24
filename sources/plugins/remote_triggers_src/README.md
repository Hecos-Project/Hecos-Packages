# Remote Triggers

**Package ID:** `remote_triggers`  
**Version:** 1.0.0  
**Status:** ⚠️ Experimental — Not fully functional

## Description

Remote Triggers is an experimental Hecos module that enables Push-to-Talk (PTT) activation from external remote sources, without requiring the standard keyboard hotkey (Ctrl+Shift).

## Supported PTT Sources

| Source | Description | Status |
|---|---|---|
| ⌨️ Keyboard Hotkey | Standard Ctrl+Shift (or custom key) | ✅ Core (always active) |
| ⌚ Smartwatch / BT Media Keys | Hardware F24 button or Play/Pause BT key | ⚠️ Experimental |
| 🌐 HTTP Webhook | `GET /api/remote-triggers/ptt/start` etc. | ⚠️ Experimental |
| 🎯 Custom Key | Any single key (e.g. `f8`) — Hold-to-Talk | ⚠️ Experimental |

## HTTP Webhook Endpoints

```
GET /api/remote-triggers/status         — PTT bus status
GET /api/remote-triggers/ptt/start      — Start PTT
GET /api/remote-triggers/ptt/stop       — Stop PTT
GET /api/remote-triggers/ptt/toggle     — Toggle PTT
GET /api/remote-triggers/config         — Read config
POST /api/remote-triggers/config        — Save config
```

## Notes

- All PTT signals are routed to the Hecos `ptt_bus` core — the audio pipeline is not modified.
- The `smartwatch_bus` listener uses `F24` as a hardware trigger key (non-colliding with OS shortcuts).
- Originally designed to allow talking to Hecos via a smartwatch voice assistant button.

## Requirements

- `pynput` (for smartwatch hardware key listening)
