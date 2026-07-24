"""
image_gen — HuggingFace Provider (SDK-based)
Uses the official huggingface_hub InferenceClient for robust,
deprecation-resistant image generation.
"""
import os
import io
from .utils import log_debug, save_image_bytes, ensure_english_prompt
import traceback


class HuggingFaceProvider:
    NAME = "huggingface"

    @staticmethod
    def get_models() -> list:
        return [
            "black-forest-labs/FLUX.1-schnell",
            "stabilityai/stable-diffusion-3.5-large",
            "stabilityai/stable-diffusion-xl-base-1.0",
        ]

    @staticmethod
    def generate(prompt: str, width: int, height: int, model: str, api_key: str = "",
                 negative_prompt: str = "", guidance_scale: float = 7.5,
                 num_inference_steps: int = 30, seed: int = -1,
                 sampler: str = "", scheduler: str = "",
                 hf_provider: str = "hf-inference") -> str:
        """
        Generate an image via HuggingFace InferenceClient (official SDK).
        hf_provider: the HF inference server to use (e.g. 'hf-inference', 'fal-ai', 'together', 'replicate').
        Returns the filename of the saved image.
        """
        if not api_key:
            api_key = os.environ.get("HUGGINGFACE_API_KEY", "").strip()
        if not api_key:
            raise Exception("Hugging Face API key not set. Add HUGGINGFACE_API_KEY to .env")

        try:
            from huggingface_hub import InferenceClient
        except ImportError:
            raise Exception(
                "huggingface_hub package is not installed. "
                "Run: pip install huggingface_hub Pillow"
            )

        if not model:
            model = "black-forest-labs/FLUX.1-schnell"  # Imposta un modello di default valido se assente

        # Mappatura degli alias (selezionati tipicamente nella configurazione o UI)
        # ai repository reali di HuggingFace per evitare l'errore 404/410.
        aliases = {
            "flux": "black-forest-labs/FLUX.1-schnell",
            "flux-schnell": "black-forest-labs/FLUX.1-schnell",
            "flux-dev": "black-forest-labs/FLUX.1-dev",
            "flux-pro": "black-forest-labs/FLUX.1-schnell",  # Fallback a schnell se pro non accessibile via SDK gratuito
            "flux-realism": "black-forest-labs/FLUX.1-schnell",
            "sdxl": "stabilityai/stable-diffusion-xl-base-1.0",
            "sd3": "stabilityai/stable-diffusion-3.5-large",
            "turbo": "stabilityai/sdxl-turbo",
        }
        
        # Sostituisce il modello se esiste negli alias, altrimenti usa quello passato
        actual_model = aliases.get(model.lower().strip(), model)

        eng_prompt = ensure_english_prompt(prompt)
        safe_api_key = api_key[:4] + "***" + api_key[-4:] if len(api_key) > 8 else "***"
        log_debug(f"[HuggingFace SDK] Inizio generazione. original_model={model} mapped_model={actual_model} prompt={eng_prompt[:60]} key={safe_api_key}")

        # Build kwargs — only pass supported params
        kwargs = {
            "prompt": eng_prompt,
            "width": width,
            "height": height,
        }
        
        # Pass model only if it's explicitly required or we have a default
        if actual_model:
            kwargs["model"] = actual_model

        if negative_prompt and negative_prompt.strip():
            kwargs["negative_prompt"] = negative_prompt

        if num_inference_steps and num_inference_steps > 0:
            kwargs["num_inference_steps"] = num_inference_steps

        # FLUX models do not support guidance_scale / scheduler
        is_flux = "flux" in actual_model.lower()
        if not is_flux:
            if guidance_scale and guidance_scale > 0:
                kwargs["guidance_scale"] = guidance_scale
            if scheduler and scheduler.lower() not in ("", "none"):
                kwargs["scheduler"] = scheduler

        if seed is not None and seed != -1:
            kwargs["seed"] = seed

        log_debug(f"[HuggingFace SDK] hf_provider ricevuto come parametro: '{hf_provider}'")        
            
        try:
            # Force hf-inference or external provider (e.g., together)
            client = InferenceClient(provider=hf_provider, api_key=api_key)
            log_debug(f"[HuggingFace SDK] Client inizializzato con provider '{hf_provider}'")
            log_debug(f"[HuggingFace SDK] Calling text_to_image with kwargs: {kwargs}")
            
            # Using parameters wrapping as sometimes external providers require parameters explicitly
            # but standard SDK `text_to_image` signature unpacks kwargs. We pass them as **kwargs.
            pil_image = client.text_to_image(**kwargs)
            log_debug("[HuggingFace SDK] text_to_image completato con successo al primo tentativo.")
        except Exception as e:
            err = str(e)
            err_type = type(e).__name__
            log_debug(f"[HuggingFace SDK] Errore di tipo '{err_type}' durante la generazione.")
            log_debug(f"[HuggingFace SDK] Traceback completo:\n{traceback.format_exc()}")
            
            # Identify known HTTP errors dynamically
            status_code = None
            if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                status_code = getattr(e.response, 'status_code')
            
            friendly_err = err
            if status_code:
                log_debug(f"[HuggingFace SDK] HTTP Status Code intercettato: {status_code}")
                if status_code == 401:
                    friendly_err = f"API Key non valida o mancante (401 Unauthorized) per il provider '{hf_provider}'."
                elif status_code == 403:
                    friendly_err = f"Accesso negato (403 Forbidden). Verifica i permessi per '{actual_model}' o per il provider '{hf_provider}'."
                elif status_code == 404:
                    friendly_err = f"Modello '{actual_model}' non trovato (404 Not Found). Potrebbe non essere supportato dal provider '{hf_provider}'."
                elif status_code == 410:
                    friendly_err = f"Modello rimosso (410 Gone). Il modello '{actual_model}' non è più disponibile o è stato rimosso dal provider '{hf_provider}'."
                elif status_code == 429:
                    friendly_err = "Limite di richieste superato (429 Too Many Requests). Attendi qualche istante e riprova."
                elif status_code == 500:
                    friendly_err = f"Errore interno del server (500). Il provider '{hf_provider}' sta avendo problemi temporanei."
                elif status_code == 503:
                    friendly_err = "Servizio non disponibile (503 Service Unavailable). Il modello sta caricando o il server è sovraccarico."
                
                # Se abbiamo intercettato un errore di rete chiaro, possiamo propagarlo subito per evitare retry inutili
                if status_code in (401, 403, 404, 410):
                    raise Exception(f"HuggingFace SDK error: {friendly_err}")
            
            # Retry without optional params that some models don't support
            if any(k in err for k in ("negative_prompt", "num_inference_steps", "scheduler", "guidance_scale")):
                log_debug("[HuggingFace SDK] Parametro non supportato rilevato, tento retry con parametri minimi...")
                try:
                    client = InferenceClient(provider=hf_provider, api_key=api_key)
                    pil_image = client.text_to_image(
                        prompt=eng_prompt,
                        model=actual_model,
                        width=width,
                        height=height
                    )
                    log_debug("[HuggingFace SDK] text_to_image completato con successo al secondo tentativo (retry).")
                except Exception as e2:
                    log_debug(f"[HuggingFace SDK] Errore anche nel retry:\n{traceback.format_exc()}")
                    raise Exception(f"HuggingFace SDK error: Retry fallito. {str(e2)}")
            else:
                raise Exception(f"HuggingFace SDK error: {friendly_err}")

        # Convert PIL.Image to bytes (PNG)
        try:
            buf = io.BytesIO()
            pil_image.save(buf, format="PNG")
            image_bytes = buf.getvalue()
        except Exception as e:
            raise Exception(f"HuggingFace: failed to convert image to bytes: {e}")

        log_debug(f"[HuggingFace SDK] Image generated, size={len(image_bytes)} bytes")

        return save_image_bytes(image_bytes, "png", prompt=prompt, params={
            "provider": "huggingface",
            "model": actual_model,
            "guidance_scale": guidance_scale if not is_flux else "N/A",
            "inference_steps": num_inference_steps,
            "seed": seed,
        })
