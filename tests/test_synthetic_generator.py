from __future__ import annotations

from datetime import datetime
from pathlib import Path

from obsidian_mcp_context.ingest import ingest_vault
from obsidian_mcp_context.query import list_tasks
from obsidian_mcp_context.synthetic import generate_synthetic_vault
from obsidian_mcp_context.vault import VaultConfig, build_context


LIFECYCLE_FIELDS = (
    "source_created_at",
    "source_observed_at",
    "created_at",
    "updated_at",
)


def _frontmatter(path: Path) -> dict[str, str]:
    raw = path.read_text(encoding="utf-8").split("---", 2)[1]
    metadata = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip("\"'")
    return metadata


def test_generate_small_synthetic_vault_is_coherent_and_realistic(tmp_path: Path):
    output = tmp_path / "generated-vault"

    manifest = generate_synthetic_vault(output, profile="small", seed=123)

    markdown_files = list(output.glob("*/*.md"))
    assert len(markdown_files) == manifest["counts"]["Total_Files"]
    assert len(markdown_files) >= 220

    context = build_context(VaultConfig(vault_path=output))
    note_titles = {Path(source_file.source_path).stem for source_file in context.files}
    resolved_links = [
        link for link in context.links if link.link_target in note_titles
    ]

    assert len(context.links) >= 600
    assert len(resolved_links) / len(context.links) >= 0.9
    assert len(list_tasks(context, checked=False, limit=1000)) >= 150
    assert len(list_tasks(context, checked=True, limit=1000)) >= 40

    for folder in ("Companies", "People", "Projects", "Research", "Risks"):
        created_at_values = [
            datetime.fromisoformat(_frontmatter(path)["created_at"])
            for path in (output / folder).glob("*.md")
        ]
        assert created_at_values
        assert min(created_at_values) < max(created_at_values), folder
        assert (max(created_at_values) - min(created_at_values)).days >= 7, folder

    for path in markdown_files:
        metadata = _frontmatter(path)
        timestamps = [datetime.fromisoformat(metadata[field]) for field in LIFECYCLE_FIELDS]
        assert timestamps == sorted(timestamps), path


def test_generated_vault_ingests_into_duckdb_landing_tables(tmp_path: Path):
    vault_path = tmp_path / "generated-vault"
    duckdb_path = tmp_path / "generated.duckdb"
    manifest = generate_synthetic_vault(vault_path, profile="small", seed=123)

    counts = ingest_vault(vault_path, duckdb_path)

    assert counts["base_obsidian_files"] == manifest["counts"]["Total_Files"]
    assert counts["base_obsidian_tasks"] >= 190
    assert counts["base_obsidian_links"] >= 600
