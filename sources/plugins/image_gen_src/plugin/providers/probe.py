"""
image_gen — Provider Probe / Diagnostica
Testa tutti i provider e i server HuggingFace disponibili.
Nessuna dipendenza da hecos.core. Funziona in ambienti isolati.
"""
import time
import concurrent.futures
from .utils import log_debug

# ── Configurazione server HuggingFace da testare ────────────────────────────────
_HF_TEST_MODEL  = "black-forest-labs/FLUX.1-schnell"
_HF_TEST_WIDTH  = 256
_HF_TEST_HEIGHT = 256
_HF_TEST_PROMPT = "a blue circle"

_HF_SERVERS = [
    ("novita",           "Novita AI (novita)"),
    ("nscale",           "Nscale (nscale)"),
    ("deepinfra",        "Deep Infra (deepinfra)"),
    ("fireworks-ai",     "Fireworks AI (fireworks-ai)"),
    ("scaleway",         "Scaleway (scaleway)"),
    ("together",         "Together AI (together)"),
    ("replicate",        "Replicate (replicate)"),
]

# ── Probe HuggingFace server ─────────────────────────────────────────────────────

def _probe_hf_server(server_id: str, server_label: str, api_key: str) -> dict:
    if not api_key:
        return {
            "name": f"HuggingFace / {server_label}",
            "server_id": server_id,
            "ok": False,
            "error": "API key mancante — impossibile testare.",
            "latency_ms": None,
        }
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        return {
            "name": f"HuggingFace / {server_label}",
            "server_id": server_id,
            "ok": False,
            "error": "huggingface_hub non installato (pip install huggingface_hub).",
            "latency_ms": None,
        }

    start = time.monotonic()
    try:
        client = InferenceClient(provider=server_id, api_key=api_key)
        pil_image = client.text_to_image(
            prompt=_HF_TEST_PROMPT,
            model=_HF_TEST_MODEL,
            width=_HF_TEST_WIDTH,
            height=_HF_TEST_HEIGHT,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        if pil_image is None:
            raise ValueError("Il provider ha restituito None invece di un'immagine.")
        log_debug(f"[Probe] HF/{server_id} OK in {elapsed}ms")
        return {
            "name": f"HuggingFace / {server_label}",
            "server_id": server_id,
            "ok": True,
            "latency_ms": elapsed,
            "error": None,
        }
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        err_str = str(e)
        if "401" in err_str: err_str = "API Key non valida (401 Unauthorized)"
        elif "403" in err_str: err_str = "Accesso negato (403 Forbidden)"
        elif "404" in err_str: err_str = "Modello non trovato su questo server (404)"
        elif "410" in err_str: err_str = "Modello rimosso da questo server (410 Gone)"
        elif "429" in err_str: err_str = "Limite richieste (429 Too Many Requests)"
        elif "503" in err_str: err_str = "Server sovraccarico (503)"
        log_debug(f"[Probe] HF/{server_id} FAIL in {elapsed}ms: {err_str}")
        return {
            "name": f"HuggingFace / {server_label}",
            "server_id": server_id,
            "ok": False,
            "latency_ms": elapsed,
            "error": err_str,
        }


# ── Probe provider gratuiti ───────────────────────────────────────────────────────

def _probe_pollinations() -> dict:
    import urllib.request
    start = time.monotonic()
    try:
        req = urllib.request.Request(
            "https://image.pollinations.ai/models",
            headers={"User-Agent": "Hecos/probe"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            r.read(64)
        elapsed = int((time.monotonic() - start) * 1000)
        return {"name": "Pollinations (Free)", "ok": True, "latency_ms": elapsed, "error": None}
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return {"name": "Pollinations (Free)", "ok": False, "latency_ms": elapsed, "error": str(e)[:80]}


def _probe_airforce() -> dict:
    import urllib.request
    start = time.monotonic()
    try:
        req = urllib.request.Request(
            "https://api.airforce/imagine2?prompt=test&model=flux&size=256x256",
            headers={"User-Agent": "Hecos/probe"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            r.read(64)
        elapsed = int((time.monotonic() - start) * 1000)
        return {"name": "Airforce (Free)", "ok": True, "latency_ms": elapsed, "error": None}
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return {"name": "Airforce (Free)", "ok": False, "latency_ms": elapsed, "error": str(e)[:80]}


# ── Probe Altri Provider API (Gemini, OpenAI, Stability) ─────────────────────────

def _probe_gemini(api_key: str) -> dict:
    """Probe Gemini Imagen via Vertex AI Express (v1beta predict endpoint).
    Note: imagen-3 requires Vertex AI; for free API keys this endpoint returns 404.
    We probe the models list instead to validate the key."""
    if not api_key: return {"name": "Google Gemini (Imagen)", "ok": False, "error": "API Key mancante", "latency_ms": None}
    import urllib.request, json
    start = time.monotonic()
    try:
        # Validate key by listing available models — works with standard API keys
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            body = json.loads(r.read())
        elapsed = int((time.monotonic() - start) * 1000)
        # Check if imagen models are available
        model_ids = [m.get("name", "") for m in body.get("models", [])]
        has_imagen = any("imagen" in m for m in model_ids)
        if has_imagen:
            return {"name": "Google Gemini (Imagen)", "ok": True, "latency_ms": elapsed, "error": None}
        else:
            return {"name": "Google Gemini (Imagen)", "ok": False, "latency_ms": elapsed,
                    "error": "Key valida ma Imagen non disponibile (richiede Vertex AI / Piano a pagamento)"}
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        err_s = str(e)
        if "403" in err_s: err_s = "403: API key non autorizzata per questo progetto"
        elif "401" in err_s: err_s = "401: API Key non valida"
        return {"name": "Google Gemini (Imagen)", "ok": False, "latency_ms": elapsed, "error": err_s}

def _probe_gemini_native(api_key: str) -> dict:
    """Probe Gemini 2.0 Flash native image generation (free tier, available to all API keys)."""
    if not api_key: return {"name": "Gemini Native (Flash)", "ok": False, "error": "API Key mancante", "latency_ms": None}
    import urllib.request, json
    start = time.monotonic()
    try:
        # Use the preview model name (more stable)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-preview-image-generation:generateContent?key={api_key}"
        payload = json.dumps({
            "contents": [{"parts": [{"text": "a blue circle"}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read(128)
        elapsed = int((time.monotonic() - start) * 1000)
        return {"name": "Gemini Native (Flash)", "ok": True, "latency_ms": elapsed, "error": None}
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        err_s = str(e)
        if "403" in err_s: err_s = "403: API non abilitata per questo progetto"
        elif "401" in err_s: err_s = "401: API Key non valida"
        elif "404" in err_s: err_s = "404: Modello non ancora disponibile per questa chiave"
        return {"name": "Gemini Native (Flash)", "ok": False, "latency_ms": elapsed, "error": err_s}

def _probe_openai(api_key: str) -> dict:
    if not api_key: return {"name": "OpenAI (DALL-E)", "ok": False, "error": "API Key mancante", "latency_ms": None}
    import urllib.request, json
    start = time.monotonic()
    try:
        req = urllib.request.Request("https://api.openai.com/v1/images/generations",
                                     data=json.dumps({"prompt": "test", "model": "dall-e-3", "size": "1024x1024"}).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            r.read(64)
        elapsed = int((time.monotonic() - start) * 1000)
        return {"name": "OpenAI (DALL-E)", "ok": True, "latency_ms": elapsed, "error": None}
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        err = "401: API Key non valida" if "401" in str(e) else str(e)
        return {"name": "OpenAI (DALL-E)", "ok": False, "latency_ms": elapsed, "error": err}

def _probe_stability(api_key: str) -> dict:
    if not api_key: return {"name": "Stability AI", "ok": False, "error": "API Key mancante", "latency_ms": None}
    import urllib.request
    start = time.monotonic()
    try:
        # Request a simple generation to trigger auth check
        req = urllib.request.Request("https://api.stability.ai/v2beta/stable-image/generate/core",
                                     data=b"prompt=test",
                                     headers={"Authorization": f"Bearer {api_key}", "Accept": "image/*"})
        with urllib.request.urlopen(req, timeout=8) as r:
            r.read(64)
        elapsed = int((time.monotonic() - start) * 1000)
        return {"name": "Stability AI", "ok": True, "latency_ms": elapsed, "error": None}
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        err = "401: API Key non valida" if "401" in str(e) else str(e)
        return {"name": "Stability AI", "ok": False, "latency_ms": elapsed, "error": err}


# ── Entry point ──────────────────────────────────────────────────────────────────

def probe_all_providers(keys: dict = None) -> list:
    """
    Testa tutti i provider e i server HuggingFace in parallelo.
    keys: { "huggingface": "...", "gemini": "...", "openai": "...", "stability": "..." }
    Restituisce lista di dict: name, ok, latency_ms, error.
    """
    if keys is None: keys = {}
    hf_api_key = keys.get("huggingface", "")
    log_debug(f"[Probe] Avvio probe completo. Chiavi trovate: {list(keys.keys())}")
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        futures[executor.submit(_probe_pollinations)] = "pollinations"
        futures[executor.submit(_probe_airforce)] = "airforce"
        futures[executor.submit(_probe_gemini, keys.get("gemini", ""))] = "gemini"
        futures[executor.submit(_probe_gemini_native, keys.get("gemini", ""))] = "gemini_native"
        futures[executor.submit(_probe_openai, keys.get("openai", ""))] = "openai"
        futures[executor.submit(_probe_stability, keys.get("stability", ""))] = "stability"

        for server_id, server_label in _HF_SERVERS:
            futures[executor.submit(_probe_hf_server, server_id, server_label, hf_api_key)] = f"hf/{server_id}"

        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                results.append({
                    "name": futures[future],
                    "ok": False,
                    "error": str(e),
                    "latency_ms": None
                })

    results.sort(key=lambda r: (0 if r["ok"] else 1, r.get("latency_ms") or 9999))
    log_debug(f"[Probe] Completato. {sum(1 for r in results if r['ok'])}/{len(results)} provider OK.")
    return results
