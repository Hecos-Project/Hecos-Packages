"""
hecos/modules/net_search/vision/__init__.py
Compatibility proxy forwarding directly to the unified Hecos Multimodal Perception subsystem
at hecos.modules.web_ui.vision.
"""
from hecos.modules.web_ui.vision import (
    load_vision_config,
    reload_vision_config,
    extract_search_session_images,
    VisionRouter,
    inspect_image
)

def inject_search_vision(session_id: str, config=None, vision_cfg=None):
    return extract_search_session_images(session_id, config=vision_cfg)

__all__ = [
    "load_vision_config",
    "reload_vision_config",
    "extract_search_session_images",
    "VisionRouter",
    "inject_search_vision",
]
