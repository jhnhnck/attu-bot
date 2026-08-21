---
name: docker-commands
description: canonical docker compose commands and scripts/ wrapper reference for AttuBot's dev and prod stacks - which compose file to use, what each script wraps, build stages, and the gotchas around the tests profile, the seed restore, and the symlinked docker-compose.yml. trigger when the user asks to "run tests", "build", "rebuild containers", "deploy", "bring up the stack", "restore from backup", "refresh the seed", or "migrate the server"; when the user mentions `docker compose`, `docker-compose.dev.yml`, `docker-compose.prod.yml`, the `tests` profile, the `tester` or `doombox` build target, or any of the docker-wrapper scripts (`run_tests.py`, `deploy.py`, `restore.sh`, `migrate_server.zsh`, `create_dev_seed.sh`, `ferret_init.sh`); when answering questions about which compose file is canonical, why `--profile tests` is or isn't needed, or what stage of the Dockerfile a service uses. canonical source for command form - if a doc disagrees with this skill, the skill wins. for log-reading recipes (`docker compose logs`, `journalctl`, structlog parsing) use `container-logs` instead.
---

# docker-commands

reference card for docker tasks in this repo. one canonical command per task; one paragraph per script. for log-reading work see the `container-logs` skill.

## stacks at a glance

| stack | working dir | compose file | project name | services |
|---|---|---|---|---|
| **dev** (default for tests, web hand-runs) | `/srv/services/doom-bot-dev` | `docker-compose.dev.yml` | `doom-bot-dev` | `ferret`, `postgres`, `ferret-init` (one-shot seeder), `legacy-web`, `tests` (profile-gated) |
| **prod** | `/srv/services/doom-bot` | `docker-compose.prod.yml` | `doom-bot` | `core`, `legacy-web`, `ferret`, `postgres`, `tests` (profile-gated) |
| **chat** (dormant) | included from a parent stack | `apps/chat/compose.yml` | `doom-bot-chat` | `ingestor`, `qdrant`, `llama-server` |

`docker-compose.yml` in each working dir is a symlink to its `*.dev.yml` / `*.prod.yml` sibling. `-f <file>` is still preferred in scripts and docs because it makes the target stack explicit and works the same from either worktree. inside a worktree, the bare form (no `-f`) also works.

dev postgres uses `tmpfs` for its data dir, so every dev start is from-scratch. prod uses an external named volume `doom-bot_postgres_data`.

## canonical commands

| task | command |
|---|---|
| run tests (dev) | `docker compose -f docker-compose.dev.yml run --build --rm --quiet-build tests` |
| run tests with args | `docker compose -f docker-compose.dev.yml run --build --rm --quiet-build tests scripts/run_tests.py --coverage -x` |
| run tests via host wrapper | `python scripts/run_tests.py [args]` (recurses into docker for you) |
| dev legacy web | `docker compose -f docker-compose.dev.yml up --build legacy-web` (binds `127.0.1.8:8080`) |
| build dev images only | `docker compose -f docker-compose.dev.yml build` |
| bring up prod | `docker compose -f docker-compose.prod.yml up --build -d` |
| build prod images only | `docker compose -f docker-compose.prod.yml build` |
| stop prod (for restore/maintenance) | `docker compose -f docker-compose.prod.yml stop core legacy-web` |
| deploy (bump + tag + merge + push) | `python scripts/deploy.py minor --deploy` |
| revert to a prior tag | `python scripts/deploy.py --revert <tag>` |
| restore prod from backup | `bash scripts/restore.sh /srv/backups/attu-bot/<ts>.tar.bz2` (run from prod dir) |
| refresh dev seed | `bash scripts/create_dev_seed.sh /srv/backups/attu-bot/<ts>.tar.bz2` |
| migrate prod to new host | `scripts/migrate_server.zsh [--ssh-user U] [--target-dir D] TARGET_HOST` |
| read prod logs | see the `container-logs` skill — `docker compose logs`, `journalctl`, structlog parsing |

`--quiet-build` is part of the canonical test form because every script-driven invocation already uses it; matching it everywhere keeps cold-cache rebuild output noise out of the way. `--profile tests` is **not** required: `docker compose run <svc>` auto-activates a profiled service. it is only needed if you ever say `up tests` (which is unusual — tests is one-shot, not long-running).

## scripts/ wrappers

