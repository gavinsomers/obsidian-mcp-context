from pathlib import Path


MODELS_DIR = Path("models")
MARTS_DIR = MODELS_DIR / "marts"

GENERIC_CORE_MODELS = {
    "models/marts/dim/dim_notes.sql",
    "models/marts/dim/dim_entities.sql",
    "models/marts/dim/dim_entity_types.sql",
    "models/marts/dim/dim_vault_profiles.sql",
    "models/marts/fact/fact_blocks.sql",
    "models/marts/fact/fact_tasks.sql",
    "models/marts/fact/fact_links.sql",
    "models/marts/fact/fact_tags.sql",
    "models/marts/fact/fact_mentions.sql",
    "models/marts/mart/mart_timeline.sql",
}

PROFILE_OR_DOMAIN_MODELS = {
    "models/marts/dim/dim_people.sql",
    "models/marts/dim/dim_companies.sql",
    "models/marts/dim/dim_projects.sql",
    "models/marts/fact/fact_decisions.sql",
    "models/marts/fact/fact_risks.sql",
    "models/marts/fact/fact_entity_events.sql",
    "models/marts/fact/fact_entity_relationships.sql",
    "models/marts/fact/fact_entity_states.sql",
    "models/marts/mart/mart_open_loops.sql",
    "models/marts/mart/mart_entity_open_loops.sql",
    "models/marts/mart/mart_entity_context.sql",
    "models/marts/mart/mart_person_context.sql",
    "models/marts/mart/mart_person_summary.sql",
    "models/marts/mart/mart_project_context.sql",
    "models/marts/mart/mart_project_summary.sql",
    "models/marts/mart/mart_company_summary.sql",
}


def test_generic_core_mart_contract_is_documented():
    docs = Path("docs/generic-core-marts.md").read_text(encoding="utf-8")

    for model_path in GENERIC_CORE_MODELS:
        assert Path(model_path).stem in docs


def test_generic_core_and_profile_domain_models_are_explicitly_separated():
    sql_models = {path.as_posix() for path in MARTS_DIR.glob("*/*.sql")}

    assert GENERIC_CORE_MODELS.issubset(sql_models)
    assert PROFILE_OR_DOMAIN_MODELS.issubset(sql_models)
    assert not GENERIC_CORE_MODELS & PROFILE_OR_DOMAIN_MODELS


def test_generic_core_models_do_not_filter_to_specific_business_entity_types():
    business_types = ("company", "person", "project", "decision", "risk")

    for model_path in sorted(GENERIC_CORE_MODELS):
        sql = Path(model_path).read_text(encoding="utf-8").casefold()
        for entity_type in business_types:
            assert f"= '{entity_type}'" not in sql
            assert f'= "{entity_type}"' not in sql


def test_vault_profile_metadata_is_part_of_generic_core():
    staging_sql = Path("models/staging/stg_obsidian_ingest_profile.sql").read_text(
        encoding="utf-8"
    )
    dim_sql = Path("models/marts/dim/dim_vault_profiles.sql").read_text(
        encoding="utf-8"
    )

    assert "base_obsidian_ingest_profile" in staging_sql
    assert "profile_fingerprint as vault_profile_id" in dim_sql
    assert "folder_note_types" in dim_sql
    assert "note_type_counts" in dim_sql
