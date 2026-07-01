from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading

from obsidian_mcp_context.replay_dashboard import REPLAY_STATE_FILE, SCHEDULER_STATE_FILE
from obsidian_mcp_context.synthetic_demo_health import (
    _read_env_file,
    main,
    run_checks,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/api/status"}:
            self._send_json(
                HTTPStatus.OK,
                {"readiness": {"ready": True}, "service": self.path},
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/ask":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        question = payload["question"]
        if "Beacon" in question:
            entity = "Project Beacon 2"
            source = "Risks/Project Beacon 2 Metric Reconciliation Risk 2.md"
        elif "decisions" in question or "decisions" in question.casefold():
            entity = "Project Atlas 1"
            source = "Decisions/Project Atlas 1 Security Review Decision 1.md"
        else:
            entity = "Project Atlas 1"
            source = "Risks/Project Atlas 1 Adoption Workflow Risk 1.md"
        self._send_json(
            HTTPStatus.OK,
            {
                "status": "ok",
                "mode": "mart-backed",
                "entity": {"name": entity},
                "answer": f"Mart-backed context for {entity}.",
                "sources": [{"source_path": source}],
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _server() -> tuple[ThreadingHTTPServer, threading.Thread, int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, server.server_address[1]


def test_check_synthetic_demo_script_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", "scripts/check_synthetic_demo.sh"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr


def test_read_env_file_ignores_comments_and_unquotes_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nREPLAY_QA_PORT='8084'\nOBSIDIAN_WEB_PORT=3000\n",
        encoding="utf-8",
    )

    assert _read_env_file(env_file) == {
        "REPLAY_QA_PORT": "8084",
        "OBSIDIAN_WEB_PORT": "3000",
    }


def test_run_checks_passes_with_state_services_and_canned_questions(tmp_path):
    _write_json(tmp_path / REPLAY_STATE_FILE, {"loaded_count": 3})
    _write_json(tmp_path / SCHEDULER_STATE_FILE, {"status": "success"})
    examples = tmp_path / "examples.json"
    examples.write_text(
        Path("examples/replay-qa-examples.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    server, thread, port = _server()
    try:
        env = {
            "OBSIDIAN_WEB_PORT": str(port),
            "MCP_PORT": str(port),
            "DBT_DOCS_PORT": str(port),
            "POSTGRES_BROWSER_PORT": str(port),
            "REPLAY_DASHBOARD_PORT": str(port),
            "REPLAY_QA_PORT": str(port),
        }
        checks = run_checks(
            env=env,
            state_dir=tmp_path,
            examples_path=examples,
            host="127.0.0.1",
            timeout=2,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert all(check.ok for check in checks), checks
    assert {check.name for check in checks} >= {
        "replay-dashboard",
        "replay-qa",
        "qa-example:atlas-risks-open-loops",
        "qa-example:atlas-decisions",
        "qa-example:beacon-risks",
    }


def test_main_uses_profile_selected_eval_pack(tmp_path, capsys):
    _write_json(tmp_path / REPLAY_STATE_FILE, {"loaded_count": 3})
    _write_json(tmp_path / SCHEDULER_STATE_FILE, {"status": "success"})
    eval_pack = tmp_path / "account-eval.json"
    eval_pack.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "account-eval",
                "examples": [
                    {
                        "id": "atlas-risk",
                        "question": "What are the risks for Project Atlas 1?",
                        "expected_status": "ok",
                        "expected_entity": "Project Atlas 1",
                        "min_sources": 1,
                        "expected_source_contains": ["Risks/Project Atlas 1"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        f"""
[replay_qa]
eval_pack = "{eval_pack}"
""".strip(),
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    server, thread, port = _server()
    try:
        env_file.write_text(
            "\n".join(
                [
                    f"OBSIDIAN_WEB_PORT={port}",
                    f"MCP_PORT={port}",
                    f"DBT_DOCS_PORT={port}",
                    f"POSTGRES_BROWSER_PORT={port}",
                    f"REPLAY_DASHBOARD_PORT={port}",
                    f"REPLAY_QA_PORT={port}",
                ]
            ),
            encoding="utf-8",
        )
        result = main(
            [
                "--env-file",
                str(env_file),
                "--state-dir",
                str(tmp_path),
                "--vault-profile",
                str(profile_path),
                "--skip-http",
                "--json",
            ]
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    captured = capsys.readouterr()
    assert result == 0
    payload = json.loads(captured.out)
    assert any(
        check["name"] == "qa-example:atlas-risk" and check["ok"] is True
        for check in payload["checks"]
    )


def test_run_checks_fails_when_state_is_missing(tmp_path):
    checks = run_checks(
        env={},
        state_dir=tmp_path,
        examples_path=Path("examples/replay-qa-examples.json"),
        host="127.0.0.1",
        timeout=0.01,
        include_http=False,
        include_qa=False,
    )

    assert [check.ok for check in checks] == [True, False, False]


def test_main_can_print_json_without_live_services(tmp_path, capsys):
    result = main(
        [
            "--state-dir",
            str(tmp_path),
            "--skip-http",
            "--skip-qa",
            "--json",
        ]
    )
    captured = capsys.readouterr()

    assert result == 1
    assert '"ok": false' in captured.out
