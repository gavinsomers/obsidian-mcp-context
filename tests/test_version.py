import tomllib
from pathlib import Path

from obsidian_mcp_context import __version__


def test_package_version_matches_project_metadata():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert __version__ == pyproject["project"]["version"]
