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
