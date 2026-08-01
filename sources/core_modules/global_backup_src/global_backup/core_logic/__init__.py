"""
hecos.hpm.global_backup.core_logic
─────────────────────────────────────
Global Backup Orchestrator for Hecos (HPM Module).

Exposes:
  orchestrator  — per-module backup/restore functions
  scheduler     — APScheduler wrapper for automatic backups
  store         — persistent configuration (YAML)
  api           — Flask routes at /hecos/api/backup/...
"""
