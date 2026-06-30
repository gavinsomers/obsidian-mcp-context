from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import time

from obsidian_mcp_context.domain import frontmatter_value, source_date


DEFAULT_STATE_FILE = ".obsidian-mcp-replay-state.json"
DEFAULT_TIMESTAMP_FIELD = "created_at"
TIMESTAMP_FALLBACK_FIELDS = (
    "created_at",
    "source_created_at",
    "source_observed_at",
    "updated_at",
)


@dataclass(frozen=True)
class ReplayEntry:
    relative_path: str
    replay_timestamp: datetime
    timestamp_source: str
    size_bytes: int


@dataclass(frozen=True)
class ReplayOptions:
    source: Path
    target: Path
    timestamp_field: str = DEFAULT_TIMESTAMP_FIELD
    start: datetime | None = None
    end: datetime | None = None
    speed: float = 0.0
    tick_seconds: float = 1.0
    batch_size: int = 0
    limit: int = 0
    dry_run: bool = False
    reset: bool = False
    state_file_name: str = DEFAULT_STATE_FILE


def parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if not normalized:
        raise ValueError("empty timestamp")
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    if "T" not in normalized and len(normalized) == 10:
        normalized = f"{normalized}T00:00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def build_replay_manifest(
    source: Path,
    *,
    timestamp_field: str = DEFAULT_TIMESTAMP_FIELD,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[ReplayEntry]:
    source = source.resolve()
    entries: list[ReplayEntry] = []
    for path in sorted(source.rglob("*.md")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        timestamp, timestamp_source = _replay_timestamp(
            path, text, source=source, timestamp_field=timestamp_field
        )
        if start and timestamp < start:
            continue
        if end and timestamp > end:
            continue
        entries.append(
            ReplayEntry(
                relative_path=path.relative_to(source).as_posix(),
                replay_timestamp=timestamp,
                timestamp_source=timestamp_source,
                size_bytes=path.stat().st_size,
            )
        )
    return sorted(entries, key=lambda entry: (entry.replay_timestamp, entry.relative_path))


def run_replay(options: ReplayOptions) -> dict[str, object]:
    source = options.source.resolve()
    target = options.target.resolve()
    _validate_paths(source, target)

    entries = build_replay_manifest(
        source,
        timestamp_field=options.timestamp_field,
        start=options.start,
        end=options.end,
    )
    if options.limit:
        entries = entries[: options.limit]

    state_path = target / options.state_file_name
    if options.reset and not options.dry_run:
        _reset_target(target)

    state = _read_state(state_path)
    manifest_paths = {entry.relative_path for entry in entries}
    loaded_files = set(state.get("loaded_files", [])) & manifest_paths

    if options.dry_run:
        return _report(
            options=options,
            entries=entries,
            loaded_files=loaded_files,
            copied=[],
            state_path=state_path,
            status="dry_run",
        )

    target.mkdir(parents=True, exist_ok=True)
    copied: list[ReplayEntry] = []
    virtual_now = entries[0].replay_timestamp if entries else None

    while True:
        due = _due_entries(entries, loaded_files, virtual_now)
        if options.batch_size > 0:
            due = due[: options.batch_size]
        for entry in due:
            _copy_entry(source, target, entry)
            loaded_files.add(entry.relative_path)
            copied.append(entry)

        remaining = [entry for entry in entries if entry.relative_path not in loaded_files]
        latest_loaded = copied[-1].replay_timestamp if copied else _latest_loaded(entries, loaded_files)
        _write_state(
            state_path,
            source=source,
            target=target,
            options=options,
            entries=entries,
            loaded_files=loaded_files,
            latest_loaded=latest_loaded,
            virtual_now=virtual_now,
        )

        if not remaining:
            break
        if options.speed <= 0:
            virtual_now = remaining[-1].replay_timestamp
            continue

        if virtual_now is None:
            virtual_now = remaining[0].replay_timestamp
        time.sleep(options.tick_seconds)
        virtual_now = datetime.fromtimestamp(
            virtual_now.timestamp() + (options.speed * options.tick_seconds)
        )

    return _report(
        options=options,
        entries=entries,
        loaded_files=loaded_files,
        copied=copied,
        state_path=state_path,
        status="complete",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-replay-vault",
        description="Replay generated Obsidian notes into an isolated target vault.",
    )
    parser.add_argument(
        "--source",
        default="examples/generated-vaults/large",
        help="Generated source vault to replay from.",
    )
    parser.add_argument(
        "--target",
        default="var/replay-vault",
        help="Isolated target vault to populate.",
    )
    parser.add_argument(
        "--timestamp-field",
        default=DEFAULT_TIMESTAMP_FIELD,
        help="Preferred frontmatter timestamp field for replay ordering.",
    )
    parser.add_argument("--start", help="Inclusive replay start timestamp or date.")
    parser.add_argument("--end", help="Inclusive replay end timestamp or date.")
    parser.add_argument(
        "--speed",
        type=float,
        default=0.0,
        help=(
            "Virtual seconds advanced per real second. "
            "Use 0 to copy all selected notes immediately."
        ),
    )
    parser.add_argument(
        "--tick-seconds",
        type=float,
        default=1.0,
        help="Real seconds between replay ticks when --speed is greater than 0.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Maximum notes copied per tick. Use 0 for no per-tick cap.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit the sorted manifest to the first N notes, mainly for smoke tests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the replay manifest summary without copying files.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the target vault contents before replaying.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = run_replay(
            ReplayOptions(
                source=Path(args.source),
                target=Path(args.target),
                timestamp_field=args.timestamp_field,
                start=parse_datetime(args.start) if args.start else None,
                end=parse_datetime(args.end) if args.end else None,
                speed=args.speed,
                tick_seconds=args.tick_seconds,
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=args.dry_run,
                reset=args.reset,
            )
        )
    except (OSError, ValueError) as exc:
        print(f"Replay failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _replay_timestamp(
    path: Path,
    text: str,
    *,
    source: Path,
    timestamp_field: str,
) -> tuple[datetime, str]:
    requested = frontmatter_value(text, timestamp_field)
    if requested:
        return parse_datetime(requested), timestamp_field
    for field in TIMESTAMP_FALLBACK_FIELDS:
        if field == timestamp_field:
            continue
        value = frontmatter_value(text, field)
        if value:
            return parse_datetime(value), field
    date_value = frontmatter_value(text, "date") or source_date(path.relative_to(source).as_posix(), text)
    if date_value:
        return parse_datetime(date_value), "date"
    stat = path.stat()
    return datetime.fromtimestamp(stat.st_mtime), "mtime"


def _validate_paths(source: Path, target: Path) -> None:
    if not source.exists() or not source.is_dir():
        raise ValueError(f"source vault does not exist: {source}")
    if source == target:
        raise ValueError("source and target vault paths must differ")
    if target in source.parents:
        raise ValueError("target vault cannot be a parent of the source vault")
    if source in target.parents:
        raise ValueError("target vault cannot be inside the source vault")


def _reset_target(target: Path) -> None:
    if not target.exists():
        return
    for child in target.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _read_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_state(
    path: Path,
    *,
    source: Path,
    target: Path,
    options: ReplayOptions,
    entries: list[ReplayEntry],
    loaded_files: set[str],
    latest_loaded: datetime | None,
    virtual_now: datetime | None,
) -> None:
    remaining = len([entry for entry in entries if entry.relative_path not in loaded_files])
    payload = {
        "source_root": str(source),
        "target_root": str(target),
        "timestamp_field": options.timestamp_field,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "virtual_time": _format_datetime(virtual_now),
        "latest_loaded_timestamp": _format_datetime(latest_loaded),
        "loaded_count": len(loaded_files),
        "remaining_count": remaining,
        "total_count": len(entries),
        "loaded_files": sorted(loaded_files),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _copy_entry(source: Path, target: Path, entry: ReplayEntry) -> None:
    source_path = source / entry.relative_path
    target_path = target / entry.relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)


def _due_entries(
    entries: list[ReplayEntry],
    loaded_files: set[str],
    virtual_now: datetime | None,
) -> list[ReplayEntry]:
    if virtual_now is None:
        return [entry for entry in entries if entry.relative_path not in loaded_files]
    return [
        entry
        for entry in entries
        if entry.relative_path not in loaded_files and entry.replay_timestamp <= virtual_now
    ]


def _latest_loaded(
    entries: list[ReplayEntry], loaded_files: set[str]
) -> datetime | None:
    loaded = [entry.replay_timestamp for entry in entries if entry.relative_path in loaded_files]
    return max(loaded) if loaded else None


def _report(
    *,
    options: ReplayOptions,
    entries: list[ReplayEntry],
    loaded_files: set[str],
    copied: list[ReplayEntry],
    state_path: Path,
    status: str,
) -> dict[str, object]:
    remaining = [entry for entry in entries if entry.relative_path not in loaded_files]
    timestamps = [entry.replay_timestamp for entry in entries]
    return {
        "status": status,
        "source": str(options.source),
        "target": str(options.target),
        "state_path": str(state_path),
        "timestamp_field": options.timestamp_field,
        "total_count": len(entries),
        "copied_count": len(copied),
        "loaded_count": len(loaded_files),
        "remaining_count": len(remaining),
        "first_timestamp": _format_datetime(min(timestamps) if timestamps else None),
        "last_timestamp": _format_datetime(max(timestamps) if timestamps else None),
        "latest_loaded_timestamp": _format_datetime(
            copied[-1].replay_timestamp if copied else _latest_loaded(entries, loaded_files)
        ),
        "next_timestamp": _format_datetime(remaining[0].replay_timestamp if remaining else None),
        "sample": [
            {
                "relative_path": entry.relative_path,
                "replay_timestamp": _format_datetime(entry.replay_timestamp),
                "timestamp_source": entry.timestamp_source,
                "size_bytes": entry.size_bytes,
            }
            for entry in entries[:5]
        ],
    }


def _format_datetime(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


if __name__ == "__main__":
    raise SystemExit(main())
