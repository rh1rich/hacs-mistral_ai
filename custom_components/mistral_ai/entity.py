"""Shared entity helpers for the Mistral AI custom integration."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from typing import TYPE_CHECKING, Any

from mistralai.client import errors as mistral_errors, models as mistral_models
from mistralai.client.types import UNSET
from voluptuous_openapi import convert

from homeassistant.components import conversation
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, llm
from homeassistant.helpers.json import json_dumps
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.ulid import ulid_now

from .const import (
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_STT_MODEL,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    CONF_TTS_MODEL,
    DOMAIN,
    MAX_TOOL_ITERATIONS,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_STT_MODEL,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
    RECOMMENDED_TTS_MODEL,
)
from .coordinator import MistralAIConfigEntry, MistralCoordinator

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Iterable

    from mistralai.client.utils import eventstreaming

    from homeassistant.config_entries import ConfigSubentry


def _is_value_set(value: Any) -> bool:
    """Return whether a generated SDK field was populated."""
    return value is not None and value is not UNSET


def _extract_thinking_text(thinking_chunks: list[Any]) -> str:
    """Flatten nested thinking chunks into plain text."""
    return "".join(
        chunk.text
        for chunk in thinking_chunks
        if isinstance(chunk, mistral_models.TextChunk)
    )


def _extract_delta_text_and_thinking(
    delta_content: Any,
) -> tuple[str, str]:
    """Extract plain text and thinking text from a streamed content delta."""
    if not _is_value_set(delta_content):
        return "", ""

    if isinstance(delta_content, str):
        return delta_content, ""

    text_parts: list[str] = []
    thinking_parts: list[str] = []

    for content_chunk in delta_content:
        if isinstance(content_chunk, mistral_models.TextChunk):
            text_parts.append(content_chunk.text)
        elif isinstance(content_chunk, mistral_models.ThinkChunk):
            thinking_text = _extract_thinking_text(content_chunk.thinking)
            if thinking_text:
                thinking_parts.append(thinking_text)

    return "".join(text_parts), "".join(thinking_parts)


def _normalize_tool_arguments(arguments: dict[str, Any] | str | None) -> dict[str, Any]:
    """Normalize Mistral tool arguments into a dict."""
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    if not arguments:
        return {}
    return json.loads(arguments)


def _convert_content_to_mistral_messages(
    chat_content: Iterable[conversation.Content],
) -> list[mistral_models.ChatCompletionRequestMessage]:
    """Convert Home Assistant conversation content to Mistral messages."""
    messages: list[mistral_models.ChatCompletionRequestMessage] = []

    for content in chat_content:
        if isinstance(content, conversation.SystemContent):
            messages.append(mistral_models.SystemMessage(content=content.content))
            continue

        if isinstance(content, conversation.UserContent):
            messages.append(mistral_models.UserMessage(content=content.content))
            continue

        if isinstance(content, conversation.AssistantContent):
            assistant_message = mistral_models.AssistantMessage()
            add_msg = False
            if content.content:
                assistant_message.content = content.content
                add_msg = True
            if content.tool_calls:
                assistant_message.tool_calls = [
                    mistral_models.ToolCall(
                        id=tool_call.id,
                        type="function",
                        function=mistral_models.FunctionCall(
                            name=tool_call.tool_name,
                            arguments=tool_call.tool_args,
                        ),
                    )
                    for tool_call in content.tool_calls
                ]
                add_msg = True
            if add_msg:
                messages.append(assistant_message)
            continue

        if isinstance(content, conversation.ToolResultContent):
            messages.append(
                mistral_models.ToolMessage(
                    tool_call_id=content.tool_call_id,
                    name=content.tool_name,
                    content=json_dumps(content.tool_result),
                )
            )
            continue

        raise HomeAssistantError(
            f"Unsupported chat log content for Mistral: {type(content).__name__}"
        )

    return messages


def _format_tool(
    tool: llm.Tool,
    custom_serializer: Callable[[Any], Any] | None,
) -> mistral_models.ChatCompletionStreamRequestTool:
    """Convert a Home Assistant tool specification into a Mistral function tool."""
    function_definition = mistral_models.Function(
        name=tool.name,
        parameters=convert(tool.parameters, custom_serializer=custom_serializer),
    )
    if tool.description:
        function_definition.description = tool.description
    return mistral_models.Tool(type="function", function=function_definition)


def _decode_base64_audio(audio_data: str) -> bytes:
    """Decode the provider's base64-encoded audio payload."""
    return base64.b64decode(audio_data)


@dataclass(slots=True)
class _PendingToolCall:
    """Accumulate partial streamed tool call data until it is complete."""

    index: int
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments_buffer: str = ""
    arguments_object: dict[str, Any] | None = None

    def update(self, tool_call: mistral_models.ToolCall) -> None:
        """Merge a streamed tool call delta into the current accumulator."""
        if tool_call.id and tool_call.id != "null":
            self.tool_call_id = tool_call.id
        if tool_call.function.name:
            self.tool_name = tool_call.function.name

        arguments = tool_call.function.arguments
        if isinstance(arguments, dict):
            if self.arguments_object is None:
                self.arguments_object = {}
            self.arguments_object.update(arguments)
        elif isinstance(arguments, str):
            self.arguments_buffer += arguments

    def to_tool_input(self) -> llm.ToolInput:
        """Return a Home Assistant tool input object."""
        if self.arguments_object is not None:
            tool_args = self.arguments_object
        else:
            try:
                tool_args = _normalize_tool_arguments(self.arguments_buffer)
            except json.JSONDecodeError as err:
                raise HomeAssistantError(
                    f"Unable to parse tool call arguments for {self.tool_name or 'tool'}"
                ) from err

        return llm.ToolInput(
            tool_name=self.tool_name or "tool",
            tool_args=tool_args,
            id=self.tool_call_id or ulid_now(),
        )


