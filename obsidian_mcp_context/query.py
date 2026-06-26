from __future__ import annotations

from dataclasses import asdict

from obsidian_mcp_context.vault import VaultContext


def _contains(value: str | None, needle: str | None) -> bool:
    if not needle:
        return True
    return needle.casefold() in (value or "").casefold()


def list_notes(context: VaultContext, limit: int = 100) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source_file in context.files[:limit]:
        note_blocks = [
            block for block in context.blocks if block.source_path == source_file.source_path
        ]
        rows.append(
            {
                "source_path": source_file.source_path,
                "absolute_path": str(source_file.absolute_path),
                "block_count": len(note_blocks),
            }
        )
    return rows


def search_blocks(
    context: VaultContext,
    text: str | None = None,
    source_path: str | None = None,
    heading: str | None = None,
    limit: int = 25,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for block in context.blocks:
        if not _contains(block.text, text):
            continue
        if not _contains(block.source_path, source_path):
            continue
        if not _contains(block.heading_path, heading):
            continue
        rows.append(asdict(block))
        if len(rows) >= limit:
            break
    return rows


def list_tasks(
    context: VaultContext,
    checked: bool | None = None,
    text: str | None = None,
    source_path: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for task in context.tasks:
        if checked is not None and task.checked is not checked:
            continue
        if not _contains(task.task_text, text):
            continue
        if not _contains(task.source_path, source_path):
            continue
        rows.append(asdict(task))
        if len(rows) >= limit:
            break
    return rows


def get_note_context(context: VaultContext, source_path: str) -> dict[str, object]:
    return {
        "source_path": source_path,
        "blocks": [
            asdict(block) for block in context.blocks if block.source_path == source_path
        ],
        "tasks": [
            asdict(task) for task in context.tasks if task.source_path == source_path
        ],
        "links": [
            asdict(link) for link in context.links if link.source_path == source_path
        ],
        "tags": [asdict(tag) for tag in context.tags if tag.source_path == source_path],
        "lines": [
            asdict(line) for line in context.lines if line.source_path == source_path
        ],
    }
