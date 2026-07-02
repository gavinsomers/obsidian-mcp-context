# Vault Profiler

The vault profiler is a read-only command for understanding a vault's aggregate
shape before designing or tuning a vault profile. It is safe for the public demo
workflow because the default report contains counts and distributions, not note
content or source paths.

Run it against the generated demo vault:

```bash
obsidian-mcp-context-profile-vault \
  --vault examples/generated-vaults/large \
  --vault-profile generated-demo
```

Default output:

```text
var/vault-profile-report.json
```

`var/` is ignored. Do not commit profiler reports produced from real notes.

## Main Signals

The report includes aggregate counts by default:

- scanned file counts and source extensions
- folder and inferred note-type distribution
- frontmatter key coverage
- lifecycle timestamp field coverage
- wikilink shape counts
- tag and task counts
- empty and large note counts
- readiness recommendations for profile design

The default report does not include note text, source paths, config paths, or
profile paths.

## Local Samples

For local debugging, path samples can be included explicitly:

```bash
obsidian-mcp-context-profile-vault \
  --vault /path/to/vault \
  --vault-profile /path/to/profile.toml \
  --include-samples \
  --output var/vault-profile-report.json
```

Samples still never include note content. Keep sample-enabled reports under
ignored local paths and do not commit them to the public repo.

The same command is also available through the main CLI:

```bash
obsidian-mcp-context \
  --vault examples/generated-vaults/large \
  --vault-profile generated-demo \
  profile-vault
```
