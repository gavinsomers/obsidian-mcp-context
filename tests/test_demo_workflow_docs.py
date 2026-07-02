from pathlib import Path


DEMO_DOC = Path("docs/demo-workflow.md")


def test_demo_workflow_doc_describes_two_act_d3_to_dbt_flow():
    text = DEMO_DOC.read_text(encoding="utf-8")

    assert "Act 1: generator repo" in text
    assert "show dataset growth in D3" in text
    assert "manual handoff" in text
    assert "Act 2: obsidian-mcp-context" in text
    assert "VAULT_PATH=./var/imported-vaults/generated-current" in text
    assert "docker compose --profile workflow -f docker-compose.analytics.yml run --rm dataset-workflow" in text
    assert "dbt Docs:         http://localhost:8081" in text
    assert "Postgres browser: http://localhost:8082" in text
    assert "Do not use Obsidian, replay, scheduler windows, or replay Q&A" in text


def test_primary_docs_link_to_demo_workflow():
    readme = Path("README.md").read_text(encoding="utf-8")
    onboarding = Path("docs/onboarding.md").read_text(encoding="utf-8")
    container_stack = Path("docs/container-stack.md").read_text(encoding="utf-8")
    privacy = Path("docs/demo-privacy-readiness.md").read_text(encoding="utf-8")

    assert "docs/demo-workflow.md" in readme
    assert "docs/demo-workflow.md" in onboarding
    assert "docs/demo-workflow.md" in container_stack
    assert "docs/demo-workflow.md" in privacy


def test_primary_readme_no_longer_promotes_replay_or_obsidian_as_demo_path():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "VAULT_PATH=./var/imported-vaults/generated-current WITH_INSPECTION=1" in readme
    assert "docker compose --profile workflow -f docker-compose.analytics.yml run --rm dataset-workflow" in readme
    assert "ANALYTICS_STACK_KEEP_RUNNING=1" not in readme
    assert "scripts/run_generated_obsidian.sh" not in readme
    assert "scripts/check_synthetic_demo.sh" not in readme


def test_readiness_docs_use_completed_dataset_workflow_as_primary_path():
    readiness = Path("docs/v1-release-readiness.md").read_text(encoding="utf-8")
    retrieval = Path("docs/retrieval-validation.md").read_text(encoding="utf-8")

    assert "scripts/run_dataset_workflow.sh small" in readiness
    assert "scripts/run_dataset_workflow.sh large" in readiness
    assert "Dataset workflow passed." in readiness
    assert "scripts/run_synthetic_demo.sh stop" not in readiness
    assert "scripts/check_synthetic_demo.sh" not in retrieval
