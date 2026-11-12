"""
Voice Forge - Multilingual Calibration Corpus
Provides phonetically rich and balanced reference sentences for Fish Speech.
Ensures the reference audio and text match the target language precisely,
preventing foreign accent contamination.
"""

from typing import Dict, List

# Phonetically balanced sentences and pangrams for each supported language
CORPUS_BY_LANGUAGE: Dict[str, Dict[str, any]] = {
    "it": {
        "name": "Italiano",
        "flag": "🇮🇹",
        "default_text": "Ma la volpe col suo balzo ha raggiunto il quieto fante all'ombra del tiglio fiorito.",
        "samples": [
            {
                "id": "it_narrative_1",
                "label": "Narrativo (Pangramma fonetico equilibrato)",
                "text": "Ma la volpe col suo balzo ha raggiunto il quieto fante all'ombra del tiglio fiorito."
            },
            {
                "id": "it_conversational_1",
                "label": "Conversazionale naturale",
                "text": "Buongiorno! Ho preparato tutto per la giornata di oggi. Possiamo iniziare subito con il nostro lavoro."
            },
            {
                "id": "it_dynamic_1",
                "label": "Dinamico ed espressivo",
                "text": "Ascoltami bene: questo è un momento straordinario, e ogni dettaglio può fare davvero la differenza!"
            }
        ]
    },
    "en": {
        "name": "English",
        "flag": "🇬🇧",
        "default_text": "The quick brown fox jumps over the lazy dog near the vibrant riverbank.",
        "samples": [
            {
                "id": "en_narrative_1",
                "label": "Narrative (Classic phonetic pangram)",
                "text": "The quick brown fox jumps over the lazy dog near the vibrant riverbank."
            },
            {
                "id": "en_conversational_1",
                "label": "Natural Conversational",
                "text": "Hello there! Everything is ready for our session today. Let's get started whenever you are ready."
            },
            {
                "id": "en_dynamic_1",
                "label": "Dynamic & Expressive",
                "text": "Listen carefully: this is an incredible opportunity, and every single step counts towards our goal."
            }
        ]
    },
    "de": {
        "name": "Deutsch",
        "flag": "🇩🇪",
        "default_text": "Zwölf Boxkämpfer jagen Viktor quer über den großen Sylter Deich.",
        "samples": [
            {
                "id": "de_narrative_1",
                "label": "Klassisches Pangramm",
                "text": "Zwölf Boxkämpfer jagen Viktor quer über den großen Sylter Deich."
            },
            {
                "id": "de_conversational_1",
                "label": "Natürliche Konversation",
                "text": "Guten Tag! Ich habe alles für heute vorbereitet. Wir können jederzeit mit der Arbeit beginnen."
            }
        ]
    },
    "fr": {
        "name": "Français",
        "flag": "🇫🇷",
        "default_text": "Portez ce vieux whisky au juge blond qui fume un cigare près du grand pont.",
        "samples": [
            {
                "id": "fr_narrative_1",
                "label": "Pangramme classique",
                "text": "Portez ce vieux whisky au juge blond qui fume un cigare près du grand pont."
            },
            {
                "id": "fr_conversational_1",
                "label": "Conversation naturelle",
                "text": "Bonjour ! Tout est prêt pour notre séance d'aujourd'hui. Nous pouvons commencer dès que vous le souhaitez."
            }
        ]
    },
    "es": {
        "name": "Español",
        "flag": "🇪🇸",
        "default_text": "El veloz murciélago hindú comía feliz cardillo y kiwi bajo la sombra del pinar.",
        "samples": [
            {
                "id": "es_narrative_1",
                "label": "Pangrama fonético",
                "text": "El veloz murciélago hindú comía feliz cardillo y kiwi bajo la sombra del pinar."
            },
            {
                "id": "es_conversational_1",
                "label": "Conversacional natural",
                "text": "¡Hola! He preparado todo para la jornada de hoy. Podemos comenzar en cuanto estés listo."
            }
        ]
    },
    "ja": {
        "name": "日本語 (Japanese)",
        "flag": "🇯🇵",
        "default_text": "いろはにほへと ちりぬるを わかよたれそ つねならむ うゐのおくやま けふこえて あさきゆめみし ゑひもせす。",
        "samples": [
            {
                "id": "ja_iroha",
                "label": "いろは歌 (Iroha classic)",
                "text": "いろはにほへと ちりぬるを わかよたれそ つねならむ うゐのおくやま けふこえて あさきゆめみし ゑひもせす。"
            },
            {
                "id": "ja_conversational",
                "label": "日常会話 (Natural conversation)",
                "text": "こんにちは！本日の準備はすべて整いました。いつでも作業を始められますよ。"
            }
        ]
    },
    "zh": {
        "name": "中文 (Chinese)",
        "flag": "🇨🇳",
        "default_text": "天地玄黄，宇宙洪荒。日月盈昃，辰宿列张。寒来暑往，秋收冬藏。",
        "samples": [
            {
                "id": "zh_qianziwen",
                "label": "千字文 (Qianziwen)",
                "text": "天地玄黄，宇宙洪荒。日月盈昃，辰宿列张。寒来暑往，秋收冬藏。"
            },
            {
                "id": "zh_conversational",
                "label": "日常对话 (Natural conversation)",
                "text": "你好！今天的所有准备工作都已经完成了。我们随时可以开始。"
            }
        ]
    }
}

def get_languages() -> List[Dict[str, str]]:
    """Returns list of supported languages with code, name and flag."""
    return [
        {"code": code, "name": data["name"], "flag": data["flag"]}
        for code, data in CORPUS_BY_LANGUAGE.items()
    ]

def get_corpus_languages() -> List[Dict[str, str]]:
    """Alias for get_languages."""
    return get_languages()

def get_default_text_for_language(lang: str) -> str:
    """Returns the default phonetically balanced text for the given language."""
    data = CORPUS_BY_LANGUAGE.get(lang.lower(), CORPUS_BY_LANGUAGE["it"])
    return data["default_text"]

def get_samples_for_language(lang: str) -> List[Dict[str, str]]:
    """Returns the sample texts for the given language."""
    data = CORPUS_BY_LANGUAGE.get(lang.lower(), CORPUS_BY_LANGUAGE["it"])
    return data.get("samples", [])

def get_all_samples_for_language(lang: str) -> List[Dict[str, str]]:
    """Alias for get_samples_for_language."""
    return get_samples_for_language(lang)

def get_calibration_sample(lang: str, sample_type: str = "narrative") -> Dict[str, str]:
    """Returns a specific calibration sample or the first available for the language."""
    samples = get_samples_for_language(lang)
    for s in samples:
        if sample_type.lower() in s.get("id", "").lower() or sample_type.lower() in s.get("label", "").lower():
            return s
    if samples:
        return samples[0]
    return {
        "id": f"{lang}_default",
        "label": "Default",
        "text": get_default_text_for_language(lang)
    }

