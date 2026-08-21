# bugs - mkdocs

## open

- mkdocstrings cannot resolve any of the six workspace packages — all have `package = false` in pyproject.toml so uv does not install them into the venv; mkdocstrings uses python import machinery and raises ModuleNotFoundError; fix: add `paths:` to mkdocstrings handler config in mkdocs.yml pointing to all six source dirs (apps/bot, apps/server, apps/casino, packages/shared-models, packages/attu-logging, packages/attu-wiki) — **fix-in-phase-1** (blocker for api reference)

## closed

- stale agents.md link in docs/nova-core.md — pre-existing link to agents.md (renamed to architecture.md); fixed in 8039757
