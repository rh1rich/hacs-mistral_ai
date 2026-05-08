[![hacs_badge](https://img.shields.io/badge/My_HACS-Mistral_AI-41BDF5?logo=homeassistant&logoColor=white)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rh1rich&repository=hacs-mistral_ai&category=integration)
[![Validate workflow](https://img.shields.io/github/actions/workflow/status/rh1rich/hacs-mistral_ai/validate.yml?label=Validate&logo=github)](https://github.com/rh1rich/hacs-mistral_ai/actions/workflows/validate.yml)
![GitHub all releases](https://img.shields.io/github/downloads/rh1rich/hacs-mistral_ai/total?color=d9810f&label=Downloads&logo=GitHub)

<!-- [![Lint workflow](https://img.shields.io/github/actions/workflow/status/rh1rich/hacs-mistral_ai/lint.yml?label=Lint&logo=github)](https://github.com/rh1rich/hacs-mistral_ai/actions/workflows/lint.yml) -->

<p align="center">
	<img src="https://raw.githubusercontent.com/rh1rich/hacs-mistral_ai/main/custom_components/mistral_ai/brand/logo.png#gh-light-mode-only" alt="Mistral AI logo" width="420">
	<img src="https://raw.githubusercontent.com/rh1rich/hacs-mistral_ai/main/custom_components/mistral_ai/brand/dark_logo.png#gh-dark-mode-only" alt="Mistral AI logo" width="420">
</p>

<h3 align="center">Mistral AI Custom Integration for Home Assistant</h3>

# What This Is

This custom integration brings [Mistral AI](https://mistral.ai/) to Home Assistant with native support for:

- Conversation
- Text-to-speech
- Speech-to-text

It is inspired by Home Assistant's built-in [OpenAI Conversation](https://www.home-assistant.io/integrations/openai_conversation/) and [Anthropic](https://www.home-assistant.io/integrations/anthropic/) integrations, while exposing Mistral models through the same Home Assistant-first configuration flow and Assist ecosystem.

# What It Does

After setup, the integration creates dedicated subentries for all three Mistral AI capabilities:

- A streaming conversation agent that can be used with Assist and Home Assistant LLM tools
- A text-to-speech entity backed by Mistral voices and multiple output formats
- A speech-to-text entity for Assist pipelines and voice workflows

The goal is to make Mistral AI feel like a natural Home Assistant provider rather than a separate sidecar service.

# Requirements

A valid Mistral API key and access to the models you want to use.

Recommended defaults used by the integration:

- Conversation: `mistral-small-latest`
- Speech-to-text: `voxtral-mini-latest`
- Text-to-speech: `voxtral-mini-tts-latest`

Available models and voices depend on your Mistral account.

# Installation And Configuration

## Install Through HACS

1. Open HACS in Home Assistant.
2. Add this repository, or use the direct link: [Mistral AI in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=rh1rich&repository=hacs-mistral_ai&category=integration).
3. Download the integration.
4. Restart Home Assistant.

## Set Up The Integration

1. Go to Settings -> Devices & Services.
2. Add the integration, or use the direct link: [Add Mistral AI](https://my.home-assistant.io/redirect/config_flow_start/?domain=mistral_ai).
3. Enter your Mistral API key.
4. Finish the config flow.

By default, the integration creates:

- One conversation subentry
- One speech-to-text subentry
- One text-to-speech subentry

You can reconfigure each subentry later from the integration page.

# Options

## Conversation

Conversation subentries support:

- Prompt instructions using Home Assistant templates
- Optional access to Home Assistant Assist tools through `llm_hass_api`
- Model selection
- Max tokens
- Temperature
- Top P

## Speech-To-Text

Speech-to-text subentries support:

- Model selection
- WAV and OGG input formats
- Mono and stereo input
- Multiple sample rates supported by Home Assistant STT entities

## Text-To-Speech

Text-to-speech subentries support:

- Model selection
- Voice selection
- Default language selection
- Streaming and non-streaming playback
- `mp3`, `opus`, `wav`, `flac`, and `pcm` output formats

# Notes And Limitations

- This is a cloud integration and requires internet access.
- Authentication and catalog discovery are performed against the Mistral API.
- Voice availability and supported languages come from the provider's current voice catalog.
- Runtime dependency compatibility is pinned in the integration manifest and mirrored in `requirements.txt` for development.

# Changelog

See the [release history](https://github.com/rh1rich/hacs-mistral_ai/releases).

# Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md) for development guidance.

# License

[MIT](LICENSE)

