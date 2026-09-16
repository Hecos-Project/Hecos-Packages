"""
image_gen — SwarmUI HTTP Client
Handles all HTTP communication with a local SwarmUI instance.

Responsibilities:
  - Session management (get / refresh / cache)
  - Image generation via POST /API/GenerateText2Image
  - Image download via GET /View/{path}
  - Model listing via POST /API/ListModels
  - Automatic session refresh on expiry
"""

import time
import threading
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    from hecos_sdk import logger
except ImportError:
    class _L:
        def info(self, *a): print("[SWARM_CLIENT]", *a)
        def warning(self, *a): print("[SWARM_CLIENT WARN]", *a)
        def error(self, *a): print("[SWARM_CLIENT ERR]", *a)
        def debug(self, *a): pass
    logger = _L()


class SwarmUIError(Exception):
    """Base exception for SwarmUI client errors."""
    pass


class SwarmUIConnectionError(SwarmUIError):
    """Raised when the SwarmUI server is unreachable."""
    pass


class SwarmUISessionError(SwarmUIError):
    """Raised when session management fails."""
    pass


class SwarmUIGenerationError(SwarmUIError):
    """Raised when image generation fails."""
    pass


class SwarmUIClient:
    """
    HTTP client for SwarmUI REST API.

    Usage:
        client = SwarmUIClient("http://localhost:7801")
        image_bytes = client.generate(prompt="a cat", model="flux", ...)
        models = client.list_models()
    """

    def __init__(self, base_url: str = "http://localhost:7801",
                 timeout: int = 120, auth_token: str = ""):
        if requests is None:
            raise ImportError("'requests' package is required for SwarmUI client.")

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.auth_token = auth_token

        self._session_id: Optional[str] = None
        self._session_lock = threading.Lock()
        self._session_timestamp: float = 0.0
        # Sessions expire after ~30 min of inactivity; refresh proactively
        self._session_max_age: float = 1500.0  # 25 minutes

    # ── Session Management ────────────────────────────────────────────────

    def _get_cookies(self) -> dict:
        """Build cookies dict for authenticated requests."""
        if self.auth_token:
            return {"swarm_token": self.auth_token}
        return {}

    def _request_new_session(self) -> str:
        """Request a new session_id from SwarmUI."""
        url = f"{self.base_url}/API/GetNewSession"
        try:
            resp = requests.post(
                url, json={}, timeout=10,
                cookies=self._get_cookies(),
            )
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                raise SwarmUISessionError(f"Session error: {data['error']}")

            session_id = data.get("session_id")
            if not session_id:
                raise SwarmUISessionError("No session_id in response")

            logger.info(f"[SWARM_CLIENT] New session: {session_id[:12]}...")
            return session_id

        except requests.ConnectionError:
            logger.error(f"[SWARM_CLIENT] Connection refused at {self.base_url}. Is SwarmUI running?")
            raise SwarmUIConnectionError(
                f"Cannot connect to SwarmUI at {self.base_url}. "
                "Make sure SwarmUI is running."
            )
        except requests.Timeout:
            logger.error(f"[SWARM_CLIENT] Connection timeout at {self.base_url}.")
            raise SwarmUIConnectionError(
                f"SwarmUI at {self.base_url} timed out during session request."
            )
        except SwarmUIError:
            raise
        except Exception as e:
            raise SwarmUISessionError(f"Failed to get session: {e}")

    def get_session(self) -> str:
        """
        Get a valid session_id (cached, thread-safe).
        Automatically refreshes if expired or missing.
        """
        with self._session_lock:
            now = time.time()
            if (self._session_id
                    and (now - self._session_timestamp) < self._session_max_age):
                return self._session_id

            self._session_id = self._request_new_session()
            self._session_timestamp = now
            return self._session_id

    def _invalidate_session(self):
        """Invalidate the cached session (e.g., on invalid_session_id error)."""
        with self._session_lock:
            self._session_id = None
            self._session_timestamp = 0.0

    # ── API Calls ─────────────────────────────────────────────────────────

    def _api_post(self, route: str, payload: dict,
                  timeout: Optional[int] = None,
                  retry_on_session: bool = True) -> dict:
        """
        Generic POST to SwarmUI API with automatic session injection
        and retry on session expiry.
        """
        url = f"{self.base_url}/API/{route}"
        payload["session_id"] = self.get_session()

        try:
            resp = requests.post(
                url, json=payload,
                timeout=timeout or self.timeout,
                cookies=self._get_cookies(),
            )
            resp.raise_for_status()
            data = resp.json()

            # Handle session expiry
            if data.get("error_id") == "invalid_session_id" and retry_on_session:
                logger.warning("[SWARM_CLIENT] Session expired, refreshing...")
                self._invalidate_session()
                payload["session_id"] = self.get_session()
                resp = requests.post(
                    url, json=payload,
                    timeout=timeout or self.timeout,
                    cookies=self._get_cookies(),
                )
                resp.raise_for_status()
                data = resp.json()

            if "error" in data and data.get("error_id") != "invalid_session_id":
                raise SwarmUIError(f"SwarmUI API error: {data['error']}")

            return data

        except requests.ConnectionError:
            logger.error(f"[SWARM_CLIENT] Lost connection to {self.base_url}. Was SwarmUI closed?")
            raise SwarmUIConnectionError(
                f"Lost connection to SwarmUI at {self.base_url}"
            )
        except requests.Timeout:
            logger.error(f"[SWARM_CLIENT] API timeout for route {route}.")
            raise SwarmUIConnectionError(
                f"SwarmUI request to {route} timed out after {timeout or self.timeout}s"
            )
        except SwarmUIError:
            raise
        except Exception as e:
            raise SwarmUIError(f"API call to {route} failed: {e}")

    def generate(self, params: dict) -> tuple[list[str], dict]:
        """
        Generate image(s) via SwarmUI.

        Args:
            params: Pre-built parameter dict from params.build_swarmui_params().

        Returns:
            Tuple of (image_paths, metadata) where image_paths are the
            SwarmUI-relative paths to download.
        """
        logger.info(f"[SWARM_CLIENT] Generating: model={params.get('model', '?')}, "
                     f"steps={params.get('steps', '?')}, "
                     f"size={params.get('width', '?')}x{params.get('height', '?')}")

        data = self._api_post("GenerateText2Image", params, timeout=self.timeout)

        images = data.get("images", [])
        if not images:
            raise SwarmUIGenerationError(
                "SwarmUI returned no images. Check model availability and prompt."
            )

        # images can be list of strings or list of dicts
        image_paths = []
        for img in images:
            if isinstance(img, str):
                image_paths.append(img)
            elif isinstance(img, dict):
                image_paths.append(img.get("image", ""))
            else:
                image_paths.append(str(img))

        image_paths = [p for p in image_paths if p]
        if not image_paths:
            raise SwarmUIGenerationError("SwarmUI returned empty image paths.")

        logger.info(f"[SWARM_CLIENT] Generated {len(image_paths)} image(s)")
        return image_paths, data

    def download_image(self, image_path: str) -> bytes:
        """
        Download a generated image from SwarmUI.

        Args:
            image_path: The path returned by generate(), e.g.
                        "View/local/raw/2024-01-02/image.png"
        """
        # SwarmUI paths may or may not start with /
        clean_path = image_path.lstrip("/")
        url = f"{self.base_url}/{clean_path}"

        try:
            resp = requests.get(
                url, timeout=30,
                cookies=self._get_cookies(),
            )
            resp.raise_for_status()

            if len(resp.content) < 100:
                raise SwarmUIGenerationError(
                    f"Downloaded image is suspiciously small ({len(resp.content)} bytes)"
                )

            return resp.content

        except requests.ConnectionError:
            logger.error(f"[SWARM_CLIENT] Failed to download image, connection failed with {url}. Is SwarmUI closed?")
            raise SwarmUIConnectionError(
                f"Failed to download image from {url}"
            )
        except SwarmUIError:
            raise
        except Exception as e:
            raise SwarmUIError(f"Image download failed: {e}")

    def list_models(self, subtype: Optional[str] = None) -> list[dict]:
        """
        Fetch available models from SwarmUI.
        """
        try:
            logger.info(f"[SWARM_CLIENT] Fetching models from {self.base_url} (subtype={subtype})")
            payload = {"path": "", "depth": 2}
            if subtype:
                payload["subtype"] = subtype
            data = self._api_post("ListModels", payload, timeout=15)
            models_raw = data.get("files", [])
            logger.info(f"[SWARM_CLIENT] Received {len(models_raw)} raw models from API.")
            models = []
            for m in models_raw:
                if isinstance(m, str):
                    models.append({"name": m, "title": m})
                elif isinstance(m, dict):
                    models.append({
                        "name":                m.get("name", m.get("title", "")),
                        "title":               m.get("title", m.get("name", "")),
                        "compat_class":        m.get("compat_class", ""),
                        "architecture":        m.get("architecture", ""),
                        "class":               m.get("class", ""),
                        "trigger_phrase":      m.get("trigger_phrase", ""),
                        "lora_default_weight": m.get("lora_default_weight", ""),
                        "loaded":              m.get("loaded", False),
                    })
            return models
        except Exception as e:
            logger.error(f"[SWARM_CLIENT] list_models failed: {e}")
            raise SwarmUIError(f"Failed to list models: {e}")

        except Exception as e:
            logger.warning(f"[SWARM_CLIENT] Failed to list models: {e}")
            return []

    def list_t2i_params(self) -> dict:
        """
        Fetch available T2I parameters from SwarmUI.
        Useful for discovering samplers, schedulers, and other options.
        """
        try:
            data = self._api_post("ListT2IParams", {}, timeout=10)
            return data
        except Exception as e:
            logger.warning(f"[SWARM_CLIENT] Failed to list T2I params: {e}")
            return {}

    def ping(self) -> bool:
        """Quick connectivity test. Returns True if SwarmUI is reachable."""
        try:
            resp = requests.post(
                f"{self.base_url}/API/GetNewSession",
                json={}, timeout=5,
                cookies=self._get_cookies(),
            )
            return resp.status_code == 200
        except Exception:
            return False
