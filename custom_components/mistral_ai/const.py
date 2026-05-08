"""Constants for the Mistral AI custom integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.helpers import llm

DOMAIN = "mistral_ai"
LOGGER = logging.getLogger(__package__)

API_TIMEOUT_MS = 30_000
MAX_TOOL_ITERATIONS = 10

DEFAULT_NAME = "Mistral AI"
DEFAULT_CONVERSATION_NAME = "Mistral AI Conversation"
DEFAULT_STT_NAME = "Mistral AI Speech-to-Text"
DEFAULT_TTS_NAME = "Mistral AI Text-to-Speech"

CONF_CHAT_MODEL = "chat_model"
CONF_LANGUAGE = "language"
CONF_MAX_TOKENS = "max_tokens"
CONF_PROMPT = "prompt"
CONF_RECOMMENDED = "recommended"
CONF_STT_MODEL = "stt_model"
CONF_TEMPERATURE = "temperature"
CONF_TOP_P = "top_p"
CONF_TTS_MODEL = "tts_model"

RECOMMENDED_CHAT_MODEL = "mistral-small-latest"
RECOMMENDED_STT_MODEL = "voxtral-mini-latest"
RECOMMENDED_TTS_MODEL = "voxtral-mini-tts-latest"
RECOMMENDED_TTS_LANGUAGE = "en-US"

RECOMMENDED_MAX_TOKENS = 1024
RECOMMENDED_TEMPERATURE = 0.15
RECOMMENDED_TOP_P = 1.0

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}
RECOMMENDED_STT_OPTIONS = {
    CONF_STT_MODEL: RECOMMENDED_STT_MODEL,
}
RECOMMENDED_TTS_OPTIONS = {
    CONF_TTS_MODEL: RECOMMENDED_TTS_MODEL,
    CONF_LANGUAGE: RECOMMENDED_TTS_LANGUAGE,
}

SUPPORTED_STT_LANGUAGES = [
    "af-ZA",
    "ar-SA",
    "hy-AM",
    "az-AZ",
    "be-BY",
    "bs-BA",
    "bg-BG",
    "ca-ES",
    "zh-CN",
    "hr-HR",
    "cs-CZ",
    "da-DK",
    "nl-NL",
    "en-US",
    "et-EE",
    "fi-FI",
    "fr-FR",
    "gl-ES",
    "de-DE",
    "el-GR",
    "he-IL",
    "hi-IN",
    "hu-HU",
    "is-IS",
    "id-ID",
    "it-IT",
    "ja-JP",
    "kn-IN",
    "kk-KZ",
    "ko-KR",
    "lv-LV",
    "lt-LT",
    "mk-MK",
    "ms-MY",
    "mr-IN",
    "mi-NZ",
    "ne-NP",
    "no-NO",
    "fa-IR",
    "pl-PL",
    "pt-PT",
    "ro-RO",
    "ru-RU",
    "sr-RS",
    "sk-SK",
    "sl-SI",
    "es-ES",
    "sw-KE",
    "sv-SE",
    "fil-PH",
    "ta-IN",
    "th-TH",
    "tr-TR",
    "uk-UA",
    "ur-PK",
    "vi-VN",
    "cy-GB",
]

SUPPORTED_TTS_FORMATS = ["mp3", "opus", "wav", "flac", "pcm"]
