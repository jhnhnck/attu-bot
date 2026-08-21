# mkdocs

incorporate mkdocs-material with mkdocstrings into the doom-bot project: restructure `notes/` into `docs/`, configure mkdocs-material as the site generator, and auto-generate API reference pages for all six workspace packages via mkdocstrings.

## goals

1. `mkdocs serve` and `mkdocs build --strict` run cleanly from the project root
2. all developer-facing notes (architecture, config, features, dev guides, style) appear in the nav as polished pages
3. API reference auto-generated from docstrings for all six workspace packages: nova-core, casino-bot, attu-server, attu-models, attu-logging, attu-wiki
4. agent-internal files (bugs.md, to-do.md, plans/) stay on disk but excluded from nav

## non-goals

- hosting or deployment (github pages, internal server)
- adding or improving docstrings (coverage is already excellent)
- migrating agent automation (CLAUDE.md, skills, memory) to different formats

## constraints

- uv workspace; mkdocs deps added to the dev group in root pyproject.toml
- notes/ is referenced throughout CLAUDE.md and agent memory; rename requires grepping .claude/ for all occurrences, not just CLAUDE.md
- docstring style is google convention (ruff pydocstyle config); mkdocstrings must be configured to match
- nova_core uses PEP 562 lazy loading via `__getattr__`; griffe (mkdocstrings' static analyzer) may not handle dynamic exports correctly
- no CI pipeline for mkdocs build - out of scope

## accepted risks

mkdocstrings API pages will surface internal modules not intended as public API. nav controls visibility, but `mkdocs build --strict` still resolves all `:::` directives - configure `show_if_no_docstring: false` and `filters: ["!^_"]` to suppress empties and private members. if griffe cannot resolve nova_core's dynamic exports after 1 hour of investigation, fall back to hand-authored stubs for nova_core only (remaining 5 packages have no dynamic loading).

---

### phase 0 - scaffold and probe

**scope:** rename notes/ → docs/, patch all references across .claude/, add mkdocs deps, write mkdocs.yml, and verify mkdocstrings can import packages via a probe page before phase 1 commits to the full API reference.

- run `grep -r "notes/" .claude/ --include="*.md" -l` to inventory all reference sites; patch them all (CLAUDE.md, memory files, skills, plans)
- rename `notes/` → `docs/` via `git mv`
- add to root `pyproject.toml` dev group: `mkdocs-material`, `mkdocstrings[python]`
- `uv sync`
- write `mkdocs.yml` at project root:
  - `docs_dir: docs`
  - theme: material with dark/light palette toggle
  - nav covering architecture, config-system, features/*, dev/*, style/*
  - exclude from nav: bugs.md, to-do.md, coverage.md, nova-core.md, plans/, .meta.md
  - mkdocstrings plugin configured: google docstring style, `show_if_no_docstring: false`, `filters: ["!^_"]`
- add `docs/api-probe.md` with `:::attu_logging` directive; run `mkdocs build` and verify attu_logging renders with docstrings (smoke test for mkdocstrings import before phase 1)
- remove probe page after smoke test passes

**dod:**
- `uv sync` completes without errors
- `mkdocs serve` starts with no fatal errors; nav matches intended structure in browser
- `notes/` no longer exists; all content in `docs/`; zero remaining `notes/` references in .claude/ (verify with grep)
- probe page `:::attu_logging` renders full docstrings in `mkdocs build` output before being removed

**merge gate:** `mkdocs build --strict` exits 0; grep for `notes/` in .claude/ returns empty; CLAUDE.md diff shows only path updates, no content changed in moved files

---

### phase 1 - api reference

**scope:** create API reference pages in docs/api/ for each workspace package using mkdocstrings directives, wire into nav.

- create `docs/api/` with one .md per package:
  - `nova-core.md` → `:::nova_core` with submodule filtering
  - `attu-models.md` → `:::attu_models`
  - `attu-logging.md` → `:::attu_logging`
  - `attu-wiki.md` → `:::attu_wiki`
  - `attu-server.md` → `:::attu_server`
  - `casino-bot.md` → `:::casino_bot`
- nova_core: use explicit `members` list or submodule-level directives rather than top-level `:::nova_core` to avoid a wall of internal command handlers
- add "api reference" section to mkdocs nav
- pivot criterion: if nova_core's PEP 562 exports produce empty/broken griffe output after 1 hour of debugging, replace `:::nova_core` with hand-authored stubs listing key public classes

**dod:**
- `mkdocs build --strict` exits 0
- all six packages appear in API reference nav
- public classes and functions render with docstrings; spot-check: nova_core.loader.FeatureContext and attu_wiki.client.WikiClient both render

**merge gate:** `mkdocs build --strict` exits 0; spot-check in browser confirms FeatureContext and WikiClient pages with full docstrings

## status

| phase | status |
|---|---|
| 0 - scaffold and probe | in progress |
| 1 - api reference | not started |
