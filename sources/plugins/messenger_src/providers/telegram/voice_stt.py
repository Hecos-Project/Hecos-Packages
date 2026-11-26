"""
Voice-note OGG-to-text transcription helper for inbound Telegram messages.
Isolated from polling/provider logic to keep modules focused.
"""

from __future__ import annotations

import io


def transcribe_ogg_voice_bytes(ogg_bytes: bytes | bytearray) -> str:
    """
    Converts raw OGG Opus voice bytes into WAV in memory and transcribes
    using SpeechRecognition in the configured Hecos language.
    """
    import soundfile as sf
    import speech_recognition as sr

    data, samplerate = sf.read(io.BytesIO(ogg_bytes))
    wav_io = io.BytesIO()
    sf.write(wav_io, data, samplerate, format="WAV")
    wav_io.seek(0)

    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_io) as source:
        audio_data = recognizer.record(source)

    lang = "it-IT"
    try:
        from hecos.core.audio.device_manager import get_audio_config
        conf = get_audio_config() or {}
        if conf.get("language"):
            lang = conf["language"]
    except Exception:
        pass

    return recognizer.recognize_google(audio_data, language=lang)
