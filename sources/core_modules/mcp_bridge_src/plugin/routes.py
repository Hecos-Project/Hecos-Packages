import os
import json
import subprocess
from flask import request, jsonify
from hecos.core.system import module_loader
from hecos.modules.mcp_bridge.config_manager import get_config as _get_mcp_config, save_config as _save_mcp_config

def init_plugin_routes(app, cfg_mgr=None, logger=None):
    if logger is None:
        from hecos.core.logging import logger as _log
        logger = _log
    
    # ── INVENTORY & STATUS ───────────────────────────────────────────────
    @app.route("/api/mcp/inventory", methods=["GET"])
    def get_mcp_inventory():
        """Returns the list of all discovered MCP tools for the UI."""
        try:
            mcp_module = module_loader.get_plugin_module("MCP_BRIDGE", legacy=False)
            if not mcp_module or not hasattr(mcp_module, "bridge_instance"):
                return jsonify({"ok": True, "servers": {}})
            
            bridge = mcp_module.bridge_instance
            inventory = {}
            
            for name, proxy in bridge.proxies.items():
                # Check status
                status = "unknown"
                if proxy.process:
                    if proxy.process.poll() is not None:
                        status = "crashed"
                    else:
                        status = getattr(proxy, "status", "connected")
                else:
                    status = "disconnected"
                
                inventory[name] = {
                    "status": status,
                    "tools": proxy.tools,
                    "error": getattr(proxy, "last_error", "")
                }
                
            return jsonify({"ok": True, "servers": inventory})
        except Exception as e:
            logger.error(f"[WebUI] /api/mcp/inventory error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/mcp/config", methods=["GET"])
    def get_mcp_config():
        """Returns the MCP Bridge config from its own autonomous TOML file."""
        try:
            data = _get_mcp_config()
            return jsonify({"ok": True, "config": data})
        except Exception as e:
            logger.error(f"[WebUI] /api/mcp/config GET error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/mcp/config", methods=["POST"])
    def save_mcp_config():
        """Saves the MCP Bridge configuration to its own autonomous file."""
        try:
            data = request.get_json(force=True)
            if not isinstance(data, dict):
                return jsonify({"ok": False, "error": "Invalid payload"}), 400

            saved = _save_mcp_config(data)
            if not saved:
                return jsonify({"ok": False, "error": "Config write failed"}), 500

            logger.info("MCP_BRIDGE", f"MCP config saved — {len(data.get('servers', {}))} server(s).")

            # Also hot-sync the bridge immediately
            mcp_module = module_loader.get_plugin_module("MCP_BRIDGE", legacy=False)
            if mcp_module and hasattr(mcp_module, "bridge_instance"):
                mcp_module.bridge_instance.sync_from_config()

            return jsonify({"ok": True})
        except Exception as e:
            logger.error(f"[WebUI] /api/mcp/config error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/mcp/reload", methods=["POST"])
    def reload_mcp_bridge():
        """Hot-syncs the MCP bridge with the current saved configuration."""
        try:
            mcp_module = module_loader.get_plugin_module("MCP_BRIDGE", legacy=False)
            if not mcp_module or not hasattr(mcp_module, "bridge_instance"):
                return jsonify({"ok": False, "error": "MCP Bridge module not loaded"}), 404

            bridge = mcp_module.bridge_instance
            bridge.sync_from_config()

            # Return updated inventory after sync
            inventory = {}
            for name, proxy in bridge.proxies.items():
                status = getattr(proxy, "status", "starting")
                inventory[name] = {
                    "status": status,
                    "tools": proxy.tools,
                    "error": getattr(proxy, "last_error", "")
                }

            return jsonify({"ok": True, "servers": inventory})
        except Exception as e:
            logger.error(f"[WebUI] /api/mcp/reload error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/mcp/restart_server", methods=["POST"])
    def restart_mcp_server():
        """Forces a hard restart of a single MCP server process."""
        try:
            data = request.get_json(force=True)
            name = data.get("name")
            if not name:
                return jsonify({"ok": False, "error": "Server name missing"}), 400

            mcp_module = module_loader.get_plugin_module("MCP_BRIDGE", legacy=False)
            if not mcp_module or not hasattr(mcp_module, "bridge_instance"):
                return jsonify({"ok": False, "error": "MCP Bridge not active"}), 404

            bridge = mcp_module.bridge_instance
            if name in bridge.proxies:
                bridge.proxies[name].stop()
                del bridge.proxies[name]

            # Re-sync to spawn it again
            bridge.sync_from_config()
            return jsonify({"ok": True})
        except Exception as e:
            logger.error(f"[WebUI] /api/mcp/restart_server error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── REGISTRY EXPLORER ───────────────────────────────────────────────
    @app.route("/api/mcp/explore", methods=["GET"])
    def explore_mcp_servers():
        """
        Searches the Smithery.ai registry using npx @smithery/cli.
        Usage: /api/mcp/explore?q=term
        """
        query = request.args.get("q", "").strip()
        registry = request.args.get("reg", "smithery").lower()
        if not query:
            return jsonify({"ok": True, "results": []})

        try:
            logger.info(f"[MCP-EXPLORE] Searching {registry} for: '{query}'")
            npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
            
            if registry == "mcp-get":
                cmd = [npx_cmd, "-y", "mcp-get", "search", query, "--json"]
            else:
                cmd = [npx_cmd, "-y", "@smithery/cli", "mcp", "search", query]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                encoding='utf-8',
                timeout=60   # 60s: npx first-run must download @smithery/cli
            )

            if result.returncode != 0:
                logger.error(f"[MCP-EXPLORE] {registry} CLI error: {result.stderr}")
                return jsonify({"ok": False, "error": f"Search on {registry} failed."}), 500

            results = []
            if registry == "mcp-get":
                try:
                    # mcp-get returns a single JSON object with a "data" list
                    data = json.loads(result.stdout)
                    results = data.get("data", [])
                except json.JSONDecodeError:
                    logger.error("[MCP-EXPLORE] Failed to parse mcp-get JSON output")
            elif registry == "github":
                try:
                    import urllib.request
                    url = f"https://api.github.com/search/repositories?q={query}+topic:mcp-server&sort=stars"
                    req = urllib.request.Request(url, headers={"User-Agent": "Hecos-Core"})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read())
                        for repo in data.get("items", []):
                            results.append({
                                "name": repo["full_name"],
                                "description": repo["description"] or "MCP Server repository",
                                "qualifiedName": f"github:{repo['full_name']}",
                                "downloads": repo["stargazers_count"],
                                "homepage": repo["html_url"],
                                "author": repo.get("owner", {}).get("login", "")
                            })
                except Exception as e:
                    logger.error(f"[MCP-EXPLORE] GitHub API error: {e}")
            elif registry == "huggingface":
                try:
                    import urllib.request
                    url = f"https://huggingface.co/api/spaces?search={query}"
                    req = urllib.request.Request(url, headers={"User-Agent": "Hecos-Core"})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read())
                        for space in data[:15]:
                            results.append({
                                "name": space["id"],
                                "description": f"Hugging Face Space ({space.get('sdk', 'mcp')})",
                                "qualifiedName": f"hf:{space['id']}",
                                "downloads": space.get("likes", 0),
                                "homepage": f"https://huggingface.co/spaces/{space['id']}",
                                "author": space.get("author", space["id"].split("/")[0])
                            })
                except Exception as e:
                    logger.error(f"[MCP-EXPLORE] Hugging Face API error: {e}")
            else:
                # Smithery returns NDJSON (one JSON object per line)
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        results.append(data)
                    except json.JSONDecodeError:
                        continue

            logger.info(f"[MCP-EXPLORE] Found {len(results)} results in {registry} for '{query}'")
            return jsonify({"ok": True, "results": results})

        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "Search timed out. Please try again."}), 504
        except Exception as e:
            logger.error(f"[MCP-EXPLORE] Critical error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