def _finalize_pending_tool_calls(
    pending_tool_calls: dict[int, _PendingToolCall],
) -> list[llm.ToolInput]:
    """Convert accumulated tool calls into Home Assistant tool inputs."""
    return [
        pending_tool_calls[index].to_tool_input()
        for index in sorted(pending_tool_calls)
    ]


async def _transform_stream(
    chat_log: conversation.ChatLog,
    stream: eventstreaming.EventStreamAsync[mistral_models.CompletionEvent],
) -> AsyncGenerator[
    conversation.AssistantContentDeltaDict | conversation.ToolResultContentDeltaDict
]:
    """Transform a Mistral chat stream into Home Assistant deltas."""
    assistant_message_started = False
    pending_tool_calls: dict[int, _PendingToolCall] = {}

    async for event in stream:
        chunk = event.data
        if chunk.usage is not None:
            chat_log.async_trace(
                {
                    "stats": {
                        "input_tokens": chunk.usage.prompt_tokens,
                        "output_tokens": chunk.usage.completion_tokens,
                    }
                }
            )

        for choice in chunk.choices:
            delta = choice.delta
            text_delta, thinking_delta = _extract_delta_text_and_thinking(delta.content)

            should_start_message = not assistant_message_started and (
                (_is_value_set(delta.role) and delta.role == "assistant")
                or text_delta
                or thinking_delta
                or _is_value_set(delta.tool_calls)
            )

            pending_payload: conversation.AssistantContentDeltaDict | None = None
            if should_start_message:
                assistant_message_started = True
                pending_payload = conversation.AssistantContentDeltaDict(
                    role="assistant"
                )

            if text_delta or thinking_delta:
                payload = pending_payload or {}
                if text_delta:
                    payload["content"] = text_delta
                if thinking_delta:
                    payload["thinking_content"] = thinking_delta
                yield payload
                pending_payload = None
            elif pending_payload is not None:
                yield pending_payload

            if _is_value_set(delta.tool_calls):
                for tool_call in delta.tool_calls:
                    tool_call_index = tool_call.index or 0
                    pending_tool_calls.setdefault(
                        tool_call_index, _PendingToolCall(index=tool_call_index)
                    ).update(tool_call)

            if choice.finish_reason == "tool_calls" and pending_tool_calls:
                yield {"tool_calls": _finalize_pending_tool_calls(pending_tool_calls)}
                pending_tool_calls.clear()
            elif choice.finish_reason == "error":
                raise HomeAssistantError("Mistral returned an error while streaming")

    if pending_tool_calls:
        yield {"tool_calls": _finalize_pending_tool_calls(pending_tool_calls)}


class MistralAIBaseEntity(CoordinatorEntity[MistralCoordinator]):
    """Shared base entity for all Mistral AI platforms."""

    _attr_has_entity_name = False

    def __init__(self, entry: MistralAIConfigEntry, subentry: ConfigSubentry) -> None:
        """Initialize the shared entity state."""
        super().__init__(entry.runtime_data)
        self.entry = entry
        self.subentry = subentry
        self._attr_name = subentry.title
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="Mistral AI",
            model=self._get_selected_model_id(),
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    def _get_selected_model_id(self) -> str:
        """Return the active model ID for the current subentry."""
        if self.subentry.subentry_type == "conversation":
            return self.subentry.data.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL)
        if self.subentry.subentry_type == "stt":
            return self.subentry.data.get(CONF_STT_MODEL, RECOMMENDED_STT_MODEL)
        return self.subentry.data.get(CONF_TTS_MODEL, RECOMMENDED_TTS_MODEL)

    def _raise_runtime_error(self, err: Exception) -> None:
        """Normalize runtime provider errors into Home Assistant errors."""
        if isinstance(err, mistral_errors.MistralError) and err.status_code in (
            401,
            403,
        ):
            self.entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Authentication with Mistral failed") from err
        raise HomeAssistantError(str(err)) from err

    async def _async_handle_chat_log(
        self,
        chat_log: conversation.ChatLog,
        max_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> None:
        """Generate a response for a Home Assistant chat log."""
        options = self.subentry.data
        tools = []
        if chat_log.llm_api:
            tools = [
                _format_tool(tool, chat_log.llm_api.custom_serializer)
                for tool in chat_log.llm_api.tools
            ]

        try:
            for _iteration in range(max_iterations):
                request_arguments: dict[str, Any] = {
                    "model": options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL),
                    "messages": _convert_content_to_mistral_messages(chat_log.content),
                    "stream": True,
                    "max_tokens": options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS),
                    "temperature": options.get(
                        CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE
                    ),
                    "top_p": options.get(CONF_TOP_P, RECOMMENDED_TOP_P),
                }
                if tools:
                    request_arguments["tools"] = tools
                    request_arguments["parallel_tool_calls"] = True

                response_stream = await self.coordinator.client.chat.stream_async(
                    **request_arguments
                )
                async with response_stream:
                    async for _content in chat_log.async_add_delta_content_stream(
                        self.entity_id,
                        _transform_stream(chat_log, response_stream),
                    ):
                        pass

                if not chat_log.unresponded_tool_results:
                    return
        except (
            mistral_errors.MistralError,
            mistral_errors.NoResponseError,
            ValueError,
        ) as err:
            self._raise_runtime_error(err)

        raise HomeAssistantError("Mistral reached the maximum tool-call iterations")
