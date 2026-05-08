"""The Mistral AI custom integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, LOGGER
from .coordinator import MistralAIConfigEntry, MistralCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

PLATFORMS = (Platform.CONVERSATION, Platform.STT, Platform.TTS)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Mistral AI integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MistralAIConfigEntry) -> bool:
    """Set up Mistral AI from a config entry."""
    coordinator = MistralCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    LOGGER.debug(
        "Available Mistral models: %s",
        [model.id for model in coordinator.data.models],
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MistralAIConfigEntry) -> bool:
    """Unload Mistral AI."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(
    hass: HomeAssistant, entry: MistralAIConfigEntry
) -> None:
    """Reload the integration after updates."""
    await hass.config_entries.async_reload(entry.entry_id)
