from pathlib import Path

from obsidian_mcp_context.config import load_app_config, vault_config_from_app_config
from obsidian_mcp_context.doctor import DoctorCode, DoctorOptions, run_doctor
from obsidian_mcp_context.vault import build_context
from obsidian_mcp_context.warehouse import build_warehouse, list_entities


def test_config_applies_scan_excludes_and_folder_entity_overrides(tmp_path: Path):
    vault = tmp_path / "vault"
    config_path = tmp_path / "config.toml"
    (vault / "Clients").mkdir(parents=True)
    (vault / "Calendars").mkdir()
    (vault / "Imports").mkdir()
    (vault / "Clients" / "Acme.md").write_text(
        "# Acme\n\nLinked from [[2026 Calendar]].\n",
        encoding="utf-8",
    )
    (vault / "Calendars" / "2026 Calendar.md").write_text(
        "# 2026 Calendar\n\nCalendar OCR notes.\n",
        encoding="utf-8",
    )
    (vault / "Imports" / "Raw.md").write_text("# Raw\n", encoding="utf-8")
    config_path.write_text(
        """
[scan]
extra_exclude_globs = ["Imports/**"]

[entities]
non_entity_note_types = ["daily", "meeting", "note", "research", "calendar"]

[entities.folders]
Clients = "company"
Calendars = "calendar"
""".strip(),
        encoding="utf-8",
    )

    app_config = load_app_config(config_path)
    context = build_context(vault_config_from_app_config(vault, app_config))
    warehouse = build_warehouse(context)
    try:
        entities = list_entities(warehouse, limit=20)
    finally:
        warehouse.close()

    assert {file.source_path for file in context.files} == {
        "Calendars/2026 Calendar.md",
        "Clients/Acme.md",
    }
    assert {
        (file.source_path, file.note_type) for file in context.files
    } == {
        ("Calendars/2026 Calendar.md", "calendar"),
        ("Clients/Acme.md", "company"),
    }
    assert {(entity["entity_type"], entity["name"]) for entity in entities} == {
        ("company", "Acme")
    }


def test_doctor_reports_loaded_config_without_content_samples(tmp_path: Path):
    vault = tmp_path / "vault"
    config_path = tmp_path / "config.toml"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n", encoding="utf-8")
    config_path.write_text(
        """
[scan]
extra_exclude_globs = ["Private/**"]

[entities.folders]
Clients = "company"
""".strip(),
        encoding="utf-8",
    )

    report = run_doctor(DoctorOptions(vault_path=vault, config_path=config_path))

    assert report["config"]["loaded"] is True
    assert report["config"]["path"] == str(config_path)
    assert "Private/**" in report["config"]["exclude_globs"]
    assert report["config"]["folder_note_type_count"] == 1
    assert report["privacy"]["samples_redacted"] is True
    assert all("sample" not in item["details"] for item in report["diagnostics"])


def test_doctor_can_ignore_lifecycle_metadata_warnings_from_config(tmp_path: Path):
    vault = tmp_path / "vault"
    config_path = tmp_path / "config.toml"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n", encoding="utf-8")
    config_path.write_text(
        """
[doctor]
lifecycle_metadata = "ignore"
""".strip(),
        encoding="utf-8",
    )

    report = run_doctor(DoctorOptions(vault_path=vault, config_path=config_path))

    assert report["status"] == "ok"
    assert report["config"]["doctor"]["lifecycle_metadata"] == "ignore"
    assert report["content"]["missing_lifecycle_field_count"] == 1
    assert all(
        item["code"] != DoctorCode.MISSING_LIFECYCLE_METADATA.value
        for item in report["diagnostics"]
    )


def test_doctor_can_error_on_lifecycle_metadata_from_config(tmp_path: Path):
    vault = tmp_path / "vault"
    config_path = tmp_path / "config.toml"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n", encoding="utf-8")
    config_path.write_text(
        """
[doctor]
lifecycle_metadata = "error"
""".strip(),
        encoding="utf-8",
    )

    report = run_doctor(DoctorOptions(vault_path=vault, config_path=config_path))

    assert report["status"] == "error"
    assert report["config"]["doctor"]["lifecycle_metadata"] == "error"
    assert any(
        item["code"] == DoctorCode.MISSING_LIFECYCLE_METADATA.value
        and item["severity"] == "error"
        for item in report["diagnostics"]
    )


