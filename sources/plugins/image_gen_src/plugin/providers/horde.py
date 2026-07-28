"""
image_gen — AI Horde Provider
Free, crowdsourced, distributed GPU cluster via aihorde.net.
Supports hundreds of models including uncensored ones.
API is asynchronous: submit → poll → retrieve.
"""
import time
import base64
from .utils import log_debug, save_image_bytes, get_proxies

_BASE_URL = "https://aihorde.net/api/v2"
_ANON_KEY = "0000000000"

# Popular fallback models in case the API is unreachable
_FALLBACK_MODELS = [
    "stable_diffusion",
    "SDXL 1.0",
    "DreamShaper",
    "Realistic Vision",
    "AbsoluteReality",
    "Anything v5",
    "Epic Realism",
    "Deliberate",
    "CyberRealistic",
    "MeinaMix",
]


class HordeProvider:
    NAME = "horde"

    @staticmethod
    def _headers(api_key: str) -> dict:
        key = api_key.strip() if api_key and api_key.strip() else _ANON_KEY
        return {
            "apikey": key,
            "Content-Type": "application/json",
            "Client-Agent": "Hecos:1.0:hecos@local",
        }

    @staticmethod
    def get_models() -> list:
        """Fetch currently available models from the Horde cluster."""
        try:
            import requests
            r = requests.get(
                f"{_BASE_URL}/status/models",
                params={"type": "image", "min_count": 1, "sort": "count"},
                timeout=10,
                proxies=get_proxies("horde"),
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    # Return model names sorted by worker count (most popular first)
                    return [m["name"] for m in data if m.get("name")]
        except Exception as e:
            log_debug(f"[Horde] Model list fetch failed: {e}")
        return _FALLBACK_MODELS

    @staticmethod
    def get_user_info(api_key: str) -> dict:
        """
        Fetch Horde account info (Kudos balance, username etc.)
        Returns a dict with keys: username, kudos, id, worker_count
        """
        try:
            import requests
            key = api_key.strip() if api_key and api_key.strip() else _ANON_KEY
            r = requests.get(
                f"{_BASE_URL}/find_user",
                headers=HordeProvider._headers(key),
                timeout=10,
                proxies=get_proxies("horde"),
            )
            if r.status_code == 200:
                d = r.json()
                return {
                    "ok": True,
                    "username": d.get("username", "Anonymous"),
                    "kudos": d.get("kudos", 0),
                    "id": d.get("id"),
                    "worker_count": d.get("worker_count", 0),
                    "is_anonymous": (not api_key or api_key.strip() == _ANON_KEY),
                }
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    def generate(
        prompt: str,
        width: int,
        height: int,
        model: str,
        api_key: str = "",
        negative_prompt: str = "",
        guidance_scale: float = 7.5,
        num_inference_steps: int = 30,
        seed: int = -1,
        sampler: str = "",
        scheduler: str = "",
        # Horde-specific extras (passed via **extra_kwargs from __init__.py)
        horde_nsfw: bool = True,
        horde_worker_blacklist: str = "",
    ) -> str:
        """
        Generate an image via AI Horde.
        The API is asynchronous: we submit the request, then poll until done.
        Returns the filename of the saved image.
        """
        import requests

        headers = HordeProvider._headers(api_key)

        # ── Clamp dimensions to multiples of 64 (Horde requirement) ──────────
        width  = max(64, (int(width)  // 64) * 64)
        height = max(64, (int(height) // 64) * 64)

        # ── Map sampler name ─────────────────────────────────────────────────
        _SAMPLER_MAP = {
            "euler":        "k_euler",
            "euler_a":      "k_euler_a",
            "dpm++2m":      "k_dpmpp_2m",
            "dpm++sde":     "k_dpmpp_sde",
            "heun":         "k_heun",
            "dpm2":         "k_dpm_2",
            "dpm2_a":       "k_dpm_2_a",
            "lms":          "k_lms",
            "plms":         "PLMS",
            "ddim":         "DDIM",
        }
        horde_sampler = _SAMPLER_MAP.get(
            (sampler or "euler").lower().replace(" ", "_"),
            "k_euler_a",
        )

        # ── Build worker blacklist ────────────────────────────────────────────
        blacklist = [w.strip() for w in horde_worker_blacklist.split(",") if w.strip()] if horde_worker_blacklist else []

        # ── Payload ──────────────────────────────────────────────────────────
        payload: dict = {
            "prompt": prompt,
            "params": {
                "sampler_name":       horde_sampler,
                "cfg_scale":          float(guidance_scale) if guidance_scale and guidance_scale > 0 else 7.5,
                "steps":              max(1, int(num_inference_steps)) if num_inference_steps else 30,
                "width":              width,
                "height":             height,
                "karras":             True,
                "n":                  1,
                "clip_skip":          1,
            },
            "nsfw":          horde_nsfw,
            "censor_nsfw":   False,
            "models":        [model] if model else ["stable_diffusion"],
            "r2":            True,   # request R2-compatible URLs (recommended)
        }
        if negative_prompt and negative_prompt.strip():
            payload["prompt"] = f"{prompt} ### {negative_prompt}"
        if seed is not None and seed != -1:
            payload["params"]["seed"] = str(seed)
        # Note: Horde doesn't have a native worker blacklist via the "workers" array.
        # The "workers" array is actually a strict whitelist. If an invalid ID like "admin" is used, it fails.
        # We will ignore the UI blacklist field for now to prevent breaking generations.
        
        log_debug(f"[Horde] Submitting request. model={model} size={width}x{height} nsfw={horde_nsfw}")

        # ── Submit ───────────────────────────────────────────────────────────
        try:
            resp = requests.post(
                f"{_BASE_URL}/generate/async",
                json=payload,
                headers=headers,
                timeout=30,
                proxies=get_proxies("horde"),
            )
        except Exception as e:
            raise Exception(f"Horde submit error: {e}")

        if resp.status_code == 401:
            raise Exception("Horde: API key non valida. Usa una key valida oppure lascia vuoto per accesso anonimo.")
        if resp.status_code == 503:
            raise Exception("Horde: nessun worker disponibile per questo modello al momento.")
        if resp.status_code not in (200, 202):
            raise Exception(f"Horde submit HTTP {resp.status_code}: {resp.text[:200]}")

        job_id = resp.json().get("id")
        if not job_id:
            raise Exception(f"Horde: nessun job ID ricevuto. Risposta: {resp.text[:200]}")

        log_debug(f"[Horde] Job submitted. id={job_id}")

        # ── Poll ─────────────────────────────────────────────────────────────
        poll_url = f"{_BASE_URL}/generate/status/{job_id}"
        max_wait = 120   # seconds
        interval = 3     # seconds between checks
        elapsed  = 0

        while elapsed < max_wait:
            time.sleep(interval)
            elapsed += interval

            try:
                status_resp = requests.get(
                    poll_url,
                    headers=headers,
                    timeout=20,
                    proxies=get_proxies("horde"),
                )
            except Exception as e:
                log_debug(f"[Horde] Poll error: {e}, retrying...")
                continue

            if status_resp.status_code != 200:
                log_debug(f"[Horde] Poll HTTP {status_resp.status_code}, retrying...")
                continue

            status = status_resp.json()
            done   = status.get("done", False)
            faulted = status.get("faulted", False)
            wait_time = status.get("wait_time", "?")
            queue_pos  = status.get("queue_position", "?")

            log_debug(f"[Horde] done={done} faulted={faulted} wait={wait_time}s queue_pos={queue_pos} elapsed={elapsed}s")

            if faulted:
                raise Exception("Horde: la generazione è fallita lato worker. Riprova o cambia modello.")

            if done:
                generations = status.get("generations", [])
                if not generations:
                    raise Exception("Horde: generazione completata ma nessuna immagine ricevuta.")

                gen = generations[0]
                img_url  = gen.get("img", "")
                img_b64  = gen.get("img_base64", "")

                # ── Try URL first (r2 mode), then base64 fallback ────────────
                img_bytes = None
                if img_url and img_url.startswith("http"):
                    try:
                        dl = requests.get(img_url, timeout=30, proxies=get_proxies("horde"))
                        if dl.status_code == 200:
                            img_bytes = dl.content
                    except Exception as e:
                        log_debug(f"[Horde] URL download failed: {e}, trying base64...")

                if img_bytes is None and img_b64:
                    try:
                        img_bytes = base64.b64decode(img_b64)
                    except Exception as e:
                        raise Exception(f"Horde: impossibile decodificare l'immagine base64: {e}")

                if not img_bytes:
                    raise Exception("Horde: immagine ricevuta vuota.")

                worker_name = gen.get("worker_name", "unknown")
                horde_model = gen.get("model", model)
                log_debug(f"[Horde] Image ready. worker={worker_name} model={horde_model} size={len(img_bytes)} bytes")

                return save_image_bytes(img_bytes, "png", prompt=prompt, params={
                    "provider":         "horde",
                    "model":            horde_model,
                    "worker":           worker_name,
                    "guidance_scale":   guidance_scale,
                    "inference_steps":  num_inference_steps,
                    "nsfw":             horde_nsfw,
                })

        # ── Timeout: cancel the job ───────────────────────────────────────────
        try:
            requests.delete(poll_url, headers=headers, timeout=10, proxies=get_proxies("horde"))
        except Exception:
            pass
        raise Exception(f"Horde: timeout dopo {max_wait}s. Il cluster potrebbe essere occupato. Riprova tra qualche minuto.")
