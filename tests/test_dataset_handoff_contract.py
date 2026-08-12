from pathlib import Path


HANDOFF_DOC = Path("docs/dataset-handoff-contract.md")


def test_dataset_handoff_contract_documents_manual_import_boundary():
    text = HANDOFF_DOC.read_text(encoding="utf-8")

    assert "does not ask the" in text
    assert "generator to copy, publish, sync, or move datasets" in text
    assert "The handoff is intentionally manual" in text
    assert "var/imported-vaults/<dataset-id>/" in text
    assert "VAULT_PATH=./var/imported-vaults/generated-current" in text
    assert "docker compose --profile workflow -f docker-compose.analytics.yml run --rm dataset-workflow" in text
    assert "does not copy from the generator and does not run replay" in text


def test_dataset_handoff_contract_defines_completed_vault_shape():
    text = HANDOFF_DOC.read_text(encoding="utf-8")

    assert "manifest.json" in text
    assert "At least one Markdown note" in text
    assert "completed" in text
    assert "note_count" in text
    assert "counts.Total_Files" in text


def test_primary_docs_link_to_dataset_handoff_contract():
    readme = Path("readme.md").read_text(encoding="utf-8")
    container_stack = Path("docs/container-stack.md").read_text(encoding="utf-8")
    onboarding = Path("docs/onboarding.md").read_text(encoding="utf-8")

    assert "docs/dataset-handoff-contract.md" in readme
    assert "dataset-handoff-contract.md" in container_stack
    assert "dataset-handoff-contract.md" in onboarding
