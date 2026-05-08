"""Speech-to-text platform for the Mistral AI custom integration."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING
import wave

from mistralai.client import errors as mistral_errors, models as mistral_models

from homeassistant.components import stt

from .const import (
    API_TIMEOUT_MS,
    CONF_STT_MODEL,
    RECOMMENDED_STT_MODEL,
    SUPPORTED_STT_LANGUAGES,
)
from .entity import MistralAIBaseEntity

if TYPE_CHECKING:
    from collections.abc import AsyncIterable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import MistralAIConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MistralAIConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up STT entities."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "stt":
            continue

        async_add_entities(
            [MistralAISTTEntity(config_entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


def _audio_content_type(metadata: stt.SpeechMetadata) -> str:
    """Return the content type for an uploaded audio file."""
    if metadata.format == stt.AudioFormats.WAV:
        return "audio/wav"
    if metadata.format == stt.AudioFormats.OGG:
        return "audio/ogg"
    return f"audio/{metadata.format.value}"


class MistralAISTTEntity(stt.SpeechToTextEntity, MistralAIBaseEntity):
    """Mistral AI speech-to-text entity."""

    @property
    def supported_languages(self) -> list[str]:
        """Return supported STT languages."""
        return SUPPORTED_STT_LANGUAGES

    @property
    def supported_formats(self) -> list[stt.AudioFormats]:
        """Return supported input formats."""
        return [stt.AudioFormats.WAV, stt.AudioFormats.OGG]

    @property
    def supported_codecs(self) -> list[stt.AudioCodecs]:
        """Return supported codecs."""
        return [stt.AudioCodecs.PCM, stt.AudioCodecs.OPUS]

    @property
    def supported_bit_rates(self) -> list[stt.AudioBitRates]:
        """Return supported bit depths."""
        return [
            stt.AudioBitRates.BITRATE_8,
            stt.AudioBitRates.BITRATE_16,
            stt.AudioBitRates.BITRATE_24,
            stt.AudioBitRates.BITRATE_32,
        ]

    @property
    def supported_sample_rates(self) -> list[stt.AudioSampleRates]:
        """Return supported sample rates."""
        return [
            stt.AudioSampleRates.SAMPLERATE_8000,
            stt.AudioSampleRates.SAMPLERATE_11000,
            stt.AudioSampleRates.SAMPLERATE_16000,
            stt.AudioSampleRates.SAMPLERATE_18900,
            stt.AudioSampleRates.SAMPLERATE_22000,
            stt.AudioSampleRates.SAMPLERATE_32000,
            stt.AudioSampleRates.SAMPLERATE_37800,
            stt.AudioSampleRates.SAMPLERATE_44100,
            stt.AudioSampleRates.SAMPLERATE_48000,
        ]

    @property
    def supported_channels(self) -> list[stt.AudioChannels]:
        """Return supported channel counts."""
        return [stt.AudioChannels.CHANNEL_MONO, stt.AudioChannels.CHANNEL_STEREO]

    async def async_process_audio_stream(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> stt.SpeechResult:
        """Process an audio stream into text."""
        audio_buffer = bytearray()
        async for chunk in stream:
            audio_buffer.extend(chunk)

        audio_data = bytes(audio_buffer)
        if metadata.format == stt.AudioFormats.WAV:
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_writer:
                wav_writer.setnchannels(metadata.channel.value)
                wav_writer.setsampwidth(metadata.bit_rate.value // 8)
                wav_writer.setframerate(metadata.sample_rate.value)
                wav_writer.writeframes(audio_data)
            audio_data = wav_buffer.getvalue()

        mistral_file = mistral_models.File(
            file_name=f"speech.{metadata.format.value}",
            content=audio_data,
            content_type=_audio_content_type(metadata),
        )

        model_id = self.subentry.data.get(CONF_STT_MODEL, RECOMMENDED_STT_MODEL)
        transcript_chunks: list[str] = []

        try:
            response_stream = (
                await self.coordinator.client.audio.transcriptions.stream_async(
                    model=model_id,
                    file=mistral_file,
                    language=metadata.language.split("-")[0],
                    timeout_ms=API_TIMEOUT_MS,
                )
            )
            async with response_stream:
                async for event in response_stream:
                    if isinstance(
                        event.data, mistral_models.TranscriptionStreamTextDelta
                    ):
                        transcript_chunks.append(event.data.text)
                    elif isinstance(event.data, mistral_models.TranscriptionStreamDone):
                        final_text = event.data.text or "".join(transcript_chunks)
                        if final_text:
                            return stt.SpeechResult(
                                final_text,
                                stt.SpeechResultState.SUCCESS,
                            )
        except (mistral_errors.MistralError, mistral_errors.NoResponseError) as err:
            self._raise_runtime_error(err)

        return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
