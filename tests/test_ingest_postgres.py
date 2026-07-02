from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_mcp_context.ingest_postgres import (
    _validate_schema,
    build_ingest_payload,
    build_parser,
)


def test_postgres_schema_validation_accepts_identifier_names():
    assert _validate_schema("raw") == "raw"
    assert _validate_schema("raw_obsidian_1") == "raw_obsidian_1"


def test_postgres_schema_validation_rejects_sql_fragments():
    with pytest.raises(ValueError):
        _validate_schema("raw; drop schema marts")


def test_postgres_ingest_parser_uses_env_connection(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@postgres/db")

    parser = build_parser()
    args = parser.parse_args(["--vault", "/vault"])

    assert args.connection == "postgresql://user:pass@postgres/db"
    assert args.schema == "raw"


def test_postgres_ingest_parser_accepts_vault_profile(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@postgres/db")

    parser = build_parser()
    args = parser.parse_args(
        ["--vault", "/vault", "--vault-profile", "generated-demo"]
    )

    assert args.vault_profile == "generated-demo"


def test_ingest_payload_uses_generated_demo_profile():
    payload = build_ingest_payload(
        Path("examples/synthetic-vault"),
        config_path=Path("missing.toml"),
        profile_path=Path("examples/vault-profiles/generated-demo.toml"),
    )
    context = payload["context"]
    profile_row = payload["profile_row"]
    note_type_counts = json.loads(profile_row[9])

    assert any(file.note_type == "company" for file in context.files)
    assert note_type_counts["company"] >= 1
    assert "meeting" in json.loads(profile_row[8])
    assert profile_row[0] is True
    assert profile_row[2] == "examples/vault-profiles/generated-demo.toml"
    assert profile_row[10] == len(context.files)


def test_ingest_payload_uses_custom_synthetic_profile(tmp_path: Path):
    vault = tmp_path / "vault"
    profile_path = tmp_path / "profile.toml"
    (vault / "Accounts").mkdir(parents=True)
    (vault / "Logs").mkdir()
    (vault / "Accounts" / "Acme.md").write_text("# Acme\n", encoding="utf-8")
    (vault / "Logs" / "Call.md").write_text("# Call\n", encoding="utf-8")
    profile_path.write_text(
        """
[entities]
non_entity_note_types = ["log"]

[entities.folders]
Accounts = "account"
Logs = "log"
""".strip(),
        encoding="utf-8",
    )

    payload = build_ingest_payload(
        vault,
        config_path=tmp_path / "missing.toml",
        profile_path=profile_path,
    )
    context = payload["context"]
    profile_row = payload["profile_row"]

    assert {(file.source_path, file.note_type) for file in context.files} == {
        ("Accounts/Acme.md", "account"),
        ("Logs/Call.md", "log"),
    }
    assert json.loads(profile_row[7]) == {"Accounts": "account", "Logs": "log"}
    assert json.loads(profile_row[8]) == ["log"]
    assert json.loads(profile_row[9]) == {"account": 1, "log": 1}
    assert profile_row[2] == "<redacted:profile.toml>"
    assert str(tmp_path) not in json.dumps(profile_row)
