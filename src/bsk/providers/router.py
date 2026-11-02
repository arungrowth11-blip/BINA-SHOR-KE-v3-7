from __future__ import annotations

import time
from typing import Any

from bsk.config import Settings, settings
from bsk.errors import ConfigurationError, ProviderError
from bsk.providers.gemini import GeminiTextProvider
from bsk.providers.openai_compatible import OpenAICompatibleProvider


class ProviderRouter:
    """Sequential free-key routing; never fans out and never silently selects a paid service."""

    def __init__(self, config: Settings = settings, providers: dict[str, Any] | None = None):
        self.config = config
        if providers is not None:
            self.providers = providers
        else:
            self.providers: dict[str, Any] = {}
            if config.gemini_api_key:
                self.providers["gemini"] = GeminiTextProvider(
                    config.gemini_api_key, config.gemini_text_model, config.request_timeout_seconds
                )
            if config.groq_api_key:
                self.providers["groq"] = OpenAICompatibleProvider(
                    "groq", config.groq_api_key, config.groq_text_model,
                    "https://api.groq.com/openai/v1", config.request_timeout_seconds,
                )
            if config.mistral_api_key and config.enable_mistral_free_only:
                self.providers["mistral"] = OpenAICompatibleProvider(
                    "mistral", config.mistral_api_key, config.mistral_text_model,
                    "https://api.mistral.ai/v1", config.request_timeout_seconds,
                )

    def names(self) -> list[str]:
        preferred = [self.config.writer_provider, "gemini", "groq", "mistral"]
        return list(dict.fromkeys(name for name in preferred if name in self.providers))

    def generate_with(self, provider_name: str, system: str, prompt: str, temperature: float = 0.4) -> dict[str, Any]:
        if provider_name not in self.providers:
            raise ConfigurationError(f"Provider '{provider_name}' is not configured.")
        return self.providers[provider_name].generate_json(system, prompt, temperature)

    def generate_json(
        self, system: str, prompt: str, temperature: float = 0.4, exclude: set[str] | None = None
    ) -> tuple[str, dict[str, Any]]:
        if not self.config.confirm_free_only:
            raise ConfigurationError(
                "Free-only usage has not been confirmed. Check provider account tiers/billing first, "
                "then set BSK_CONFIRM_FREE_ONLY=YES in your local .env."
            )
        excluded = exclude or set()
        attempts: list[str] = []
        for name in self.names():
            if name in excluded:
                continue
            provider = self.providers[name]
            for attempt in range(max(1, self.config.max_provider_attempts)):
                try:
                    result = provider.generate_json(system, prompt, temperature)
                    return name, result
                except Exception as exc:  # bounded, sequential failover only
                    attempts.append(f"{name} attempt {attempt + 1}: {str(exc)[:250]}")
                    message = str(exc).lower()
                    non_retryable = any(x in message for x in ("http 400", "http 401", "http 403", "http 404"))
                    if non_retryable or attempt + 1 >= max(1, self.config.max_provider_attempts):
                        break
                    time.sleep(min(2 ** attempt, 4))
        detail = " | ".join(attempts) if attempts else "No configured provider remains after exclusions."
        raise ProviderError("All eligible configured providers failed. No paid fallback was attempted. " + detail)

    def require_independent_critic(self, writer_name: str | None = None) -> None:
        eligible = [name for name in self.names() if name != writer_name]
        if not eligible:
            raise ConfigurationError(
                "Independent editorial review requires at least two configured text providers. "
                "Keep Gemini as writer and configure GROQ_API_KEY or MISTRAL_API_KEY for the critic."
            )
