"""
Hecos Document Reader — Routes
Proxy to web.routes.init_plugin_routes
"""
from .web.routes import init_plugin_routes, register_routes

__all__ = ["init_plugin_routes", "register_routes"]
