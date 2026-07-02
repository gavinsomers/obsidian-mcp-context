from obsidian_mcp_context import postgres_warehouse


def test_postgres_warehouse_defaults_to_split_layer_schemas(monkeypatch):
    monkeypatch.delenv("POSTGRES_WAREHOUSE_SCHEMAS", raising=False)
    monkeypatch.delenv("POSTGRES_MART_SCHEMA", raising=False)

    assert postgres_warehouse._schemas() == (
        "mart",
        "fact",
        "dim",
        "intermediate",
        "staging",
    )


def test_postgres_warehouse_accepts_explicit_schema_search_path(monkeypatch):
    monkeypatch.setenv("POSTGRES_WAREHOUSE_SCHEMAS", "mart, fact, dim")

    assert postgres_warehouse._schemas() == ("mart", "fact", "dim")


def test_postgres_warehouse_rejects_invalid_schema_names(monkeypatch):
    monkeypatch.setenv("POSTGRES_WAREHOUSE_SCHEMAS", "mart, bad;drop")

    try:
        postgres_warehouse._schemas()
    except ValueError as exc:
        assert "Invalid Postgres schema name" in str(exc)
    else:
        raise AssertionError("Expected invalid schema names to be rejected")


def test_postgres_warehouse_requires_vault_profile_dimension():
    assert "dim_vault_profiles" in postgres_warehouse.REQUIRED_RELATIONS["dim"]
