"""
image_gen — Local Generation Subsystem
Provides local image generation via SwarmUI (and future backends).
Each module handles one logical function:
  - client.py   → HTTP communication with SwarmUI
  - params.py   → Parameter mapping Hecos → SwarmUI format
  - models.py   → Model discovery and categorization
  - presets.py  → Built-in presets for local generation
  - health.py   → Backend health check and diagnostics
"""

from .client import SwarmUIClient
from .params import build_swarmui_params
from .models import discover_models, categorize_models
from .presets import LOCAL_BUILTIN_PRESETS
from .health import check_backend_status, get_backend_info

__all__ = [
    "SwarmUIClient",
    "build_swarmui_params",
    "discover_models",
    "categorize_models",
    "LOCAL_BUILTIN_PRESETS",
    "check_backend_status",
    "get_backend_info",
]
