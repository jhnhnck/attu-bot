# pre-mortem - mkdocs

**bottom line:** proceed with revisions

### risks

- [high] integration - mkdocstrings needs to import all 6 workspace packages at build time; nova_core pulls discord.py, motor, beanie; if `uv run mkdocs build` doesn't see them the build fails completely · probe: phase 0 probe page `:::attu_logging` verifies the import chain works before phase 1 commits to full API reference
- [medium] dependency - nova_core uses PEP 562 `__getattr__` in `__init__.py` for circular import resolution; griffe (mkdocstrings' static analyzer) may produce empty or broken output for dynamically-exported symbols · probe: inspect griffe output for nova_core early in phase 1; fall back to submodule-level directives if top-level fails
- [medium] premise - plan originally identified only CLAUDE.md and memory as referencing `notes/`; `.claude/skills/` and `.claude/plans/` also contain references · probe: `grep -r "notes/" .claude/ --include="*.md" -l` before any rename; patch all sites
- [medium] scope - `:::nova_core` at top level will produce an unusable wall of text from ~20 subpackages including all command handlers · probe: use explicit submodule-level directives or `members` filtering for nova_core in phase 1
- [low] dependency - mkdocs.yml nav lists specific files; any file listed that doesn't exist causes `mkdocs build --strict` to fail · probe: cross-reference nav entries against actual docs/ file list before build

### walking-skeleton check

phase 0 as originally written built a mkdocs site with zero mkdocstrings content, leaving the key integration unknown (can the tool import the packages?) until phase 1. revised: phase 0 now includes an `:::attu_logging` probe page that must render successfully before the probe page is removed and the phase closes. this makes phase 0 the thinnest end-to-end slice touching every layer the project will use.

### phase-order revisions

| original | proposed | reason |
|---|---|---|
| no change | no change | phase 0 (scaffold) before phase 1 (api reference) is correct risk-first ordering; the integration probe added to phase 0 retires the highest-severity unknown before phase 1 begins |

### definition-of-done additions

- phase 0 - add: probe page `:::attu_logging` renders full docstrings in `mkdocs build` output (smoke test for mkdocstrings import chain)
- phase 0 - add: grep for `notes/` in .claude/ returns empty after rename
- phase 1 - add pivot criterion: if nova_core PEP 562 exports fail griffe after 1 hour, fall back to hand-authored stubs for nova_core only
