"""Text-to-speech platform for the Mistral AI custom integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from mistralai.client import errors as mistral_errors, models as mistral_models

from homeassistant.components.tts import (
    ATTR_PREFERRED_FORMAT,
    ATTR_VOICE,
    TextToSpeechEntity,
    TtsAudioType,
    Voice,
)
from homeassistant.components.tts.entity import TTSAudioRequest, TTSAudioResponse
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import language as language_util

from .const import (
    API_TIMEOUT_MS,
    CONF_LANGUAGE,
    CONF_TTS_MODEL,
    RECOMMENDED_TTS_LANGUAGE,
    RECOMMENDED_TTS_MODEL,
    SUPPORTED_TTS_FORMATS,
)
from .entity import MistralAIBaseEntity, _decode_base64_audio

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping

    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import MistralAIConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MistralAIConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up TTS entities."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "tts":
            continue

        async_add_entities(
            [MistralAITTSEntity(config_entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


def _normalize_output_format(
    requested_format: str | None,
) -> mistral_models.SpeechOutputFormat:
    """Normalize Home Assistant audio format aliases to Mistral output formats."""
    if requested_format in SUPPORTED_TTS_FORMATS:
        return cast("mistral_models.SpeechOutputFormat", requested_format)
    if requested_format == "ogg":
        return "opus"
    if requested_format == "raw":
        return "pcm"
    return "wav"


class MistralAITTSEntity(TextToSpeechEntity, MistralAIBaseEntity):
    """Mistral AI text-to-speech entity."""

    _attr_supported_options = [ATTR_VOICE, ATTR_PREFERRED_FORMAT]

    @property
    def supported_languages(self) -> list[str]:
        """Return languages supported by the current voice catalog."""
        languages = sorted(
            {
                language
                for voice in self.coordinator.data.voices
                for language in voice.languages or []
            },
            key=str.casefold,
        )
        return languages or [RECOMMENDED_TTS_LANGUAGE]

    @property
    def default_language(self) -> str:
        """Return the default language."""
        return self.subentry.data.get(CONF_LANGUAGE, self.supported_languages[0])

    @property
    def default_options(self) -> Mapping[str, Any]:
        """Return default TTS options."""
        return {
            ATTR_VOICE: self._select_voice_id({}, self.default_language) or "",
            ATTR_PREFERRED_FORMAT: "wav",
        }

    @callback
    def async_get_supported_voices(self, language: str) -> list[Voice]:
        """Return supported voices for a language."""
        supported_voices: list[Voice] = [
            Voice(v.id, v.name) for v in self.coordinator.data.voices
        ]
        return supported_voices

    def _select_voice_id(self, options: dict[str, Any], language: str) -> str | None:
        """Return the preferred voice for a request."""
        configured_voice_id = options.get(ATTR_VOICE) or self.subentry.data.get(
            ATTR_VOICE
        )
        if configured_voice_id:
            return configured_voice_id

        supported_voices = self.async_get_supported_voices(language)
        if supported_voices:
            return supported_voices[0].voice_id

        if self.coordinator.data.voices:
            return self.coordinator.data.voices[0].id

        return None

    async def async_get_tts_audio(
        self, message: str, language: str, options: dict[str, Any]
    ) -> TtsAudioType:
        """Generate a non-streaming TTS response."""
        merged_options = {**self.subentry.data, **self.default_options, **options}
        voice_id = self._select_voice_id(merged_options, language)
        if voice_id is None:
            raise HomeAssistantError("No Mistral voice is available for text-to-speech")

        output_format = _normalize_output_format(
            merged_options.get(ATTR_PREFERRED_FORMAT)
        )

        try:
            response = await self.coordinator.client.audio.speech.complete_async(
                input=message,
                model=merged_options.get(CONF_TTS_MODEL, RECOMMENDED_TTS_MODEL),
                voice_id=voice_id,
                response_format=output_format,
                timeout_ms=API_TIMEOUT_MS,
            )
        except (mistral_errors.MistralError, mistral_errors.NoResponseError) as err:
            self._raise_runtime_error(err)

        if not isinstance(response, mistral_models.SpeechResponse):
            raise HomeAssistantError("Unexpected response returned by Mistral TTS")

        return output_format, _decode_base64_audio(response.audio_data)

    async def async_stream_tts_audio(
        self, request: TTSAudioRequest
    ) -> TTSAudioResponse:
        """Generate a streaming TTS response."""
        merged_options = {
            **self.subentry.data,
            **self.default_options,
            **request.options,
        }
        output_format = _normalize_output_format(
            merged_options.get(ATTR_PREFERRED_FORMAT)
        )
        voice_id = self._select_voice_id(merged_options, request.language)
        if voice_id is None:
            raise HomeAssistantError("No Mistral voice is available for text-to-speech")

        message = "".join([chunk async for chunk in request.message_gen])

        async def data_gen() -> AsyncGenerator[bytes]:
            try:
                response_stream = (
                    await self.coordinator.client.audio.speech.complete_async(
                        input=message,
                        model=merged_options.get(CONF_TTS_MODEL, RECOMMENDED_TTS_MODEL),
                        stream=True,
                        voice_id=voice_id,
                        response_format=output_format,
                        timeout_ms=API_TIMEOUT_MS,
                    )
                )
                async with response_stream:
                    async for event in response_stream:
                        if isinstance(
                            event.data, mistral_models.SpeechStreamAudioDelta
                        ):
                            yield _decode_base64_audio(event.data.audio_data)
            except (mistral_errors.MistralError, mistral_errors.NoResponseError) as err:
                self._raise_runtime_error(err)

        return TTSAudioResponse(output_format, data_gen())
