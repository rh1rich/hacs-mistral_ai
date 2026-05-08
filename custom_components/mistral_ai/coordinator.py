"""Shared runtime data for the Mistral AI custom integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

import httpx
from mistralai.client import Mistral, errors as mistral_errors, models as mistral_models

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import API_TIMEOUT_MS, DOMAIN, LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type MistralModelCard = mistral_models.BaseModelCard | mistral_models.FTModelCard
type MistralAIConfigEntry = ConfigEntry[MistralCoordinator]

CATALOG_REFRESH_INTERVAL = timedelta(hours=12)


@dataclass(slots=True)
class MistralCatalog:
    """Cached provider metadata."""

    models: list[MistralModelCard]
    voices: list[mistral_models.VoiceResponse]


class MistralCoordinator(DataUpdateCoordinator[MistralCatalog]):
    """Fetch and cache provider metadata shared by all entities."""

    config_entry: MistralAIConfigEntry
    client: Mistral

    def __init__(self, hass: HomeAssistant, config_entry: MistralAIConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=CATALOG_REFRESH_INTERVAL,
        )
        self.config_entry = config_entry
        self.client = Mistral(
            api_key=config_entry.data[CONF_API_KEY],
            async_client=get_async_client(hass),
            timeout_ms=API_TIMEOUT_MS,
        )

    async def _async_fetch_voices(self) -> list[mistral_models.VoiceResponse]:
        """Fetch the configured voice catalog."""
        voice_list = await self.client.audio.voices.list_async(
            limit=100,
            timeout_ms=API_TIMEOUT_MS,
        )
        return voice_list.items

    async def _async_update_data(self) -> MistralCatalog:
        """Fetch provider metadata."""
        try:
            model_list = await self.client.models.list_async(timeout_ms=API_TIMEOUT_MS)
            try:
                voices = await self._async_fetch_voices()
            except mistral_errors.MistralError as err:
                LOGGER.debug("Unable to fetch Mistral voices: %s", err)
                voices = []
        except mistral_errors.MistralError as err:
            if err.status_code in (401, 403):
                raise ConfigEntryAuthFailed(
                    "Authentication with Mistral failed"
                ) from err
            raise UpdateFailed(f"Error communicating with Mistral: {err}") from err
        except (mistral_errors.NoResponseError, httpx.HTTPError, TimeoutError) as err:
            raise UpdateFailed(f"Error communicating with Mistral: {err}") from err

        models = [
            model
            for model in (model_list.data or [])
            if isinstance(
                model, mistral_models.BaseModelCard | mistral_models.FTModelCard
            )
        ]
        return MistralCatalog(models=models, voices=voices)

    def iter_models_with_capability(self, capability: str) -> list[MistralModelCard]:
        """Return models supporting a given capability."""
        return [
            model
            for model in getattr(self, "data", MistralCatalog([], [])).models
            if getattr(model.capabilities, capability, False)
        ]

    def iter_stt_models(self) -> list[MistralModelCard]:
        """Return models suitable for speech-to-text."""
        return [
            model
            for model in getattr(self, "data", MistralCatalog([], [])).models
            if getattr(model.capabilities, "audio_transcription", False)
            # or getattr(model.capabilities, "audio_transcription_realtime", False)
        ]

    def iter_tts_models(self) -> list[MistralModelCard]:
        """Return models suitable for text-to-speech."""
        return [
            model
            for model in getattr(self, "data", MistralCatalog([], [])).models
            if getattr(model.capabilities, "audio_speech", False)
        ]

    def get_model_display_name(self, model_id: str) -> str:
        """Return a human-friendly display name for a model ID."""
        for model in getattr(self, "data", MistralCatalog([], [])).models:
            aliases = model.aliases or []
            if model.id == model_id or model_id in aliases:
                if (
                    isinstance(model.name, str)
                    and model.name
                    and model.name != model.id
                ):
                    return f"{model.name} ({model.id})"
                return model.id
        return model_id

    def get_voice(self, voice_id: str | None) -> mistral_models.VoiceResponse | None:
        """Return a configured voice by ID."""
        if voice_id is None:
            return None
        for voice in getattr(self, "data", MistralCatalog([], [])).voices:
            if voice.id == voice_id:
                return voice
        return None
