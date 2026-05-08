"""Config flow for the Mistral AI custom integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
from mistralai.client import Mistral, errors as mistral_errors
import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
)

from .const import (
    API_TIMEOUT_MS,
    CONF_CHAT_MODEL,
    CONF_LANGUAGE,
    CONF_MAX_TOKENS,
    CONF_PROMPT,
    CONF_RECOMMENDED,
    CONF_STT_MODEL,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    CONF_TTS_MODEL,
    DEFAULT_CONVERSATION_NAME,
    DEFAULT_NAME,
    DEFAULT_STT_NAME,
    DEFAULT_TTS_NAME,
    DOMAIN,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_CONVERSATION_OPTIONS,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_STT_MODEL,
    RECOMMENDED_STT_OPTIONS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
    RECOMMENDED_TTS_LANGUAGE,
    RECOMMENDED_TTS_MODEL,
    RECOMMENDED_TTS_OPTIONS,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.helpers.typing import VolDictType

    from .coordinator import MistralCoordinator, MistralModelCard

STEP_USER_DATA_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


def _model_label(model: MistralModelCard) -> str:
    """Return a friendly selector label for a model."""
    if isinstance(model.name, str) and model.name and model.name != model.id:
        return f"{model.name} ({model.id})"
    return model.id


def _voice_label(voice_id: str, voice_name: str) -> str:
    """Return a friendly selector label for a voice."""
    if voice_name and voice_name != voice_id:
        return f"{voice_name} ({voice_id})"
    return voice_id


def _default_subentries() -> list[ConfigSubentryData]:
    """Return the default subentries for a new config entry."""
    return [
        ConfigSubentryData(
            subentry_type="conversation",
            data=RECOMMENDED_CONVERSATION_OPTIONS.copy(),
            title=DEFAULT_CONVERSATION_NAME,
            unique_id=None,
        ),
        ConfigSubentryData(
            subentry_type="stt",
            data=RECOMMENDED_STT_OPTIONS.copy(),
            title=DEFAULT_STT_NAME,
            unique_id=None,
        ),
        ConfigSubentryData(
            subentry_type="tts",
            data=RECOMMENDED_TTS_OPTIONS.copy(),
            title=DEFAULT_TTS_NAME,
            unique_id=None,
        ),
        ConfigSubentryData(
            subentry_type="stt",
            data=RECOMMENDED_STT_OPTIONS.copy(),
            title=DEFAULT_STT_NAME,
            unique_id=None,
        ),
        ConfigSubentryData(
            subentry_type="tts",
            data=RECOMMENDED_TTS_OPTIONS.copy(),
            title=DEFAULT_TTS_NAME,
            unique_id=None,
        ),
    ]


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input by calling the provider API."""
    client = Mistral(
        api_key=data[CONF_API_KEY],
        async_client=get_async_client(hass),
        timeout_ms=API_TIMEOUT_MS,
    )
    await client.models.list_async(timeout_ms=API_TIMEOUT_MS)


def _conversation_model_options(
    coordinator: MistralCoordinator,
) -> list[SelectOptionDict]:
    """Build conversation model selector options."""
    return [
        SelectOptionDict(label=_model_label(model), value=model.id)
        for model in sorted(
            coordinator.iter_models_with_capability("completion_chat"),
            key=lambda model: _model_label(model).casefold(),
        )
    ]


def _stt_model_options(coordinator: MistralCoordinator) -> list[SelectOptionDict]:
    """Build STT model selector options."""
    return [
        SelectOptionDict(label=_model_label(model), value=model.id)
        for model in sorted(
            coordinator.iter_stt_models(),
            key=lambda model: _model_label(model).casefold(),
        )
    ]


def _tts_model_options(coordinator: MistralCoordinator) -> list[SelectOptionDict]:
    """Build TTS model selector options."""
    return [
        SelectOptionDict(label=_model_label(model), value=model.id)
        for model in sorted(
            coordinator.iter_tts_models(),
            key=lambda model: _model_label(model).casefold(),
        )
    ]


def _voice_options(coordinator: MistralCoordinator) -> list[SelectOptionDict]:
    """Build voice selector options."""
    return [
        SelectOptionDict(label=_voice_label(voice.id, voice.name), value=voice.id)
        for voice in sorted(
            coordinator.data.voices,
            key=lambda voice: _voice_label(voice.id, voice.name).casefold(),
        )
    ]


def _language_options(coordinator: MistralCoordinator) -> list[SelectOptionDict]:
    """Build TTS language selector options from the voice catalog."""
    languages = sorted(
        {
            language
            for voice in coordinator.data.voices
            for language in voice.languages or []
        },
        key=str.casefold,
    )
    return [SelectOptionDict(label=language, value=language) for language in languages]


class MistralAIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Mistral AI config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(user_input)
            try:
                await validate_input(self.hass, user_input)
            except mistral_errors.MistralError as err:
                if err.status_code in (401, 403):
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            except mistral_errors.NoResponseError, httpx.HTTPError, TimeoutError:
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - defensive custom component guard
                errors["base"] = "unknown"
            else:
                if self.source == SOURCE_REAUTH:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=user_input
                    )
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data=user_input,
                    subentries=_default_subentries(),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
            description_placeholders={
                "instructions_url": "https://docs.mistral.ai/",
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauthentication after an auth error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Prompt the user for a replacement API key."""
        if not user_input:
            return self.async_show_form(
                step_id="reauth_confirm", data_schema=STEP_USER_DATA_SCHEMA
            )

        return await self.async_step_user(user_input)

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            "conversation": MistralAIConversationSubentryFlowHandler,
            "stt": MistralAISTTSubentryFlowHandler,
            "tts": MistralAITTSSubentryFlowHandler,
        }


class MistralAIConversationSubentryFlowHandler(ConfigSubentryFlow):
    """Flow for managing Mistral conversation subentries."""

    options: dict[str, Any]

    @property
    def _is_new(self) -> bool:
        """Return whether the subentry is being created."""
        return self.source == "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a conversation subentry."""
        self.options = RECOMMENDED_CONVERSATION_OPTIONS.copy()
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure a conversation subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Configure basic conversation options."""
        if self._get_entry().state != ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        options = self.options
        hass_apis = [
            SelectOptionDict(label=api.name, value=api.id)
            for api in llm.async_get_apis(self.hass)
        ]
        if suggested_apis := options.get(CONF_LLM_HASS_API):
            if isinstance(suggested_apis, str):
                suggested_apis = [suggested_apis]
            valid_api_ids = {api.id for api in llm.async_get_apis(self.hass)}
            options[CONF_LLM_HASS_API] = [
                api_id for api_id in suggested_apis if api_id in valid_api_ids
            ]

        step_schema: VolDictType = {}

        if self._is_new:
            step_schema[vol.Required(CONF_NAME, default=DEFAULT_CONVERSATION_NAME)] = (
                str
            )

        step_schema.update(
            {
                vol.Optional(
                    CONF_PROMPT,
                    description={
                        "suggested_value": options.get(
                            CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT
                        )
                    },
                ): TemplateSelector(),
                vol.Optional(CONF_LLM_HASS_API): SelectSelector(
                    SelectSelectorConfig(options=hass_apis, multiple=True)
                ),
                vol.Required(
                    CONF_RECOMMENDED,
                    default=options.get(CONF_RECOMMENDED, True),
                ): bool,
            }
        )

        if user_input is not None:
            if not user_input.get(CONF_LLM_HASS_API):
                user_input.pop(CONF_LLM_HASS_API, None)

            if user_input[CONF_RECOMMENDED]:
                if self._is_new:
                    return self.async_create_entry(
                        title=user_input.pop(CONF_NAME),
                        data=user_input,
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    data=user_input,
                )

            options.update(user_input)
            if CONF_LLM_HASS_API in options and CONF_LLM_HASS_API not in user_input:
                options.pop(CONF_LLM_HASS_API)
            return await self.async_step_advanced()

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema), options
            ),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Configure advanced conversation options."""
        coordinator: MistralCoordinator = self._get_entry().runtime_data
        options = self.options

        step_schema: VolDictType = {
            vol.Optional(
                CONF_CHAT_MODEL,
                default=options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=_conversation_model_options(coordinator),
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_MAX_TOKENS,
                default=options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS),
            ): int,
            vol.Optional(
                CONF_TEMPERATURE,
                default=options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
            ): NumberSelector(NumberSelectorConfig(min=0, max=1.5, step=0.05)),
            vol.Optional(
                CONF_TOP_P,
                default=options.get(CONF_TOP_P, RECOMMENDED_TOP_P),
            ): NumberSelector(NumberSelectorConfig(min=0, max=1, step=0.05)),
        }

        if user_input is not None:
            options.update(user_input)
            if self._is_new:
                return self.async_create_entry(
                    title=options.pop(CONF_NAME),
                    data=options,
                )
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=options,
            )

        return self.async_show_form(
            step_id="advanced",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema), options
            ),
        )


class MistralAISTTSubentryFlowHandler(ConfigSubentryFlow):
    """Flow for managing Mistral STT subentries."""

    options: dict[str, Any]

    @property
    def _is_new(self) -> bool:
        """Return whether the subentry is being created."""
        return self.source == "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add an STT subentry."""
        self.options = RECOMMENDED_STT_OPTIONS.copy()
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure an STT subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Configure STT options."""
        if self._get_entry().state != ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        coordinator: MistralCoordinator = self._get_entry().runtime_data
        options = self.options

        step_schema: VolDictType = {}

        if self._is_new:
            step_schema[vol.Required(CONF_NAME, default=DEFAULT_STT_NAME)] = str

        step_schema[
            vol.Optional(
                CONF_STT_MODEL,
                default=options.get(CONF_STT_MODEL, RECOMMENDED_STT_MODEL),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=_stt_model_options(coordinator),
                custom_value=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        )

        if user_input is not None:
            options.update(user_input)
            if self._is_new:
                return self.async_create_entry(
                    title=options.pop(CONF_NAME),
                    data=options,
                )
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=options,
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema), options
            ),
        )


class MistralAITTSSubentryFlowHandler(ConfigSubentryFlow):
    """Flow for managing Mistral TTS subentries."""

    options: dict[str, Any]

    @property
    def _is_new(self) -> bool:
        """Return whether the subentry is being created."""
        return self.source == "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a TTS subentry."""
        self.options = RECOMMENDED_TTS_OPTIONS.copy()
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure a TTS subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Configure TTS options."""
        if self._get_entry().state != ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        coordinator: MistralCoordinator = self._get_entry().runtime_data
        options = self.options

        step_schema: VolDictType = {}

        if self._is_new:
            step_schema[vol.Required(CONF_NAME, default=DEFAULT_TTS_NAME)] = str

        step_schema.update(
            {
                vol.Optional(
                    CONF_TTS_MODEL,
                    default=options.get(CONF_TTS_MODEL, RECOMMENDED_TTS_MODEL),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=_tts_model_options(coordinator),
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_LANGUAGE,
                    default=options.get(CONF_LANGUAGE, RECOMMENDED_TTS_LANGUAGE),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=_language_options(coordinator),
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "voice",
                    default=options.get("voice", ""),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=_voice_options(coordinator),
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        if user_input is not None:
            options.update(user_input)
            if self._is_new:
                return self.async_create_entry(
                    title=options.pop(CONF_NAME),
                    data=options,
                )
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=options,
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema), options
            ),
        )
