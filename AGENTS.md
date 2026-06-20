# Project Rules

## Release And Changelog

- Shipped changes must not stay only under `## Unreleased`. Before commit or push, move them into a dated section: `## X.Y.Z - YYYY-MM-DD`.
- When a release section is added, keep release metadata aligned in `pyproject.toml`, `uv.lock`, `src/pyaireader/mcp/server.py`, and `docs/registry-server-json-candidate.json`.
- Do not edit old planning examples just because they mention an older version.
- Before reporting release work as complete, run:
  - `uv lock` if `pyproject.toml` version changed
  - `uv run python -c "from importlib.metadata import version; print(version('pyaireader'))"`
  - `git diff --check`
