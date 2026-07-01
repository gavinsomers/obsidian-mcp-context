from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from obsidian_mcp_context.replay_dashboard import REPLAY_STATE_FILE, SCHEDULER_STATE_FILE


DEFAULT_ENV_FILE = ".env.analytics"
FALLBACK_ENV_FILE = ".env.analytics.example"
DEFAULT_EXAMPLES_FILE = "examples/replay-qa-examples.json"
DEFAULT_STATE_DIR = "var/replay-vault"

SERVICE_DEFAULTS = {
    "obsidian-webtop": ("OBSIDIAN_WEB_PORT", "3000", "/"),
    "mcp-http": ("MCP_PORT", "8000", "/"),
    "dbt-docs": ("DBT_DOCS_PORT", "8081", "/"),
    "postgres-browser": ("POSTGRES_BROWSER_PORT", "8082", "/"),
    "replay-dashboard": ("REPLAY_DASHBOARD_PORT", "8083", "/api/status"),
    "replay-qa": ("REPLAY_QA_PORT", "8084", "/api/status"),
}


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-synthetic-demo-health",
        description="Check the generated-vault synthetic demo stack and canned replay Q&A examples.",
    )
    parser.add_argument(
        "--env-file",
        default=os.environ.get("ENV_FILE") or _default_env_file(),
        help="Compose env file to read ports from. Defaults to .env.analytics, then .env.analytics.example.",
    )
    parser.add_argument(
        "--state-dir",
        default=os.environ.get("REPLAY_TARGET_VAULT") or DEFAULT_STATE_DIR,
        help="Replay target vault containing replay and scheduler state files.",
    )
    parser.add_argument(
        "--examples",
        default=DEFAULT_EXAMPLES_FILE,
        help="JSON file containing canned replay Q&A examples.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--skip-dbt-docs", action="store_true")
    parser.add_argument("--skip-http", action="store_true")
    parser.add_argument("--skip-qa", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable check results.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = _read_env_file(Path(args.env_file))
    checks = run_checks(
        env=env,
        state_dir=Path(args.state_dir),
        examples_path=Path(args.examples),
        host=args.host,
        timeout=args.timeout,
        include_dbt_docs=not args.skip_dbt_docs,
        include_http=not args.skip_http,
        include_qa=not args.skip_qa,
    )
    payload = {
        "ok": all(check.ok for check in checks),
        "checks": [check.__dict__ for check in checks],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_human(checks)
    return 0 if payload["ok"] else 1


def run_checks(
    *,
    env: dict[str, str],
    state_dir: Path,
    examples_path: Path,
    host: str,
    timeout: float,
    include_dbt_docs: bool = True,
    include_http: bool = True,
    include_qa: bool = True,
) -> list[Check]:
    checks: list[Check] = []
    checks.extend(_state_checks(state_dir))
    if include_http:
        checks.extend(
            _service_checks(
                env=env,
                host=host,
                timeout=timeout,
                include_dbt_docs=include_dbt_docs,
            )
        )
    if include_qa:
        checks.extend(
            _qa_example_checks(
                examples_path=examples_path,
                qa_url=_service_url(
                    env=env,
                    host=host,
                    service="replay-qa",
                    path="/api/ask",
                ),
                timeout=timeout,
            )
        )
    return checks


def _state_checks(state_dir: Path) -> list[Check]:
    checks = [Check("state-dir", state_dir.exists(), str(state_dir))]
    replay = _read_json(state_dir / REPLAY_STATE_FILE)
    scheduler = _read_json(state_dir / SCHEDULER_STATE_FILE)
    checks.append(
        Check(
            "replay-state",
            bool(replay) and _int_value(replay.get("loaded_count")) > 0,
            _state_detail(replay, "loaded_count"),
        )
    )
    checks.append(
        Check(
            "scheduler-state",
            scheduler.get("status") == "success",
            f"status={scheduler.get('status', 'missing')}",
        )
    )
    return checks


def _service_checks(
    *,
    env: dict[str, str],
    host: str,
    timeout: float,
    include_dbt_docs: bool,
) -> list[Check]:
    checks: list[Check] = []
    for service in SERVICE_DEFAULTS:
        if service == "dbt-docs" and not include_dbt_docs:
            continue
        url = _service_url(env=env, host=host, service=service)
        try:
            status, payload = _http_get(url, timeout=timeout)
        except Exception as exc:  # pragma: no cover - exact exception varies by platform.
            checks.append(Check(service, False, f"{url}: {exc}"))
            continue
        ok = 200 <= status < 500
        detail = f"{url}: HTTP {status}"
        if service in {"replay-dashboard", "replay-qa"}:
            readiness = payload.get("readiness") if isinstance(payload, dict) else None
            ready = isinstance(readiness, dict) and readiness.get("ready") is True
            ok = ok and ready
            detail = f"{detail}, ready={ready}"
        checks.append(Check(service, ok, detail))
    return checks


def _qa_example_checks(
    *,
    examples_path: Path,
    qa_url: str,
    timeout: float,
) -> list[Check]:
    payload = _read_json(examples_path)
    examples = payload.get("examples") if isinstance(payload, dict) else None
    if not isinstance(examples, list):
        return [Check("qa-examples-file", False, f"{examples_path}: missing examples[]")]
    checks = [Check("qa-examples-file", True, f"{examples_path}: {len(examples)} examples")]
    for example in examples:
        if not isinstance(example, dict):
            checks.append(Check("qa-example", False, "example is not an object"))
            continue
        example_id = str(example.get("id") or example.get("question") or "unnamed")
        question = str(example.get("question", "")).strip()
        if not question:
            checks.append(Check(f"qa-example:{example_id}", False, "missing question"))
            continue
        try:
            answer = _http_post_json(
                qa_url,
                {"question": question, "summarize": bool(example.get("summarize", False))},
                timeout=timeout,
            )
        except Exception as exc:
            checks.append(Check(f"qa-example:{example_id}", False, f"{qa_url}: {exc}"))
            continue
        checks.append(_validate_qa_answer(example_id, example, answer))
    return checks


def _validate_qa_answer(
    example_id: str,
    example: dict[str, Any],
    answer: dict[str, Any],
) -> Check:
    failures: list[str] = []
    expected_status = example.get("expected_status")
    if expected_status and answer.get("status") != expected_status:
        failures.append(f"status={answer.get('status')!r}")
    expected_entity = example.get("expected_entity")
    entity = answer.get("entity") if isinstance(answer.get("entity"), dict) else {}
    if expected_entity and entity.get("name") != expected_entity:
        failures.append(f"entity={entity.get('name')!r}")
    mode_contains = str(example.get("expected_mode_contains", ""))
    if mode_contains and mode_contains not in str(answer.get("mode", "")):
        failures.append(f"mode={answer.get('mode')!r}")
    min_sources = int(example.get("min_sources", 0) or 0)
    sources = answer.get("sources") if isinstance(answer.get("sources"), list) else []
    if len(sources) < min_sources:
        failures.append(f"sources={len(sources)}")
    for expected in example.get("expected_answer_contains", []) or []:
        if str(expected) not in str(answer.get("answer", "")):
            failures.append(f"answer missing {expected!r}")
    source_text = json.dumps(sources, sort_keys=True)
    for expected in example.get("expected_source_contains", []) or []:
        if str(expected) not in source_text:
            failures.append(f"sources missing {expected!r}")
    detail = "ok" if not failures else "; ".join(failures)
    return Check(f"qa-example:{example_id}", not failures, detail)


def _service_url(
    *,
    env: dict[str, str],
    host: str,
    service: str,
    path: str | None = None,
) -> str:
    port_key, default_port, default_path = SERVICE_DEFAULTS[service]
    port = os.environ.get(port_key) or env.get(port_key) or default_port
    return f"http://{host}:{port}{path or default_path}"


def _http_get(url: str, *, timeout: float) -> tuple[int, dict[str, Any]]:
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, _maybe_json(body)
    except HTTPError as exc:
        return exc.code, {}
    except URLError as exc:
        raise RuntimeError(exc.reason) from exc


def _http_post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        decoded = _maybe_json(body)
        if not isinstance(decoded, dict):
            raise RuntimeError("response was not a JSON object")
        return decoded


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _maybe_json(body: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _state_detail(state: dict[str, Any], key: str) -> str:
    if not state:
        return "missing"
    return f"{key}={state.get(key, 'missing')}"


def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _default_env_file() -> str:
    if Path(DEFAULT_ENV_FILE).exists():
        return DEFAULT_ENV_FILE
    return FALLBACK_ENV_FILE


def _print_human(checks: list[Check]) -> None:
    for check in checks:
        marker = "OK" if check.ok else "FAIL"
        print(f"[{marker}] {check.name}: {check.detail}")
    if not all(check.ok for check in checks):
        print("Synthetic demo health check failed.", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
