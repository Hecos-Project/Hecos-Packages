"""
mcp_bridge/config_manager.py
────────────────────────────────────────────────────────────────────
Autonomous configuration manager for the MCP Bridge package.

Follows the same pattern as image_gen (Pydantic + TOML).
Config is stored in mcp_bridge.toml, inside the package's own
directory — fully independent from hecos.yaml / plugins.yaml.
"""
import os
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field

try:
    from hecos_sdk import logger
except ImportError:
    class _L:
        def info(self, *a):    print("[MCP_BRIDGE CONFIG]", *a)
        def error(self, *a):   print("[MCP_BRIDGE CONFIG ERR]", *a)
        def warning(self, *a): print("[MCP_BRIDGE CONFIG WARN]", *a)
        def debug(self, *a):   pass
    logger = _L()

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

try:
    import tomli_w
    _HAS_TOMLI_W = True
except ImportError:
    _HAS_TOMLI_W = False


# ── Pydantic Schema ──────────────────────────────────────────────────────────

class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""
    type: str = "stdio"          # "stdio" | "http"
    command: str = ""            # e.g. "npx"  (stdio only)
    args: List[str] = Field(default_factory=list)   # e.g. ["-y", "@mcp/..."]
    env: Dict[str, str] = Field(default_factory=dict)
    url: str = ""                # remote URL (http type only)
    enabled: bool = True


class MCPBridgeConfig(BaseModel):
    """Root configuration for the MCP Bridge package."""
    enabled: bool = True
    lazy_load: bool = False
    servers: Dict[str, MCPServerConfig] = Field(default_factory=dict)


# ── File paths ───────────────────────────────────────────────────────────────

_THIS_DIR = Path(__file__).parent.resolve()
_CONFIG_FILE = _THIS_DIR / "mcp_bridge.toml"
_ROOT_KEY = "mcp_bridge"


# ── Read / Write ─────────────────────────────────────────────────────────────

def _read_toml() -> dict:
    """Read the TOML config file; bootstrap defaults if missing."""
    if not _CONFIG_FILE.exists():
        defaults = MCPBridgeConfig().model_dump(mode="json")
        if _HAS_TOMLI_W:
            try:
                _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                _CONFIG_FILE.write_bytes(
                    tomli_w.dumps({_ROOT_KEY: defaults}).encode("utf-8")
                )
                logger.info("[MCP_BRIDGE_CONFIG] Default config created.")
            except Exception as e:
                logger.error(f"[MCP_BRIDGE_CONFIG] Could not write defaults: {e}")
        return defaults
    try:
        raw = tomllib.loads(_CONFIG_FILE.read_bytes().decode("utf-8"))
        return raw.get(_ROOT_KEY, {})
    except Exception as e:
        logger.error(f"[MCP_BRIDGE_CONFIG] Failed to read config: {e}")
        return {}


def _write_toml(section: dict) -> bool:
    """Write just the [mcp_bridge] section to the TOML file."""
    if not _HAS_TOMLI_W:
        logger.error("[MCP_BRIDGE_CONFIG] tomli_w not available, cannot save.")
        return False
    try:
        existing: dict = {}
        if _CONFIG_FILE.exists():
            try:
                existing = tomllib.loads(_CONFIG_FILE.read_bytes().decode("utf-8"))
            except Exception:
                existing = {}
        existing[_ROOT_KEY] = section
        _CONFIG_FILE.write_bytes(tomli_w.dumps(existing).encode("utf-8"))
        logger.debug("[MCP_BRIDGE_CONFIG] Config saved.")
        return True
    except Exception as e:
        logger.error(f"[MCP_BRIDGE_CONFIG] Failed to save config: {e}")
        return False


# ── Public API ───────────────────────────────────────────────────────────────

def get_config() -> dict:
    """Returns the full config as a plain dict (validated via Pydantic)."""
    raw = _read_toml()
    try:
        obj = MCPBridgeConfig.model_validate(raw)
    except Exception:
        obj = MCPBridgeConfig()
    return obj.model_dump(mode="json")


def save_config(data: dict) -> bool:
    """Validates and saves the config dict to mcp_bridge.toml."""
    try:
        obj = MCPBridgeConfig.model_validate(data)
        return _write_toml(obj.model_dump(mode="json"))
    except Exception as e:
        logger.error(f"[MCP_BRIDGE_CONFIG] Validation error on save: {e}")
        return False
