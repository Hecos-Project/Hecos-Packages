"""
search/stream_hunter/__init__.py
Modular Live Stream Discovery, Probing, M3U Parsing & VLC Playback Subsystem for Hecos Net Search.
"""
from .models import StreamItem
from .service import StreamHunterService, get_stream_hunter_service, search_streams
from .routes import register_stream_hunter_routes

__all__ = [
    "StreamItem",
    "StreamHunterService",
    "get_stream_hunter_service",
    "search_streams",
    "register_stream_hunter_routes",
]
