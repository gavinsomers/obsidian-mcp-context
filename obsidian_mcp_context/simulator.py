from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import shutil


LIFECYCLE_FIELD_RE = re.compile(
    r"(?m)^created_at:\s*[\"']?(?P<value>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})[\"']?\s*$"
)


def _created_at(path: Path) -> datetime | None:
    if path.suffix != ".md":
        return None
    match = LIFECYCLE_FIELD_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    if not match:
        return None
    return datetime.fromisoformat(match.group("value"))


def _relative_markdown_files(seed_vault: Path) -> list[Path]:
    return sorted(
        path.relative_to(seed_vault)
        for path in seed_vault.rglob("*.md")
        if path.is_file()
    )


def _simulation_bounds(seed_vault: Path) -> tuple[date, date]:
    created_dates = [
        created.date()
        for rel_path in _relative_markdown_files(seed_vault)
        if (created := _created_at(seed_vault / rel_path)) is not None
    ]
    if not created_dates:
        today = date.today()
        return today, today
    return min(created_dates), max(created_dates)


def _load_state(state_path: Path, seed_vault: Path) -> dict[str, object]:
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    start_date, end_date = _simulation_bounds(seed_vault)
    return {
        "virtual_date": (start_date - timedelta(days=1)).isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "released": [],
        "run_number": 0,
    }


def _write_state(state_path: Path, state: dict[str, object]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _copy_note(seed_vault: Path, live_vault: Path, rel_path: Path) -> None:
    destination = live_vault / rel_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed_vault / rel_path, destination)


def advance_simulation(
    seed_vault: Path,
    live_vault: Path,
    state_path: Path,
    days: int = 12,
) -> dict[str, object]:
    if not seed_vault.exists():
        raise FileNotFoundError(f"Seed vault does not exist: {seed_vault}")
    live_vault.mkdir(parents=True, exist_ok=True)
    state = _load_state(state_path, seed_vault)
    current_date = date.fromisoformat(str(state["virtual_date"]))
    end_date = date.fromisoformat(str(state["end_date"]))
    next_date = min(current_date + timedelta(days=days), end_date)
    released = set(str(path) for path in state.get("released", []))
    newly_released = []

    for rel_path in _relative_markdown_files(seed_vault):
        created = _created_at(seed_vault / rel_path)
        if created is None or created.date() > next_date:
            continue
        rel_path_string = rel_path.as_posix()
        if rel_path_string in released:
            continue
        _copy_note(seed_vault, live_vault, rel_path)
        released.add(rel_path_string)
        newly_released.append(rel_path_string)

    manifest_path = seed_vault / "manifest.json"
    if manifest_path.exists():
        shutil.copy2(manifest_path, live_vault / "manifest.seed.json")

    state["virtual_date"] = next_date.isoformat()
    state["released"] = sorted(released)
    state["run_number"] = int(state.get("run_number", 0)) + 1
    state["last_released_count"] = len(newly_released)
    state["total_released_count"] = len(released)
    state["complete"] = next_date >= end_date
    _write_state(state_path, state)
    return {
        "virtual_date": state["virtual_date"],
        "run_number": state["run_number"],
        "newly_released_count": len(newly_released),
        "total_released_count": len(released),
        "complete": state["complete"],
    }


def reset_simulation(live_vault: Path, state_path: Path) -> None:
    if live_vault.exists():
        shutil.rmtree(live_vault)
    if state_path.exists():
        state_path.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-simulate-vault",
        description="Release synthetic vault notes into a live vault according to virtual created_at dates.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    advance = subparsers.add_parser("advance", help="Advance virtual time and release due notes.")
    advance.add_argument("--seed-vault", required=True, help="Full generated seed vault.")
    advance.add_argument("--live-vault", required=True, help="Live vault to populate incrementally.")
    advance.add_argument("--state", required=True, help="Simulation state JSON path.")
    advance.add_argument("--days", type=int, default=12, help="Virtual days to advance.")

    reset = subparsers.add_parser("reset", help="Delete the live vault and state file.")
    reset.add_argument("--live-vault", required=True, help="Live vault to delete.")
    reset.add_argument("--state", required=True, help="Simulation state JSON path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "advance":
        result = advance_simulation(
            seed_vault=Path(args.seed_vault),
            live_vault=Path(args.live_vault),
            state_path=Path(args.state),
            days=args.days,
        )
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "reset":
        reset_simulation(live_vault=Path(args.live_vault), state_path=Path(args.state))
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
