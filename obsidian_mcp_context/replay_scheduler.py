from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time


DEFAULT_REPLAY_STATE = ".obsidian-mcp-replay-state.json"
DEFAULT_SCHEDULER_STATE = ".obsidian-mcp-scheduler-state.json"


@dataclass(frozen=True)
class SchedulerOptions:
    vault: Path
    ingest_command: str
    dbt_command: str
    interval_seconds: float = 60.0
    max_runs: int = 0
    once: bool = False
    state_file_name: str = DEFAULT_SCHEDULER_STATE
    replay_state_file_name: str = DEFAULT_REPLAY_STATE


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    started_at: str
    finished_at: str


class SchedulerCommandError(RuntimeError):
    def __init__(self, result: CommandResult) -> None:
        super().__init__(f"command failed with exit code {result.returncode}: {result.command}")
        self.result = result


def run_scheduler(
    options: SchedulerOptions,
    *,
    command_runner: callable | None = None,
    sleeper: callable | None = None,
) -> dict[str, object]:
    vault = options.vault.resolve()
    vault.mkdir(parents=True, exist_ok=True)
    state_path = vault / options.state_file_name
    replay_state_path = vault / options.replay_state_file_name
    runner = command_runner or _run_command
    sleep = sleeper or time.sleep
    run_history = _read_existing_history(state_path)
    max_runs = 1 if options.once else options.max_runs
    run_number = 0

    while True:
        run_number += 1
        run = _run_once(
            options=options,
            vault=vault,
            replay_state_path=replay_state_path,
            runner=runner,
            run_number=run_number,
        )
        run_history.append(run)
        _write_state(
            state_path,
            status=run["status"],
            vault=vault,
            replay_state_path=replay_state_path,
            interval_seconds=options.interval_seconds,
            run_history=run_history,
        )

        if max_runs and run_number >= max_runs:
            break
        if options.once:
            break
        sleep(options.interval_seconds)

    return _state_payload(
        status=str(run_history[-1]["status"]) if run_history else "idle",
        vault=vault,
        replay_state_path=replay_state_path,
        interval_seconds=options.interval_seconds,
        run_history=run_history,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-replay-scheduler",
        description="Run ingest and dbt repeatedly against a replay target vault.",
    )
    parser.add_argument(
        "--vault",
        default="var/replay-vault",
        help="Replay target vault path to ingest and model.",
    )
    parser.add_argument(
        "--ingest-command",
        required=True,
        help="Shell command that rebuilds Postgres raw tables from the replay vault.",
    )
    parser.add_argument(
        "--dbt-command",
        required=True,
        help="Shell command that runs dbt against the Postgres raw tables.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=60.0,
        help="Seconds to wait between successful or failed scheduler runs.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Stop after N scheduler runs. Use 0 to run until interrupted.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one ingest/dbt cycle and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = run_scheduler(
            SchedulerOptions(
                vault=Path(args.vault),
                ingest_command=args.ingest_command,
                dbt_command=args.dbt_command,
                interval_seconds=args.interval_seconds,
                max_runs=args.max_runs,
                once=args.once,
            )
        )
    except KeyboardInterrupt:
        print("Replay scheduler interrupted.", file=sys.stderr)
        return 130
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "success" else 2


def _run_once(
    *,
    options: SchedulerOptions,
    vault: Path,
    replay_state_path: Path,
    runner: callable,
    run_number: int,
) -> dict[str, object]:
    started_at = _utc_now()
    replay_state = _read_json(replay_state_path)
    run: dict[str, object] = {
        "run_number": run_number,
        "status": "running",
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "virtual_time": replay_state.get("virtual_time"),
        "latest_loaded_timestamp": replay_state.get("latest_loaded_timestamp"),
        "loaded_count": replay_state.get("loaded_count"),
        "remaining_count": replay_state.get("remaining_count"),
        "replay_state_path": str(replay_state_path),
        "ingest": None,
        "dbt": None,
    }
    start_monotonic = time.monotonic()
    try:
        ingest = runner(options.ingest_command)
        run["ingest"] = _command_result_payload(ingest)
        if ingest.returncode != 0:
            raise SchedulerCommandError(ingest)

        dbt = runner(options.dbt_command)
        run["dbt"] = _command_result_payload(dbt)
        if dbt.returncode != 0:
            raise SchedulerCommandError(dbt)

        run["status"] = "success"
    except SchedulerCommandError as exc:
        if run["ingest"] is None and exc.result.command == options.ingest_command:
            run["ingest"] = _command_result_payload(exc.result)
        if run["dbt"] is None and exc.result.command == options.dbt_command:
            run["dbt"] = _command_result_payload(exc.result)
        run["status"] = "failed"
        run["error"] = str(exc)
    finished_at = _utc_now()
    run["finished_at"] = finished_at
    run["duration_seconds"] = round(time.monotonic() - start_monotonic, 3)
    return run


def _run_command(command: str) -> CommandResult:
    started_at = _utc_now()
    completed = subprocess.run(
        command,
        shell=True,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        started_at=started_at,
        finished_at=_utc_now(),
    )


def _read_existing_history(path: Path) -> list[dict[str, object]]:
    payload = _read_json(path)
    runs = payload.get("runs", [])
    return list(runs) if isinstance(runs, list) else []


def _write_state(
    path: Path,
    *,
    status: str,
    vault: Path,
    replay_state_path: Path,
    interval_seconds: float,
    run_history: list[dict[str, object]],
) -> None:
    path.write_text(
        json.dumps(
            _state_payload(
                status=status,
                vault=vault,
                replay_state_path=replay_state_path,
                interval_seconds=interval_seconds,
                run_history=run_history,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _state_payload(
    *,
    status: str,
    vault: Path,
    replay_state_path: Path,
    interval_seconds: float,
    run_history: list[dict[str, object]],
) -> dict[str, object]:
    last_run = run_history[-1] if run_history else None
    return {
        "status": status,
        "updated_at": _utc_now(),
        "vault": str(vault),
        "replay_state_path": str(replay_state_path),
        "interval_seconds": interval_seconds,
        "run_count": len(run_history),
        "last_success_at": _last_success_at(run_history),
        "last_virtual_time": last_run.get("virtual_time") if last_run else None,
        "last_loaded_count": last_run.get("loaded_count") if last_run else None,
        "last_remaining_count": last_run.get("remaining_count") if last_run else None,
        "runs": run_history[-20:],
    }


def _command_result_payload(result: CommandResult) -> dict[str, object]:
    return {
        "command": result.command,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "started_at": result.started_at,
        "finished_at": result.finished_at,
    }


def _last_success_at(run_history: list[dict[str, object]]) -> str | None:
    for run in reversed(run_history):
        if run.get("status") == "success":
            return str(run.get("finished_at"))
    return None


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
