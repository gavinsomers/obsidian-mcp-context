from __future__ import annotations

from datetime import date
from pathlib import Path

from obsidian_mcp_context.simulator import advance_simulation, reset_simulation
from obsidian_mcp_context.synthetic import generate_synthetic_vault


def test_simulator_releases_notes_incrementally_by_virtual_day(tmp_path: Path):
    seed_vault = tmp_path / "seed"
    live_vault = tmp_path / "live"
    state_path = tmp_path / "state" / "simulation-state.json"
    generate_synthetic_vault(
        seed_vault,
        profile="small",
        seed=42,
        start_date=date(2025, 1, 6),
    )

    first = advance_simulation(seed_vault, live_vault, state_path, days=1)
    first_files = set(live_vault.glob("*/*.md"))
    second = advance_simulation(seed_vault, live_vault, state_path, days=12)
    second_files = set(live_vault.glob("*/*.md"))

    assert first["run_number"] == 1
    assert second["run_number"] == 2
    assert first["newly_released_count"] > 0
    assert second["newly_released_count"] > 0
    assert len(first_files) < len(second_files)
    assert first_files.issubset(second_files)


def test_simulator_reset_clears_live_vault_and_state(tmp_path: Path):
    seed_vault = tmp_path / "seed"
    live_vault = tmp_path / "live"
    state_path = tmp_path / "state" / "simulation-state.json"
    generate_synthetic_vault(seed_vault, profile="small", seed=42)
    advance_simulation(seed_vault, live_vault, state_path, days=12)

    reset_simulation(live_vault, state_path)

    assert not live_vault.exists()
    assert not state_path.exists()
