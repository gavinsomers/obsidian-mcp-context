from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1, sha256
from pathlib import Path
import re


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TASK_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.+)$")
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
TAG_RE = re.compile(r"(?<![\w/])#([A-Za-z0-9][A-Za-z0-9_/-]*)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")


@dataclass(frozen=True)
class ParsedBlock:
    source_path: str
    block_id: str
    block_hash: str
    heading: str | None
    heading_path: str | None
    heading_level: int
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class ParsedTask:
    source_path: str
    block_id: str
    task_id: str
    task_text: str
    checked: bool
    line_number: int
    heading: str | None
    heading_path: str | None
    block_hash: str


@dataclass(frozen=True)
class ParsedLink:
    source_path: str
    block_id: str
    link_target: str
    link_text: str
    line_number: int


@dataclass(frozen=True)
class ParsedTag:
    source_path: str
    block_id: str
    tag: str
    line_number: int


@dataclass(frozen=True)
class ParsedLine:
    source_path: str
    block_id: str
    line_number: int
    heading: str | None
    heading_path: str | None
    text: str


@dataclass(frozen=True)
class ParsedFile:
    blocks: list[ParsedBlock]
    tasks: list[ParsedTask]
    links: list[ParsedLink]
    tags: list[ParsedTag]
    lines: list[ParsedLine]


@dataclass
class _TaskDraft:
    task_text: str
    checked: bool
    line_number: int


@dataclass
class _LinkDraft:
    link_target: str
    link_text: str
    line_number: int


@dataclass
class _TagDraft:
    tag: str
    line_number: int


@dataclass
class _LineDraft:
    text: str
    line_number: int


