"""
mcp_bridge — Hecos Model Context Protocol Bridge
Root __init__.py: re-exports from the plugin/ subpackage.
This is needed because HPM installs the full package tree with
plugin_dir=".", so Python sees hecos.modules.mcp_bridge as this package
and hecos.modules.mcp_bridge.plugin as the subpackage.
"""
from .plugin import (
    MCPProxy,
    MCPBridgePlugin,
    DynamicTools,
    bridge_instance,
    tools,
    on_load,
    info,
    execute,
    MCP_PROTOCOL_VERSION,
    MCP_CALL_TIMEOUT,
    MCP_INIT_TIMEOUT,
)

__all__ = [
    "MCPProxy",
    "MCPBridgePlugin",
    "DynamicTools",
    "bridge_instance",
    "tools",
    "on_load",
    "info",
    "execute",
    "MCP_PROTOCOL_VERSION",
    "MCP_CALL_TIMEOUT",
    "MCP_INIT_TIMEOUT",
]
