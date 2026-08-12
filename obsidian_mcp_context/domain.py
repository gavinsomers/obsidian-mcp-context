from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from obsidian_mcp_context.parser import ParsedFile


DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
FRONTMATTER_DATE_RE = re.compile(
    r"(?ms)\A\s*---.*?^date:\s*[\"']?(\d{4}-\d{2}-\d{2})[\"']?\s*$.*?^---\s*$"
)
FRONTMATTER_FIELD_RE = re.compile(r"(?ms)\A\s*---(?P<body>.*?)^---\s*$")
NON_WORD_RE = re.compile(r"[^a-z0-9]+")
NOTE_TYPE_BY_FOLDER = {
    "companies": "company",
    "daily": "daily",
    "decisions": "decision",
    "meetings": "meeting",
    "people": "person",
    "projects": "project",
    "research": "research",
    "risks": "risk",
}
NON_ENTITY_NOTE_TYPES = {"daily", "meeting", "note", "research"}
FRONTMATTER_LIST_ITEM_RE = re.compile(r"^\s*-\s*(.+?)\s*$")


def slug(value: str) -> str:
    normalized = NON_WORD_RE.sub("-", value.casefold()).strip("-")
    return normalized or "unknown"


def note_title(
    source_path: str,
    text: str | None = None,
    *,
    parsed_file: ParsedFile | None = None,
) -> str:
    if parsed_file is None and text:
        from obsidian_mcp_context.parser import parse_markdown_text

        parsed_file = parse_markdown_text(text, source_path)
    if parsed_file:
        first_block_text = parsed_file.blocks[0].text if parsed_file.blocks else None
        explicit_title = frontmatter_value(first_block_text, "title")
        if explicit_title:
            return explicit_title
        first_h1 = next(
            (
                block.heading
                for block in parsed_file.blocks
                if block.heading_level == 1 and block.heading
            ),
            None,
        )
        if first_h1:
            return first_h1
    return Path(source_path).stem


def link_resolution_key(value: str) -> str:
    target = value.split("#", 1)[0].split("^", 1)[0].strip()
    if target.casefold().endswith(".md"):
        target = target[:-3]
    return target.casefold()


def note_resolution_keys(
    source_path: str,
    title: str,
    aliases: tuple[str, ...] = (),
) -> set[str]:
    path_without_extension = (
        source_path[:-3] if source_path.casefold().endswith(".md") else source_path
    )
    keys = {
        title.casefold(),
        path_without_extension.casefold(),
        PurePosixPath(path_without_extension).name.casefold(),
    }
    keys.update(link_resolution_key(alias) for alias in aliases)
    return {key for key in keys if key}


def note_type(
    source_path: str,
    folder_note_types: dict[str, str] | None = None,
) -> str:
    parts = PurePosixPath(source_path).parts
    if not parts:
        return "note"
    folder = parts[0].casefold()
    configured = {
        key.casefold(): value for key, value in (folder_note_types or {}).items()
    }
    if folder in configured:
        return configured[folder]
    if folder in NOTE_TYPE_BY_FOLDER:
        return NOTE_TYPE_BY_FOLDER[folder]
    if len(parts) == 1:
        return "note"
    return singular_entity_type(folder)


def singular_entity_type(folder: str) -> str:
    normalized = slug(folder).replace("-", "_")
    if normalized.endswith("ies") and len(normalized) > 3:
        return f"{normalized[:-3]}y"
    if normalized.endswith("s") and len(normalized) > 1:
        return normalized[:-1]
    return normalized or "note"


def is_entity_note_type(value: str) -> bool:
    return value not in NON_ENTITY_NOTE_TYPES


def source_date(source_path: str, text: str | None = None) -> str | None:
    match = DATE_RE.search(source_path)
    if match:
        return match.group(1)
    if text:
        frontmatter_match = FRONTMATTER_DATE_RE.search(text)
        if frontmatter_match:
            return frontmatter_match.group(1)
        content_text = FRONTMATTER_FIELD_RE.sub("", text, count=1)
        content_match = DATE_RE.search(content_text)
        if content_match:
            return content_match.group(1)
    return None


def _clean_frontmatter_scalar(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
        quote = cleaned[0]
        cleaned = cleaned[1:-1]
        if quote == "'":
            cleaned = cleaned.replace("''", "'")
    return cleaned.strip()


def frontmatter_values(text: str | None, field: str) -> tuple[str, ...]:
    if not text:
        return ()
    frontmatter_match = FRONTMATTER_FIELD_RE.search(text)
    if not frontmatter_match:
        return ()

    values: list[str] = []
    collecting_block = False
    for line in frontmatter_match.group("body").splitlines():
        field_match = re.match(rf"^{re.escape(field)}:\s*(.*)$", line)
        if field_match:
            raw_value = field_match.group(1).strip()
            collecting_block = not raw_value
            if raw_value.startswith("[") and raw_value.endswith("]"):
                values.extend(
                    cleaned
                    for item in raw_value[1:-1].split(",")
                    if (cleaned := _clean_frontmatter_scalar(item))
                )
            elif raw_value:
                values.append(_clean_frontmatter_scalar(raw_value))
            continue
        if collecting_block:
            item_match = FRONTMATTER_LIST_ITEM_RE.match(line)
            if item_match:
                value = _clean_frontmatter_scalar(item_match.group(1))
                if value:
                    values.append(value)
                continue
            if line and not line.startswith((" ", "\t")):
                collecting_block = False
    return tuple(dict.fromkeys(value for value in values if value))


def frontmatter_value(text: str | None, field: str) -> str | None:
    values = frontmatter_values(text, field)
    return values[0] if values else None