def _hash_sha1(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()


def _hash_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _normalize_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def _clean_heading(raw: str) -> str:
    return raw.strip().rstrip("#").strip()


def _split_wikilink(raw: str) -> tuple[str, str]:
    if "|" in raw:
        target, label = raw.split("|", 1)
    else:
        target, label = raw, raw
    return target.strip(), label.strip()


def _strip_inline_code(line: str) -> str:
    return INLINE_CODE_RE.sub("", line)


class _CurrentBlock:
    def __init__(
        self,
        source_path: str,
        heading: str | None,
        heading_path: str | None,
        heading_level: int,
        start_line: int,
    ) -> None:
        self.source_path = source_path
        self.heading = heading
        self.heading_path = heading_path
        self.heading_level = heading_level
        self.start_line = start_line
        self.lines: list[str] = []
        self.tasks: list[_TaskDraft] = []
        self.links: list[_LinkDraft] = []
        self.tags: list[_TagDraft] = []
        self.semantic_lines: list[_LineDraft] = []

    def append_line(self, line: str) -> None:
        self.lines.append(line)

    def finish(
        self, end_line: int
    ) -> tuple[
        ParsedBlock,
        list[ParsedTask],
        list[ParsedLink],
        list[ParsedTag],
        list[ParsedLine],
    ]:
        text = "\n".join(self.lines).rstrip("\n")
        normalized = _normalize_text(text)
        block_hash = _hash_sha256(normalized)
        block_id = _hash_sha1(
            f"{self.source_path}:{self.heading_path or ''}:{self.start_line}"
        )
        block = ParsedBlock(
            source_path=self.source_path,
            block_id=block_id,
            block_hash=block_hash,
            heading=self.heading,
            heading_path=self.heading_path,
            heading_level=self.heading_level,
            start_line=self.start_line,
            end_line=max(end_line, self.start_line),
            text=text,
        )
        tasks = [
            ParsedTask(
                source_path=self.source_path,
                block_id=block_id,
                task_id=_hash_sha1(
                    f"{self.source_path}:{task.line_number}:{_normalize_text(task.task_text)}"
                ),
                task_text=task.task_text,
                checked=task.checked,
                line_number=task.line_number,
                heading=self.heading,
                heading_path=self.heading_path,
                block_hash=block_hash,
            )
            for task in self.tasks
        ]
        links = [
            ParsedLink(
                source_path=self.source_path,
                block_id=block_id,
                link_target=link.link_target,
                link_text=link.link_text,
                line_number=link.line_number,
            )
            for link in self.links
        ]
        tags = [
            ParsedTag(
                source_path=self.source_path,
                block_id=block_id,
                tag=tag.tag,
                line_number=tag.line_number,
            )
            for tag in self.tags
        ]
        lines = [
            ParsedLine(
                source_path=self.source_path,
                block_id=block_id,
                line_number=line.line_number,
                heading=self.heading,
                heading_path=self.heading_path,
                text=line.text,
            )
            for line in self.semantic_lines
        ]
        return block, tasks, links, tags, lines


def parse_markdown_file(path: Path, source_path: str) -> ParsedFile:
    return parse_markdown_text(
        path.read_text(encoding="utf-8", errors="replace"), source_path
    )


def parse_plain_text_file(path: Path, source_path: str) -> ParsedFile:
    return parse_plain_text(
        path.read_text(encoding="utf-8", errors="replace"), source_path
    )


def parse_plain_text(text: str, source_path: str) -> ParsedFile:
    raw_lines = text.splitlines()
    block_id = _hash_sha1(f"{source_path}:text:1")
    semantic_lines = [
        ParsedLine(
            source_path=source_path,
            block_id=block_id,
            line_number=index,
            heading=None,
            heading_path=None,
            text=line.strip(),
        )
        for index, line in enumerate(raw_lines, start=1)
        if line.strip()
    ]
    block = ParsedBlock(
        source_path=source_path,
        block_id=block_id,
        block_hash=_hash_sha256(_normalize_text(text)),
        heading=None,
        heading_path=None,
        heading_level=0,
        start_line=1,
        end_line=max(len(raw_lines), 1),
        text=text.rstrip("\n"),
    )
    return ParsedFile(blocks=[block], tasks=[], links=[], tags=[], lines=semantic_lines)


def parse_markdown_text(text: str, source_path: str) -> ParsedFile:
    lines = text.splitlines()
    blocks: list[ParsedBlock] = []
    tasks: list[ParsedTask] = []
    links: list[ParsedLink] = []
    tags: list[ParsedTag] = []
    semantic_lines: list[ParsedLine] = []

    heading_stack: list[tuple[int, str]] = []
    current = _CurrentBlock(
        source_path=source_path,
        heading=None,
        heading_path=None,
        heading_level=0,
        start_line=1,
    )

    in_frontmatter = bool(lines and lines[0].strip() == "---")
    frontmatter_closed = not in_frontmatter
    active_fence_marker: str | None = None

    def close_current(end_line: int) -> None:
        block, block_tasks, block_links, block_tags, block_lines = current.finish(end_line)
        blocks.append(block)
        tasks.extend(block_tasks)
        links.extend(block_links)
        tags.extend(block_tags)
        semantic_lines.extend(block_lines)

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()

        if in_frontmatter:
            current.append_line(line)
            if index != 1 and stripped == "---":
                in_frontmatter = False
                frontmatter_closed = True
            continue

        fence_match = FENCE_RE.match(line)
        if fence_match and active_fence_marker is None:
            active_fence_marker = fence_match.group(1)
            current.append_line(line)
            continue
        if fence_match and fence_match.group(1) == active_fence_marker:
            active_fence_marker = None
            current.append_line(line)
            continue

        in_fenced_code_block = active_fence_marker is not None
        heading_match = HEADING_RE.match(line) if not in_fenced_code_block else None
        if heading_match:
            close_current(index - 1)
            level = len(heading_match.group(1))
            heading = _clean_heading(heading_match.group(2))
            heading_stack[:] = [
                (existing_level, existing_heading)
                for existing_level, existing_heading in heading_stack
                if existing_level < level
            ]
            heading_stack.append((level, heading))
            current = _CurrentBlock(
                source_path=source_path,
                heading=heading,
                heading_path=" > ".join(item[1] for item in heading_stack),
                heading_level=level,
                start_line=index,
            )
            current.append_line(line)
            continue

        current.append_line(line)

        if in_fenced_code_block or not frontmatter_closed:
            continue

        if line.strip():
            current.semantic_lines.append(
                _LineDraft(text=line.strip(), line_number=index)
            )

        task_match = TASK_RE.match(line)
        if task_match:
            current.tasks.append(
                _TaskDraft(
                    task_text=task_match.group(2).strip(),
                    checked=task_match.group(1).lower() == "x",
                    line_number=index,
                )
            )

        link_scan_line = _strip_inline_code(line)
        for link_match in WIKILINK_RE.finditer(link_scan_line):
            target, label = _split_wikilink(link_match.group(1))
            if target:
                current.links.append(
                    _LinkDraft(
                        link_target=target,
                        link_text=label or target,
                        line_number=index,
                    )
                )

        if not heading_match:
            for tag_match in TAG_RE.finditer(link_scan_line):
                current.tags.append(
                    _TagDraft(tag=tag_match.group(1), line_number=index)
                )

    close_current(len(lines) if lines else 1)

    return ParsedFile(
        blocks=blocks,
        tasks=tasks,
        links=links,
        tags=tags,
        lines=semantic_lines,
    )