| script | purpose |
|---|---|
| `scripts/run_tests.py` | three-suite orchestrator (pytest unit/component/integration + vitest). when invoked from the host, shells out to `docker compose run … tests` itself and forwards `^C`. flags: `-v`, `-x`, `--coverage`, `--coverage-json`. |
| `scripts/deploy.py` | bump-merge-deploy orchestrator. `bump` (`minor`\|`patch`), `--deploy`, `--revert TAG`, `--no-tests`, `--dry-run`. requires being on `dev`; merges fast-forward into trunk, tags, runs prod tests, restarts containers, 60s sleep, health-checks, then pushes. has rollback paths for most failure points. |
| `scripts/coverage_report.py` | renders a `coverage.json` payload as the markdown coverage section in `docs/to-do.md`. pure formatter; reads stdin or path. `--threshold` for ci gating. |
| `scripts/ferret_init.sh` | runs *inside* the dev `ferret-init` service. waits for ferret on tcp 27017, then `mongorestore`s the seed at `/tmp/seeds/doombot-seed/` excluding heavy/test collections. not invoked directly. |
| `scripts/create_dev_seed.sh` | host script. extracts a `.tar.bz2` prod backup, strips heavy collections (`messages`, `chat_sources`, `families`, `chat_characters`, `test_*_messages`), and stages the result at `apps/bot/assets/doombot-seed/` for `ferret-init` to pick up next dev start. |
| `scripts/restore.sh` | prod-side restore. confirms with the operator, extracts the archive into `/srv/backups/attu-bot/.restore-tmp`, then `docker compose exec core mongorestore --drop`. **stop `core` and `legacy-web` first.** |
| `scripts/migrate_server.zsh` | one-shot prod-host migration. stops services, dumps `${PROJECT}_postgres_data`, rsyncs to the target, recreates the volume there, patches the target's `docker-compose.prod.yml` to mark `postgres_data` `external`, and brings the stack up. has `--dry-run`. |

## build stages

single dockerfile at `apps/bot/Dockerfile`, four stages:

| stage | base | purpose | used by |
|---|---|---|---|
| `builder` | `rust:bookworm` | `cargo install resvg` for the svg converter binary | copied into `doombox` |
| `git-info` | `alpine:3.21` | sed-stamps `__version__` (suffixes `-${SHORT_SHA}`) and `__build_time__` into `apps/bot/doom_bot/__init__.py` | copied into `doombox` |
| `doombox` | `uv:python3.13-trixie-slim` | production runtime — system deps, mongodb-database-tools, `resvg`, `uv sync --no-dev`, app code, version stamp | prod `core`, prod+dev `legacy-web` |
| `tester` | `FROM doombox` | adds nodejs, copies `tests/`, `scripts/`, vitest/eslint configs, runs `uv sync` (with dev deps) and `npm install`. cmd: `python /home/doom/scripts/run_tests.py` | dev+prod `tests` |

`apps/chat/Dockerfile` is the dormant chat container; mirrors the bot Dockerfile and is built only when `apps/chat/compose.yml` is included from a parent stack.

workspace shape: root `pyproject.toml` declares a uv workspace over `apps/bot`, `apps/chat`, `apps/server`, `packages/shared-models`. all four manifests are copied into the image so `uv sync` resolves, even though `apps/chat/` body content is excluded by `.dockerignore` (the manifest is whitelisted with `!apps/chat/pyproject.toml`).

## gotchas

- **`tests` skips the seed.** in dev, the `tests` service depends on `ferret` (not `ferret-init`) by design — tests create their own data and would only be slowed down by waiting for the seed restore. if a test newly needs seed data, that is a test-design issue, not a compose issue.
- **`--profile tests` is not needed for `run`.** `docker compose run tests` auto-activates the profile for that one invocation. only `up` needs `--profile tests`.
- **prod `core` healthcheck reads `/tmp/bot-ready`.** the file is written from `apps/bot/doom_bot/client/events.py:_READY_SENTINEL` once the bot reaches ready state. if the prod container is reported unhealthy after a deploy, that is the file to check.
- **`docker-compose.yml` is a symlink, not a separate stack.** dev dir → `docker-compose.dev.yml`; prod dir → `docker-compose.prod.yml`. the symlink is convenience for interactive use; scripts and docs prefer `-f <file>` for clarity.
- **mongodb-database-tools and node 22 are pinned to literal versions** in `apps/bot/Dockerfile` (lines 49 and 88; both flagged "repeat TODO" in the file). when bumping either, update both occurrences (one in each `RUN` block).
- **never `git push --force` to `main`/`trunk` outside of `scripts/deploy.py --revert`** — that path force-pushes after a clean reset and is the only sanctioned way.

## anti-patterns

- bare `docker compose run tests` from the prod worktree: works, but only because the symlink coincidentally points to dev. always use `-f docker-compose.dev.yml` when running tests from prod (this is what `scripts/deploy.py` does).
- `docker compose -f docker-compose.dev.yml --profile tests run --build --rm tests` (the older form in some notes): redundant `--profile`, missing `--quiet-build`. use the canonical form above.
- `docker compose run … tests scripts/run_tests.py` with no extra args: redundant — that's already the container `CMD`. only append `scripts/run_tests.py` when you also pass flags to it.
- editing `docker-compose.yml` directly: it is a symlink. edit `*.dev.yml` or `*.prod.yml` instead.
