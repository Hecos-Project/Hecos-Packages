# Hecos Flows

Visual automation engine for Hecos. Build, schedule, and run multi-step flows from a node-based canvas.

## Features

- **Visual Canvas:** Drag-and-drop nodes to create complex automation logic.
- **Natural Language Compilation:** Create flows simply by describing what you want to achieve using AI.
- **Triggers:** Schedule flows via Cron, Intervals, or execute them manually.
- **Live Logs:** Real-time execution streaming (SSE).
- **Hecos Integration:** Seamlessly integrates with Hecos Core capabilities (Files, Drive, Network, Audio, etc).

## Requirements

- Hecos Core v0.42.0+

## Usage

Once installed, a new `Flows` navigation button will appear in the Hecos Web UI. You can also use HDCS commands:
- `/flow list`
- `/flow run <name>`
- `/flow trigger <name>`
- `/flow status <name>`

