import os
try:
    from hecos.core.logging import logger
except ImportError:
    class DummyLogger:
        def debug(self, *args, **kwargs): print("[BUILDER_DEBUG]", *args)
        def error(self, *args, **kwargs): print("[BUILDER_ERR]", *args)
        def info(self, *args, **kwargs): print("[BUILDER_INFO]", *args)
    logger = DummyLogger()

TAG = "BUILDER"

class BuilderStudioPlugin:
    """Hecos Builder Studio - Package Development IDE."""
    
    def __init__(self):
        self.tag = TAG
        self.desc = "Builder Studio: Visual IDE for building and managing Hecos packages."
        self.config_schema = {}
        self.status = "ONLINE"


_plugin = BuilderStudioPlugin()
tools = _plugin

def get_plugin():
    return _plugin

def info():
    return {
        "tag": TAG,
        "display_name": "Builder Studio",
        "description": _plugin.desc,
        "version": "1.0.0",
        "author": "Hecos Community",
        "status": _plugin.status,
    }

def status():
    return _plugin.status

