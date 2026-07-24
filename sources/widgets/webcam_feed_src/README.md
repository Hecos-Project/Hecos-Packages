# Webcam Feed

A zero-latency sidebar widget for Hecos Hub that streams a live webcam feed using the browser's native WebRTC API.

## Features
- **Live Camera Feed**: Streams directly from the client device via `navigator.mediaDevices.getUserMedia` — no backend processing, zero latency.
- **Camera Selection**: Auto-detects all video input devices (integrated, USB, virtual cameras like OBS).
- **Autostart**: Optionally auto-start the feed when the Hub loads. Setting is saved per-device in `localStorage`.
- **On/Off Toggle**: Simple button to start or stop the stream at any time.

## Installation
1. Compile with `Hecos_HPM_Builder` → `webcam_feed-1.0.0.hpkg`.
2. Install via the HPM Package Manager in the Hub.

## Notes
- The feed streams from the device **running the browser** (PC, phone, tablet).
- Browser will ask for camera permission the first time — this is required for WebRTC.
