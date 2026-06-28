from __future__ import annotations

from pathlib import Path, PurePosixPath
import re


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


def slug(value: str) -> str:
    normalized = NON_WORD_RE.sub("-", value.casefold()).strip("-")
    return normalized or "unknown"


def note_title(source_path: str) -> str:
    return Path(source_path).stem


def note_type(source_path: str) -> str:
    parts = PurePosixPath(source_path).parts
    if not parts:
        return "note"
    folder = parts[0].casefold()
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


def frontmatter_value(text: str | None, field: str) -> str | None:
    if not text:
        return None
    frontmatter_match = FRONTMATTER_FIELD_RE.search(text)
    if not frontmatter_match:
        return None
    field_match = re.search(
        rf"(?m)^{re.escape(field)}:\s*[\"']?([^\"'\n]+)[\"']?\s*$",
        frontmatter_match.group("body"),
    )
    if not field_match:
        return None
    return field_match.group(1).strip()
