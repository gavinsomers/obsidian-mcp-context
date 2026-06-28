from __future__ import annotations

from obsidian_mcp_context.ai import (
    AIProviderError,
    ContextOverflowError,
    MockProvider,
    NoneProvider,
    OllamaProvider,
    build_ai_provider,
    validate_context_budget,
)
from obsidian_mcp_context.config import (
    AIConfig,
    AppConfig,
    PrivacyConfig,
    load_app_config,
)


def test_disabled_ai_builds_none_provider():
    provider = build_ai_provider(AppConfig())

    assert isinstance(provider, NoneProvider)


def test_none_provider_raises_when_called():
    provider = NoneProvider()

    try:
        provider.complete_json(
            "prompt",
            {"type": "object"},
            max_context_chars=100,
            prompt_version="test",
        )
    except AIProviderError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("Expected disabled AI provider to fail")


def test_mock_provider_returns_json_with_metadata():
    provider = MockProvider({"answer": "yes"})

    result = provider.complete_json(
        "short prompt",
        {"type": "object", "required": ["answer"]},
        max_context_chars=100,
        prompt_version="unit-test-v1",
    )

    assert result.data == {"answer": "yes"}
    assert result.provider == "mock"
    assert result.model == "mock"
    assert result.prompt_version == "unit-test-v1"
    assert len(result.input_hash) == 64
    assert result.created_at.endswith("+00:00")
    assert provider.calls == 1


def test_context_overflow_raises_before_provider_execution():
    provider = MockProvider({"answer": "yes"})

    try:
        provider.complete_json(
            "too long",
            {"type": "object"},
            max_context_chars=3,
            prompt_version="unit-test-v1",
        )
    except ContextOverflowError as exc:
        assert "Prompt is 8 chars" in str(exc)
    else:
        raise AssertionError("Expected context overflow")

    assert provider.calls == 0


def test_validate_context_budget_rejects_non_positive_budget():
    try:
        validate_context_budget("prompt", 0)
    except ValueError as exc:
        assert "greater than zero" in str(exc)
    else:
        raise AssertionError("Expected invalid budget to fail")


def test_mock_provider_rejects_malformed_json():
    provider = MockProvider("{not-json")

    try:
        provider.complete_json(
            "prompt",
            {"type": "object"},
            max_context_chars=100,
            prompt_version="unit-test-v1",
        )
    except AIProviderError as exc:
        assert "not valid JSON" in str(exc)
    else:
        raise AssertionError("Expected malformed JSON to fail")


def test_mock_provider_enforces_required_schema_keys():
    provider = MockProvider({"answer": "yes"})

    try:
        provider.complete_json(
            "prompt",
            {"type": "object", "required": ["missing"]},
            max_context_chars=100,
            prompt_version="unit-test-v1",
        )
    except AIProviderError as exc:
        assert "missing required keys: missing" in str(exc)
    else:
        raise AssertionError("Expected required schema key validation")


def test_config_accepts_mock_provider(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[ai]
enabled = true
provider = "mock"
""".strip(),
        encoding="utf-8",
    )

    config = load_app_config(config_path)

    assert config.ai.enabled is True
    assert config.ai.provider == "mock"
    assert isinstance(build_ai_provider(config), MockProvider)


def test_ollama_provider_defaults_base_url_for_local_qwen():
    provider = build_ai_provider(
        AppConfig(
            ai=AIConfig(
                enabled=True,
                provider="ollama",
                model="qwen2.5:7b",
            )
        )
    )

    assert isinstance(provider, OllamaProvider)
    assert provider.model == "qwen2.5:7b"
    assert provider.base_url == "http://localhost:11434"


def test_ollama_provider_requires_model():
    try:
        build_ai_provider(AppConfig(ai=AIConfig(enabled=True, provider="ollama")))
    except AIProviderError as exc:
        assert "requires ai.model" in str(exc)
    else:
        raise AssertionError("Expected missing model to fail")


def test_hosted_provider_requires_api_key_env_value(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = AppConfig(
        privacy=PrivacyConfig(allow_hosted_ai=True),
        ai=AIConfig(
            enabled=True,
            provider="openai",
            model="gpt-test",
            api_key_env="OPENAI_API_KEY",
        ),
    )

    try:
        build_ai_provider(config)
    except AIProviderError as exc:
        assert "Environment variable is not set: OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing hosted API key env value to fail")


def test_hosted_provider_can_be_constructed_when_env_is_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    config = AppConfig(
        privacy=PrivacyConfig(allow_hosted_ai=True),
        ai=AIConfig(
            enabled=True,
            provider="anthropic",
            model="claude-test",
            api_key_env="ANTHROPIC_API_KEY",
        ),
    )

    provider = build_ai_provider(config)

    assert provider.provider == "anthropic"
    assert provider.model == "claude-test"