def test_config_rejects_invalid_doctor_lifecycle_metadata_mode(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[doctor]
lifecycle_metadata = "required"
""".strip(),
        encoding="utf-8",
    )

    try:
        load_app_config(config_path)
    except ValueError as exc:
        assert "doctor.lifecycle_metadata" in str(exc)
    else:
        raise AssertionError("Expected invalid lifecycle metadata mode to fail")


def test_doctor_can_ignore_selected_warning_categories_from_config(tmp_path: Path):
    vault = tmp_path / "vault"
    config_path = tmp_path / "config.toml"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n\n[[Missing]]\n", encoding="utf-8")
    (vault / "Empty.md").write_text("", encoding="utf-8")
    (vault / "image.png").write_bytes(b"ignored")
    config_path.write_text(
        """
[doctor]
lifecycle_metadata = "ignore"
unsupported_files = "ignore"
empty_notes = "ignore"
unresolved_wikilinks = "ignore"
""".strip(),
        encoding="utf-8",
    )

    report = run_doctor(DoctorOptions(vault_path=vault, config_path=config_path))

    assert report["status"] == "ok"
    assert report["config"]["doctor"]["unsupported_files"] == "ignore"
    assert report["config"]["doctor"]["empty_notes"] == "ignore"
    assert report["config"]["doctor"]["unresolved_wikilinks"] == "ignore"
    assert report["content"]["unsupported_file_count"] == 1
    assert report["content"]["empty_note_count"] == 1
    assert report["graph"]["unresolved_wikilinks"] == 1
    assert {
        DoctorCode.UNSUPPORTED_FILE.value,
        DoctorCode.EMPTY_NOTE.value,
        DoctorCode.UNRESOLVED_WIKILINK.value,
    }.isdisjoint({item["code"] for item in report["diagnostics"]})


def test_doctor_can_error_on_unresolved_wikilinks_from_config(tmp_path: Path):
    vault = tmp_path / "vault"
    config_path = tmp_path / "config.toml"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n\n[[Missing]]\n", encoding="utf-8")
    config_path.write_text(
        """
[doctor]
lifecycle_metadata = "ignore"
unresolved_wikilinks = "error"
""".strip(),
        encoding="utf-8",
    )

    report = run_doctor(DoctorOptions(vault_path=vault, config_path=config_path))

    assert report["status"] == "error"
    assert any(
        item["code"] == DoctorCode.UNRESOLVED_WIKILINK.value
        and item["severity"] == "error"
        for item in report["diagnostics"]
    )


def test_config_accepts_unresolved_wikilink_table(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[doctor.unresolved_wikilinks]
mode = "error"
ignore_target_globs = ["Archive/*", "Template:*"]
""".strip(),
        encoding="utf-8",
    )

    config = load_app_config(config_path)

    assert config.doctor_unresolved_wikilinks == "error"
    assert config.doctor_unresolved_wikilink_ignore_target_globs == (
        "Archive/*",
        "Template:*",
    )


def test_config_rejects_invalid_doctor_warning_mode(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[doctor]
unsupported_files = "skip"
""".strip(),
        encoding="utf-8",
    )

    try:
        load_app_config(config_path)
    except ValueError as exc:
        assert "doctor.unsupported_files" in str(exc)
    else:
        raise AssertionError("Expected invalid doctor warning mode to fail")


def test_config_rejects_invalid_unresolved_wikilink_ignore_globs(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[doctor.unresolved_wikilinks]
ignore_target_globs = "Archive/*"
""".strip(),
        encoding="utf-8",
    )

    try:
        load_app_config(config_path)
    except ValueError as exc:
        assert "doctor.unresolved_wikilinks.ignore_target_globs" in str(exc)
    else:
        raise AssertionError("Expected invalid unresolved target globs to fail")


