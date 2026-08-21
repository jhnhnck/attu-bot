# log - mkdocs

## starting phase 0 — 2026-08-21

- worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/mkdocs
- branch: phase/mkdocs
- parent: trunk
- dod: uv sync clean; mkdocs serve starts; notes/ gone, docs/ has all content; zero notes/ refs in .claude/; attu_logging probe page renders docstrings

## phase 0 retro — 2026-08-21

### what landed vs spec

- notes/ renamed to docs/ via git mv; all six reference sites in .claude/ patched (CLAUDE.md, memory files, plans)
- mkdocs-material and mkdocstrings[python] added to root pyproject.toml dev group; uv sync clean
- mkdocs.yml written with material theme, dark/light toggle, nav covering all developer pages; strict build exits 0 in 0.47s
- probe page added and run; revealed attu_logging import failure (see residual debt); removed after confirming the diagnostic
- stale agents.md link in nova-core.md (pre-existing) surfaced by strict build; fixed in 8039757

intentional scope narrowing: probe page could not render attu_logging docstrings (import failed), so the dod line "renders full docstrings" was interpreted as "probe ran and surfaced the failure" — confirmed by caller as met.

### what surprised us

- all six workspace packages have `package = false` in their pyproject.toml; uv does not install any of them into the venv; mkdocstrings relies on python import machinery, so it cannot resolve any of the six packages without an explicit `paths:` override in mkdocs.yml — the attu_logging probe revealed this, but the same issue affects all six (implementer note)
- bugs were written to docs/bugs.md (project bug log) rather than .claude/plans/mkdocs/bugs.md (plan bug log); carried into plan bugs.md for triage

### what residual debt remains

- mkdocstrings `paths:` config not yet set; all six packages unresolvable until fixed in phase 1
- pre-existing ruff issues in events.py (S108, RUF103, PLR0915) — not introduced by this phase; deferred

## revision after phase 0 — 2026-08-21

- phase 0: status closed in 8039757
- phase 1: scope updated — prepend step: configure mkdocstrings `paths:` in mkdocs.yml pointing to all six package source dirs before creating api/ pages; blocker prerequisite surfaced by phase 0 probe
