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
