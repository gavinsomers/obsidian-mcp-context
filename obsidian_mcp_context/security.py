from __future__ import annotations

import os
from pathlib import Path


ALLOWED_ROOTS_ENV = "OBSIDIAN_MCP_ALLOWED_ROOTS"


class VaultPathError(ValueError):
    """Raised when a requested vault path is outside configured allowed roots."""


def configured_allowed_roots(value: str | None = None) -> tuple[Path, ...]:
    raw_value = value if value is not None else os.environ.get(ALLOWED_ROOTS_ENV, "")
    roots = tuple(
        Path(item).expanduser().resolve()
        for item in raw_value.split(",")
        if item.strip()
    )
    return roots


def validate_vault_path(
    vault_path: str | Path,
    allowed_roots: tuple[Path, ...] | None = None,
) -> Path:
    resolved = Path(vault_path).expanduser().resolve()
    roots = configured_allowed_roots() if allowed_roots is None else allowed_roots
    if not roots:
        return resolved
    for root in roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    allowed = ", ".join(str(root) for root in roots)
    raise VaultPathError(
        f"Vault path is outside configured allowed roots: {resolved}. "
        f"Allowed roots: {allowed}"
    )
