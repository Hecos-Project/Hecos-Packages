"""
browser_automation/main.py
Root entry-point loaded by Hecos module_scanner via lazy or eager loading.
"""
import importlib.util
import os

_plugin_main = os.path.join(os.path.dirname(__file__), "plugin", "main.py")
_spec = importlib.util.spec_from_file_location("browser_automation_plugin_main", _plugin_main)
_mod = importlib.util.module_from_spec(_spec)

import sys
_plugin_dir = os.path.dirname(_plugin_main)
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)
_pkg_dir = os.path.dirname(_plugin_dir)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

_spec.loader.exec_module(_mod)

BrowserTools = _mod.BrowserTools
tools = _mod.tools

def on_load(config=None, **kwargs):
    """Called on Hecos boot when on_load = true in hpkg_manifest.toml."""
    import sys
    app = getattr(sys, "hecos_flask_app", None)
    cfg_mgr = getattr(sys, "hecos_config_manager", None)
    if app:
        try:
            from .web.routes import init_plugin_routes
            init_plugin_routes(app, cfg_mgr, os.path.dirname(os.path.abspath(__file__)))
        except Exception:
            pass
    return tools

def info():
    return {
        "tag": "BROWSER",
        "name": "Browser Automation",
        "version": "2.0.0",
        "description": "Playwright Browser Automation: Navigate web pages, click elements, fill forms, and take screenshots.",
        "commands": {
            "open_url": "Apri una pagina web nel browser Hecos.",
            "click": "Clicca su un elemento del DOM.",
            "type": "Digita testo in un input o form.",
            "screenshot": "Cattura uno screenshot visivo della pagina.",
            "close_browser": "Chiudi la sessione browser aperta."
        }
    }

def status():
    return "ONLINE"

def get_plugin():
    return tools
