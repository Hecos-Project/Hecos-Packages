"""
Hecos Builder Studio - Main Routes Blueprint and Facade
Coordinates sub-routers for backups, compilation, manifest management, and package lifecycle.
"""

import os
import sys

_cur_dir = os.path.dirname(os.path.abspath(__file__))
if _cur_dir not in sys.path:
    sys.path.insert(0, _cur_dir)

# Re-exports for backward compatibility
from routes_backup import (
    _strip_ansi,
    _get_repo_root,
    _find_live_package_path,
    _backup_live_package,
    register_backup_routes
)
from routes_compiler import register_compiler_routes
from routes_manifest import register_manifest_routes
from routes_lifecycle import register_lifecycle_routes


def init_plugin_routes(app, cfg_mgr, hecos_src, log):
    """
    Initializes all Builder Studio endpoints by registering them onto the central Flask app.
    100% backward compatible with Hecos package route loader.
    """
    # 1. Live backup and package backup routes
    register_backup_routes(app, cfg_mgr, hecos_src, log)

    # 2. Package build, compiler, batch-build, inspect and unpack routes
    register_compiler_routes(app, cfg_mgr, hecos_src, log)

    # 3. Manifest IO, wizard scaffolding, capabilities and media routes
    register_manifest_routes(app, cfg_mgr, hecos_src, log)

    # 4. Store catalog, local installation and live dev-sync routes
    register_lifecycle_routes(app, cfg_mgr, hecos_src, log)