def test_pipeline_config_defaults_to_sample_profile(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")

    config = load_app_config(config_path)

    assert config.source.type == "sample"
    assert config.source.sample_name == "synthetic-vault"
    assert config.pipeline.output_dir == "var"
    assert config.privacy.allow_raw_text_to_ai is False
    assert config.privacy.allow_hosted_ai is False
    assert config.ai.enabled is False
    assert config.ai.provider == "none"


def test_pipeline_config_accepts_local_obsidian_source(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[source]
type = "obsidian"
vault_path = "{vault}"

[pipeline]
output_dir = "var/local"
run_mode = "local"
""".strip(),
        encoding="utf-8",
    )

    config = load_app_config(config_path)

    assert config.source.type == "obsidian"
    assert config.source.vault_path == str(vault)
    assert config.pipeline.output_dir == "var/local"
    assert config.pipeline.run_mode == "local"


def test_pipeline_config_accepts_local_ai_without_hosted_privacy(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[ai]
enabled = true
provider = "ollama"
model = "qwen2.5:7b"
base_url = "http://localhost:11434"
""".strip(),
        encoding="utf-8",
    )

    config = load_app_config(config_path)

    assert config.ai.enabled is True
    assert config.ai.provider == "ollama"
    assert config.ai.model == "qwen2.5:7b"
    assert config.privacy.allow_hosted_ai is False


def test_pipeline_config_blocks_hosted_ai_unless_privacy_allows_it(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[ai]
enabled = true
provider = "openai"
model = "gpt-4.1-mini"
api_key_env = "OPENAI_API_KEY"
""".strip(),
        encoding="utf-8",
    )

    try:
        load_app_config(config_path)
    except ValueError as exc:
        assert "privacy.allow_hosted_ai" in str(exc)
    else:
        raise AssertionError("Expected hosted AI to require explicit privacy opt-in")


def test_pipeline_config_accepts_hosted_ai_when_privacy_allows_it(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[privacy]
allow_hosted_ai = true

[ai]
enabled = true
provider = "anthropic"
model = "claude-sonnet-4"
api_key_env = "ANTHROPIC_API_KEY"
""".strip(),
        encoding="utf-8",
    )

    config = load_app_config(config_path)

    assert config.privacy.allow_hosted_ai is True
    assert config.ai.enabled is True
    assert config.ai.provider == "anthropic"
    assert config.ai.api_key_env == "ANTHROPIC_API_KEY"


def test_pipeline_config_environment_overrides_ai_settings(
    tmp_path: Path, monkeypatch
):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[ai]
enabled = false
provider = "none"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("OBSIDIAN_MCP_AI_ENABLED", "true")
    monkeypatch.setenv("OBSIDIAN_MCP_AI_PROVIDER", "ollama")
    monkeypatch.setenv("OBSIDIAN_MCP_AI_MODEL", "qwen3:8b")
    monkeypatch.setenv("OBSIDIAN_MCP_AI_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OBSIDIAN_MCP_AI_API_KEY_ENV", "IGNORED_FOR_LOCAL")

    config = load_app_config(config_path)

    assert config.ai.enabled is True
    assert config.ai.provider == "ollama"
    assert config.ai.model == "qwen3:8b"
    assert config.ai.base_url == "http://localhost:11434"
    assert config.ai.api_key_env == "IGNORED_FOR_LOCAL"


def test_example_pipeline_configs_are_valid():
    for config_path in Path("examples/config").glob("*.toml"):
        config = load_app_config(config_path)
        assert config.loaded is True


def test_local_gemma_enrichment_profile_uses_local_ollama_only():
    config = load_app_config("examples/config/local-gemma-enrichment.toml")

    assert config.ai.enabled is True
    assert config.ai.provider == "ollama"
    assert config.ai.model == "gemma4:26b-a4b-it-q4_K_M"
    assert config.ai.base_url == "http://localhost:11434"
    assert config.privacy.allow_raw_text_to_ai is True
    assert config.privacy.allow_hosted_ai is False
    assert config.privacy.max_context_chars == 6000
