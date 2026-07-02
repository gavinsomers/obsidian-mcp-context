from __future__ import annotations

from pathlib import Path


def test_obsidian_launcher_uses_software_rendering_flags_by_default():
    launcher = Path("docker/obsidian/obsidian-open-vault").read_text(encoding="utf-8")
    compose = Path("docker-compose.analytics.yml").read_text(encoding="utf-8")

    assert "OBSIDIAN_ELECTRON_FLAGS" in launcher
    assert "--disable-gpu" in launcher
    assert "--disable-dev-shm-usage" in launcher
    assert "--ozone-platform=x11" in launcher
    assert "exec obsidian $obsidian_flags \"$vault_path\"" in launcher

    assert "LIBGL_ALWAYS_SOFTWARE" in compose
    assert "OBSIDIAN_ELECTRON_FLAGS" in compose
    assert "--disable-gpu" in compose
