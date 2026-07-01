# Releasing

This project uses hand-maintained release notes and git tags.

## Version Policy

Use semantic-ish versions:

- Major: incompatible parser, warehouse, CLI, or MCP contract changes.
- Minor: new tools, schema additions, or substantial synthetic dataset expansions.
- Patch: bug fixes, documentation, tests, and small data corrections.

Keep these files in sync for each release:

- `pyproject.toml`
- `obsidian_mcp_context/__init__.py`
- `CHANGELOG.md`

## Release Checklist

For `v1.0.0`, complete the readiness checklist in
[`docs/v1-release-readiness.md`](docs/v1-release-readiness.md) before tagging.

1. Update the version in `pyproject.toml`.
2. Update `__version__` in `obsidian_mcp_context/__init__.py`.
3. Add a new top entry to `CHANGELOG.md`.
4. Run checks:

   ```bash
   .venv/bin/python -m pytest
   .venv/bin/python -m compileall obsidian_mcp_context
   ```

5. For changes touching MCP tools or warehouse behavior, run a live stdio smoke test against the synthetic vault.
6. Open a pull request and merge to `main`.
7. After merge, tag the release from an up-to-date `main`:

   ```bash
   git switch main
   git pull --ff-only
   git tag -a v0.3.0 -m "v0.3.0"
   git push origin v0.3.0
   ```

8. Optionally create a GitHub Release:

   ```bash
   gh release create v0.3.0 \
     --title "v0.3.0" \
     --notes-file CHANGELOG.md
   ```

Do not tag releases from feature branches. Tags should point at commits on `main`.
