from __future__ import annotations

from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from obsidian_mcp_context.parser import (
    ParsedBlock,
    ParsedFile,
    ParsedLine,
    ParsedLink,
    ParsedTag,
    ParsedTask,
    parse_markdown_file,
    parse_plain_text_file,
)
from obsidian_mcp_context.security import validate_vault_path


DEFAULT_INCLUDE_GLOBS = ("**/*.md",)
DEFAULT_EXCLUDE_GLOBS = (
    ".git/**",
    ".obsidian/**",
    "System/Marts/**",
)
DEFAULT_SOURCE_EXTENSIONS = (".md",)


@dataclass(frozen=True)
class VaultConfig:
    vault_path: Path
    include_globs: tuple[str, ...] = DEFAULT_INCLUDE_GLOBS
    exclude_globs: tuple[str, ...] = DEFAULT_EXCLUDE_GLOBS
    source_extensions: tuple[str, ...] = DEFAULT_SOURCE_EXTENSIONS


@dataclass(frozen=True)
class SourceFile:
    source_path: str
    absolute_path: Path


@dataclass(frozen=True)
class VaultContext:
    vault_path: Path
    files: list[SourceFile]
    blocks: list[ParsedBlock]
    tasks: list[ParsedTask]
    links: list[ParsedLink]
    tags: list[ParsedTag]
    lines: list[ParsedLine]

    def to_dict(self) -> dict[str, object]:
        return {
            "vault_path": str(self.vault_path),
            "files": [asdict(item) | {"absolute_path": str(item.absolute_path)} for item in self.files],
            "blocks": [asdict(item) for item in self.blocks],
            "tasks": [asdict(item) for item in self.tasks],
            "links": [asdict(item) for item in self.links],
            "tags": [asdict(item) for item in self.tags],
            "lines": [asdict(item) for item in self.lines],
        }


def normalize_extensions(source_extensions: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        item.lower() if item.startswith(".") else f".{item.lower()}"
        for item in source_extensions
    )


def to_vault_relative(path: Path, vault_path: Path) -> str:
    return path.resolve().relative_to(vault_path.resolve()).as_posix()


def _matches_glob(source_path: str, pattern: str) -> bool:
    if pattern == "**/*.md" and source_path.endswith(".md"):
        return True
    if pattern == "**/*.txt" and source_path.endswith(".txt"):
        return True
    posix_path = PurePosixPath(source_path)
    if fnmatch(source_path, pattern) or posix_path.match(pattern):
        return True
    if "/**/" in pattern:
        zero_directory_pattern = pattern.replace("/**/", "/")
        return fnmatch(source_path, zero_directory_pattern) or posix_path.match(
            zero_directory_pattern
        )
    return False


def is_included(source_path: str, include_globs: tuple[str, ...]) -> bool:
    return any(_matches_glob(source_path, pattern) for pattern in include_globs)


def is_excluded(source_path: str, exclude_globs: tuple[str, ...]) -> bool:
    return any(_matches_glob(source_path, pattern) for pattern in exclude_globs)


def scan_vault(config: VaultConfig) -> list[SourceFile]:
    vault_path = validate_vault_path(config.vault_path)
    source_extensions = set(normalize_extensions(config.source_extensions))
    files: list[SourceFile] = []

    for path in sorted(vault_path.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in source_extensions:
            continue
        source_path = to_vault_relative(path, vault_path)
        if not is_included(source_path, config.include_globs):
            continue
        if is_excluded(source_path, config.exclude_globs):
            continue
        files.append(SourceFile(source_path=source_path, absolute_path=path))

    return files


def parse_source_file(source_file: SourceFile) -> ParsedFile:
    suffix = source_file.absolute_path.suffix.lower()
    if suffix == ".md":
        return parse_markdown_file(source_file.absolute_path, source_file.source_path)
    if suffix == ".txt":
        return parse_plain_text_file(source_file.absolute_path, source_file.source_path)
    raise ValueError(f"Unsupported source extension: {source_file.source_path}")


def build_context(config: VaultConfig) -> VaultContext:
    files = scan_vault(config)
    blocks: list[ParsedBlock] = []
    tasks: list[ParsedTask] = []
    links: list[ParsedLink] = []
    tags: list[ParsedTag] = []
    lines: list[ParsedLine] = []

    for source_file in files:
        parsed = parse_source_file(source_file)
        blocks.extend(parsed.blocks)
        tasks.extend(parsed.tasks)
        links.extend(parsed.links)
        tags.extend(parsed.tags)
        lines.extend(parsed.lines)

    return VaultContext(
        vault_path=validate_vault_path(config.vault_path),
        files=files,
        blocks=blocks,
        tasks=tasks,
        links=links,
        tags=tags,
        lines=lines,
    )
