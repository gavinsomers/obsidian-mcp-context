from pathlib import Path


MODELS_DIR = Path("models")
MARTS_DIR = MODELS_DIR / "marts"


def test_dbt_model_layers_are_separated_by_folder():
    assert (MODELS_DIR / "staging").is_dir()
    assert (MODELS_DIR / "intermediate").is_dir()
    assert (MARTS_DIR / "dim").is_dir()
    assert (MARTS_DIR / "fact").is_dir()
    assert (MARTS_DIR / "mart").is_dir()

    root_sql_models = sorted(path.name for path in MARTS_DIR.glob("*.sql"))
    assert root_sql_models == []


def test_dbt_mart_model_prefixes_match_their_folder():
    expected_prefixes = {
        MARTS_DIR / "dim": "dim_",
        MARTS_DIR / "fact": "fact_",
        MARTS_DIR / "mart": "mart_",
    }

    for folder, prefix in expected_prefixes.items():
        sql_models = sorted(folder.glob("*.sql"))
        assert sql_models, f"Expected dbt models in {folder}"
        assert all(path.name.startswith(prefix) for path in sql_models)
