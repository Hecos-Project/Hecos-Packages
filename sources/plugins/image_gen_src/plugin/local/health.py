"""
image_gen — Local Backend Health Check
Provides diagnostics and status reporting for the local generation backend.

Responsibilities:
  - check_backend_status()  → quick online/offline check
  - get_backend_info()      → detailed version, GPU, backend info
  - format_status_report()  → human-readable diagnostic report
"""

import time
from typing import Optional

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore

try:
    from hecos_sdk import logger
except ImportError:
    class _L:
        def info(self, *a): print("[LOCAL_HEALTH]", *a)
        def error(self, *a): print("[LOCAL_HEALTH ERR]", *a)
        def debug(self, *a): pass
    logger = _L()


# ── Status Constants ──────────────────────────────────────────────────────

STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"
STATUS_ERROR = "error"
STATUS_AUTH_REQUIRED = "auth_required"


# ── Public API ────────────────────────────────────────────────────────────

def check_backend_status(url: str, timeout: int = 5) -> dict:
    """
    Quick check if the local backend is reachable.

    Args:
        url: Base URL of the backend (e.g., "http://localhost:7801").
        timeout: Connection timeout in seconds.

    Returns:
        Dict with keys: status, latency_ms, error (if any), version (if available).
    """
    if _requests is None:
        return {
            "status": STATUS_ERROR,
            "latency_ms": 0,
            "error": "requests package not installed",
        }

    url = url.rstrip("/")
    start = time.time()

    try:
        resp = _requests.post(
            f"{url}/API/GetNewSession",
            json={},
            timeout=timeout,
        )
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            version = data.get("version", "")
            session = data.get("session_id", "")

            return {
                "status": STATUS_ONLINE,
                "latency_ms": latency,
                "version": version,
                "session_id": session[:12] + "..." if session else "",
                "error": None,
            }

        elif resp.status_code in (401, 403):
            return {
                "status": STATUS_AUTH_REQUIRED,
                "latency_ms": latency,
                "error": f"Authentication required (HTTP {resp.status_code}). "
                         "Set auth_token in local config.",
            }
        else:
            return {
                "status": STATUS_ERROR,
                "latency_ms": latency,
                "error": f"Unexpected HTTP {resp.status_code}",
            }

    except _requests.ConnectionError:
        logger.warning(f"[LOCAL_HEALTH] SwarmUI unreachable at {url}. Is it running?")
        return {
            "status": STATUS_OFFLINE,
            "latency_ms": 0,
            "error": f"Cannot connect to {url}. Is SwarmUI running?",
        }
    except _requests.Timeout:
        logger.warning(f"[LOCAL_HEALTH] Connection timeout to {url}.")
        latency = int((time.time() - start) * 1000)
        return {
            "status": STATUS_OFFLINE,
            "latency_ms": latency,
            "error": f"Connection timed out after {timeout}s",
        }
    except Exception as e:
        return {
            "status": STATUS_ERROR,
            "latency_ms": 0,
            "error": str(e),
        }


def get_backend_info(client) -> dict:
    """
    Fetch detailed backend information from SwarmUI.

    Args:
        client: A SwarmUIClient instance.

    Returns:
        Dict with backend details: version, backends, gpu_info, etc.
    """
    info = {
        "reachable": False,
        "version": "",
        "backends": [],
        "models_count": 0,
        "samplers": [],
        "schedulers": [],
    }

    try:
        # Test connectivity and get version
        if not client.ping():
            return info

        info["reachable"] = True

        # Get session data (includes version)
        import requests as _req
        resp = _req.post(
            f"{client.base_url}/API/GetNewSession",
            json={}, timeout=5,
            cookies=client._get_cookies(),
        )
        if resp.status_code == 200:
            data = resp.json()
            info["version"] = data.get("version", "unknown")

        # Get T2I params for sampler/scheduler lists
        t2i_data = client.list_t2i_params()
        if t2i_data:
            # Extract sampler and scheduler lists from param groups
            for group in t2i_data.get("param_types", []):
                if isinstance(group, dict):
                    param_id = group.get("id", "")
                    if param_id == "sampler":
                        info["samplers"] = group.get("values", [])
                    elif param_id == "scheduler":
                        info["schedulers"] = group.get("values", [])

        # Get model count
        models = client.list_models()
        info["models_count"] = len(models)

    except Exception as e:
        logger.error(f"[LOCAL_HEALTH] Failed to get backend info: {e}")

    return info


def format_status_report(url: str, client=None) -> str:
    """
    Generate a human-readable status report for the local backend.

    Args:
        url: Base URL of the backend.
        client: Optional SwarmUIClient for detailed info.

    Returns:
        Formatted markdown string.
    """
    lines = ["## 🖥️ Local Backend Status\n"]

    # Quick status check
    status = check_backend_status(url)
    status_icon = {
        STATUS_ONLINE: "✅",
        STATUS_OFFLINE: "❌",
        STATUS_ERROR: "⚠️",
        STATUS_AUTH_REQUIRED: "🔒",
    }.get(status["status"], "❓")

    lines.append(f"{status_icon} **Status**: {status['status'].upper()}")
    lines.append(f"📡 **URL**: `{url}`")

    if status["latency_ms"]:
        lines.append(f"⏱️ **Latency**: {status['latency_ms']}ms")

    if status.get("version"):
        lines.append(f"📦 **Version**: {status['version']}")

    if status.get("error"):
        lines.append(f"❗ **Error**: {status['error']}")

    # Detailed info if client is available and backend is online
    if client and status["status"] == STATUS_ONLINE:
        lines.append("\n### Dettagli Backend\n")
        info = get_backend_info(client)

        lines.append(f"🧠 **Modelli disponibili**: {info['models_count']}")

        if info.get("samplers"):
            sampler_list = ", ".join(info["samplers"][:10])
            lines.append(f"🎛️ **Samplers**: {sampler_list}")
            if len(info["samplers"]) > 10:
                lines.append(f"   (+{len(info['samplers']) - 10} altri)")

        if info.get("schedulers"):
            sched_list = ", ".join(info["schedulers"][:10])
            lines.append(f"📊 **Schedulers**: {sched_list}")

    return "\n".join(lines)
