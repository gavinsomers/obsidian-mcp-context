from pathlib import Path

from obsidian_mcp_context.config import load_app_config, vault_config_from_app_config
from obsidian_mcp_context.doctor import DoctorOptions, run_doctor
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
