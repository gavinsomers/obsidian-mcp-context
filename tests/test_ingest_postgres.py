from __future__ import annotations

import pytest

from obsidian_mcp_context.ingest_postgres import _validate_schema, build_parser


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
