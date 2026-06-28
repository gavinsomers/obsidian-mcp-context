from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from typing import Protocol
from urllib import error, request

from obsidian_mcp_context.config import AppConfig


DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


class ContextOverflowError(ValueError):
    """Raised when a prompt exceeds the configured context budget."""


class AIProviderError(RuntimeError):
    """Raised when an AI provider cannot return valid structured JSON."""


@dataclass(frozen=True)
class AICompletionResult:
    data: dict[str, object]
    provider: str
    model: str
    prompt_version: str
    input_hash: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "data": self.data,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "input_hash": self.input_hash,
            "created_at": self.created_at,
        }


class AIProvider(Protocol):
    provider: str
    model: str

    def complete_json(
        self,
        prompt: str,
        schema: dict[str, object],
        *,
        max_context_chars: int,
        prompt_version: str,
    ) -> AICompletionResult:
        ...


def validate_context_budget(prompt: str, max_context_chars: int) -> None:
    if max_context_chars <= 0:
        raise ValueError("max_context_chars must be greater than zero")
    actual_chars = len(prompt)
    if actual_chars > max_context_chars:
        raise ContextOverflowError(
            f"Prompt is {actual_chars} chars; max_context_chars is {max_context_chars}"
        )


def _metadata(
    *,
    data: dict[str, object],
    provider: str,
    model: str,
    prompt: str,
    prompt_version: str,
) -> AICompletionResult:
    return AICompletionResult(
        data=data,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        input_hash=sha256(prompt.encode("utf-8")).hexdigest(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _validate_schema_contract(
    data: dict[str, object],
    schema: dict[str, object],
) -> None:
    schema_type = schema.get("type")
    if schema_type is not None and schema_type != "object":
        raise AIProviderError("Only object JSON schemas are supported")
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(
        isinstance(item, str) for item in required
    ):
        raise AIProviderError("schema.required must be a list of strings")
    missing = [key for key in required if key not in data]
    if missing:
        joined = ", ".join(missing)
        raise AIProviderError(f"AI response is missing required keys: {joined}")


def _parse_json_object(raw: str, schema: dict[str, object]) -> dict[str, object]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIProviderError(f"AI response was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AIProviderError("AI response must be a JSON object")
    _validate_schema_contract(parsed, schema)
    return parsed


class NoneProvider:
    provider = "none"
    model = ""

    def complete_json(
        self,
        prompt: str,
        schema: dict[str, object],
        *,
        max_context_chars: int,
        prompt_version: str,
    ) -> AICompletionResult:
        raise AIProviderError("AI is disabled")


class MockProvider:
    provider = "mock"

    def __init__(self, response: dict[str, object] | str | None = None) -> None:
        self.model = "mock"
        self._response = response if response is not None else {}
        self.calls = 0

    def complete_json(
        self,
        prompt: str,
        schema: dict[str, object],
        *,
        max_context_chars: int,
        prompt_version: str,
    ) -> AICompletionResult:
        validate_context_budget(prompt, max_context_chars)
        self.calls += 1
        if isinstance(self._response, str):
            data = _parse_json_object(self._response, schema)
        else:
            data = dict(self._response)
            _validate_schema_contract(data, schema)
        return _metadata(
            data=data,
            provider=self.provider,
            model=self.model,
            prompt=prompt,
            prompt_version=prompt_version,
        )


class OllamaProvider:
    provider = "ollama"

    def __init__(self, *, model: str, base_url: str = DEFAULT_OLLAMA_BASE_URL) -> None:
        if not model:
            raise AIProviderError("ollama provider requires ai.model")
        self.model = model
        self.base_url = base_url.rstrip("/") or DEFAULT_OLLAMA_BASE_URL

    def complete_json(
        self,
        prompt: str,
        schema: dict[str, object],
        *,
        max_context_chars: int,
        prompt_version: str,
    ) -> AICompletionResult:
        validate_context_budget(prompt, max_context_chars)
        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }
        ).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, error.URLError, json.JSONDecodeError) as exc:
            raise AIProviderError(f"ollama request failed: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
            raise AIProviderError("ollama response did not include a JSON response string")
        data = _parse_json_object(payload["response"], schema)
        return _metadata(
            data=data,
            provider=self.provider,
            model=self.model,
            prompt=prompt,
            prompt_version=prompt_version,
        )


class HostedProviderStub:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key_env: str,
        allow_hosted_ai: bool,
    ) -> None:
        if not allow_hosted_ai:
            raise AIProviderError(
                "privacy.allow_hosted_ai must be true to configure hosted AI"
            )
        if not model:
            raise AIProviderError(f"{provider} provider requires ai.model")
        if not api_key_env:
            raise AIProviderError(f"{provider} provider requires ai.api_key_env")
        if "=" in api_key_env:
            raise AIProviderError("ai.api_key_env must be an env-var name, not a key")
        if not os.environ.get(api_key_env):
            raise AIProviderError(f"Environment variable is not set: {api_key_env}")
        self.provider = provider
        self.model = model
        self.api_key_env = api_key_env

    def complete_json(
        self,
        prompt: str,
        schema: dict[str, object],
        *,
        max_context_chars: int,
        prompt_version: str,
    ) -> AICompletionResult:
        validate_context_budget(prompt, max_context_chars)
        raise AIProviderError(
            f"{self.provider} completion is not implemented in Phase 4"
        )


def build_ai_provider(config: AppConfig) -> AIProvider:
    if not config.ai.enabled or config.ai.provider == "none":
        return NoneProvider()
    if config.ai.provider == "mock":
        return MockProvider()
    if config.ai.provider == "ollama":
        return OllamaProvider(
            model=config.ai.model,
            base_url=config.ai.base_url or DEFAULT_OLLAMA_BASE_URL,
        )
    if config.ai.provider in {"openai", "anthropic"}:
        return HostedProviderStub(
            provider=config.ai.provider,
            model=config.ai.model,
            api_key_env=config.ai.api_key_env,
            allow_hosted_ai=config.privacy.allow_hosted_ai,
        )
    raise AIProviderError(f"Unsupported AI provider: {config.ai.provider}")
