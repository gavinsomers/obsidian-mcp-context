from pathlib import Path
import subprocess


def test_local_privacy_files_are_ignored_by_git():
    result = subprocess.run(
        [
            "git",
            "check-ignore",
            ".env.analytics",
            ".obsidian-mcp-context.toml",
            ".privacy-banned-terms.local",
            "var/replay-vault/.obsidian-mcp-replay-state.json",
            "logs/synthetic-demo/replay.log",
            "target/manifest.json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    ignored = set(result.stdout.splitlines())
    assert ".env.analytics" in ignored
    assert ".obsidian-mcp-context.toml" in ignored
    assert ".privacy-banned-terms.local" in ignored
    assert "var/replay-vault/.obsidian-mcp-replay-state.json" in ignored
    assert "logs/synthetic-demo/replay.log" in ignored
    assert "target/manifest.json" in ignored


def test_demo_privacy_doc_exists():
    path = Path("docs/demo-privacy-readiness.md")

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "generated/synthetic vaults only" in text
    assert "Gavin's personal Obsidian vault is out of scope" in text
