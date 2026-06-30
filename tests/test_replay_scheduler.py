from __future__ import annotations

import json

from obsidian_mcp_context.replay_scheduler import (
    CommandResult,
    SchedulerOptions,
    main,
    run_scheduler,
)


def _result(command: str, returncode: int = 0) -> CommandResult:
    return CommandResult(
        command=command,
        returncode=returncode,
        stdout=f"ok: {command}",
        stderr="" if returncode == 0 else "failed",
        started_at="2026-06-30T10:00:00+00:00",
        finished_at="2026-06-30T10:00:01+00:00",
    )


def test_scheduler_runs_ingest_then_dbt_and_records_replay_watermark(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian-mcp-replay-state.json").write_text(
        json.dumps(
            {
                "virtual_time": "2023-04-20T06:14:00",
                "latest_loaded_timestamp": "2023-04-20T06:14:00",
                "loaded_count": 3,
                "remaining_count": 5677,
            }
        ),
        encoding="utf-8",
    )
    commands: list[str] = []

    def runner(command: str) -> CommandResult:
        commands.append(command)
        return _result(command)

    report = run_scheduler(
        SchedulerOptions(
            vault=vault,
            ingest_command="ingest",
            dbt_command="dbt",
            once=True,
        ),
        command_runner=runner,
    )

    state = json.loads((vault / ".obsidian-mcp-scheduler-state.json").read_text())
    assert commands == ["ingest", "dbt"]
    assert report["status"] == "success"
    assert state["run_count"] == 1
    assert state["last_virtual_time"] == "2023-04-20T06:14:00"
    assert state["last_loaded_count"] == 3
    assert state["last_remaining_count"] == 5677
    assert state["runs"][0]["status"] == "success"


def test_scheduler_records_failure_and_skips_dbt_when_ingest_fails(tmp_path):
    vault = tmp_path / "vault"
    commands: list[str] = []

    def runner(command: str) -> CommandResult:
        commands.append(command)
        return _result(command, returncode=1)

    report = run_scheduler(
        SchedulerOptions(
            vault=vault,
            ingest_command="ingest",
            dbt_command="dbt",
            once=True,
        ),
        command_runner=runner,
    )

    run = report["runs"][0]
    assert commands == ["ingest"]
    assert report["status"] == "failed"
    assert run["status"] == "failed"
    assert run["ingest"]["returncode"] == 1
    assert run["dbt"] is None


def test_scheduler_preserves_existing_history(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state_path = vault / ".obsidian-mcp-scheduler-state.json"
    state_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_number": 99,
                        "status": "success",
                        "finished_at": "2026-06-30T09:00:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = run_scheduler(
        SchedulerOptions(
            vault=vault,
            ingest_command="ingest",
            dbt_command="dbt",
            once=True,
        ),
        command_runner=lambda command: _result(command),
    )

    assert report["run_count"] == 2
    assert report["runs"][0]["run_number"] == 99
    assert report["runs"][1]["run_number"] == 1


def test_cli_returns_nonzero_on_failed_run(tmp_path, capsys):
    exit_code = main(
        [
            "--vault",
            str(tmp_path / "vault"),
            "--ingest-command",
            "false",
            "--dbt-command",
            "echo should-not-run",
            "--once",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert report["status"] == "failed"
