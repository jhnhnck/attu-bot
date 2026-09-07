---
name: docker-commands
description: canonical docker compose commands and scripts/ wrapper reference for AttuBot's dev and prod stacks - which compose file to use, what each script wraps, build stages, and the gotchas around the tests profile and the seed restore. trigger when the user asks to "run tests", "build", "rebuild containers", "deploy", "bring up the stack", "restore from backup", "refresh the seed", or "migrate the server"; when the user mentions `docker compose`, `docker-compose.dev.yml`, `docker-compose.prod.yml`, the `tests` profile, the `tester` or `doombox` build target, or any of the docker-wrapper scripts (`run_tests.py`, `deploy.py`, `restore.sh`, `migrate_server.zsh`, `create_dev_seed.sh`, `ferret_init.sh`); when answering questions about which compose file is canonical, why `--profile tests` is or isn't needed, or what stage of the Dockerfile a service uses. canonical source for command form - if a doc disagrees with this skill, the skill wins. for log-reading recipes (`docker compose logs`, `journalctl`, structlog parsing) use `container-logs` instead.
---

# docker-commands

reference card for docker tasks in this repo. one canonical command per task; one paragraph per script. for log-reading work see the `container-logs` skill.

## stacks at a glance

| stack | working dir | compose file | project name | services |
|---|---|---|---|---|
| **dev** (tests, local db) | `/home/jhn/Projects/doom-bot` | `docker-compose.dev.yml` | `doom-bot-dev` | `ferret`, `postgres`, `mongo`, `ferret-init` (one-shot seeder), `tests` (profile-gated) |
| **prod** | `/srv/services/doom-bot` | `docker-compose.prod.yml` | `doom-bot` | `core`, `server`, `ferret`, `postgres`, `tests` (profile-gated) |

there is **no committed `docker-compose.yml`**; the name is gitignored and any local copy is a personal symlink. always pass `-f docker-compose.dev.yml` or `-f docker-compose.prod.yml`, in scripts, in docs, and by hand. the dev stack has no bot service at all, so a bare `docker compose up` in the dev checkout would not start the bot even if it resolved.

the dev stack also carries a standalone `mongo` service used by venv test runs (`TEST_DB_URL=mongodb://localhost:27017/doombot`). it has two workarounds baked in, a `GLIBC_TUNABLES` rseq override and a raised `nofile` ulimit; read the comments on the service before changing it.

dev postgres uses `tmpfs` for its data dir, so every dev start is from-scratch. prod uses an external named volume `doom-bot_postgres_data`.

## canonical commands

| task | command |
|---|---|
| run tests (primary path) | `uv run python scripts/run_tests.py [args]` - all three suites |
| dev mongo for venv tests | `docker compose -f docker-compose.dev.yml up -d mongo` (then `TEST_DB_URL=mongodb://localhost:27017/doombot`) |
| run tests in docker (unit + component only) | `docker compose -f docker-compose.dev.yml run --build --rm --quiet-build tests` |
| run tests in docker with args | `docker compose -f docker-compose.dev.yml run --build --rm --quiet-build tests scripts/run_tests.py --coverage -x` |
| build dev images only | `docker compose -f docker-compose.dev.yml build` |
| bring up prod | `docker compose -f docker-compose.prod.yml up --build -d` |
| build prod images only | `docker compose -f docker-compose.prod.yml build` |
| stop prod (for restore/maintenance) | `docker compose -f docker-compose.prod.yml stop core server` |
| deploy (bump + tag + merge + push) | `python scripts/deploy.py minor --deploy` |
| snapshot the live config for the running tag | `python scripts/deploy.py --snapshot-config <tag>` |
| revert to a prior tag | `python scripts/deploy.py --revert <tag>` |
| restore prod from backup | `bash scripts/restore.sh /srv/backups/attu-bot/<ts>.tar.bz2` (run from prod dir) |
| refresh dev seed | `bash scripts/create_dev_seed.sh /srv/backups/attu-bot/<ts>.tar.bz2` |
| migrate prod to new host | `scripts/migrate_server.zsh [--ssh-user U] [--target-dir D] TARGET_HOST` |
| read prod logs | see the `container-logs` skill — `docker compose logs`, `journalctl`, structlog parsing |

the venv path is primary: `run_tests.py` runs the suites in the current interpreter and no longer relaunches itself into docker. the docker `tests` service is **unit and component only** - it mounts no `.secrets` and sets no `ATTU_CONFIG_FILE`, so integration tests cannot find a config file there and fail on `config.on_init()`. it does set `TEST_DB_URL` at the dev `ferret` service, so db-backed component tests work.

`--quiet-build` is part of the canonical docker test form because every script-driven invocation already uses it; matching it everywhere keeps cold-cache rebuild output noise out of the way. `--profile tests` is **not** required: `docker compose run <svc>` auto-activates a profiled service. it is only needed if you ever say `up tests` (unusual; tests is one-shot, not long-running).

## scripts/ wrappers

| script | purpose |
|---|---|
| `scripts/run_tests.py` | three-suite pytest orchestrator (unit, component, integration). runs the suites directly in the current interpreter's venv; it no longer relaunches itself into docker. flags: `-v`, `-x`, `--coverage`, `--coverage-json`. |
| `scripts/deploy.py` | bump-merge-deploy orchestrator. `bump` (`minor`\|`patch`), `--deploy`, `--revert TAG`, `--snapshot-config TAG`, `--force`, `--no-tests`, `--dry-run`. requires being on `trunk`; merges fast-forward into `prod`, tags, runs prod tests, restarts containers, 60s sleep, health-checks, then pushes. has rollback paths for most failure points. **config snapshots**: the live `.secrets/attu-bot.toml` is gitignored, so reverting code across a `__config_version__` change would otherwise leave the old image facing a config it cannot parse. a deploy saves the config as `attu-bot.toml.<tag>`, and `--revert` restores that tag's copy, aborting if it is missing (`--force` overrides). capture the current version's config with `--snapshot-config <tag>` **before** migrating it forward. |
| `scripts/coverage_report.py` | renders a `coverage.json` payload as the markdown coverage section in `docs/to-do.md`. pure formatter; reads stdin or path. `--threshold` for ci gating. |
| `scripts/ferret_init.sh` | runs *inside* the dev `ferret-init` service. waits for ferret on tcp 27017, then `mongorestore`s the seed at `/tmp/seeds/doombot-seed/` excluding heavy/test collections. not invoked directly. |
| `scripts/create_dev_seed.sh` | host script. extracts a `.tar.bz2` prod backup, strips heavy collections (`messages`, `chat_sources`, `families`, `chat_characters`, `test_*_messages`), and stages the result at `apps/bot/assets/doombot-seed/` for `ferret-init` to pick up next dev start. |
| `scripts/restore.sh` | prod-side restore. confirms with the operator, extracts the archive into `/srv/backups/attu-bot/.restore-tmp`, then `docker compose exec core mongorestore --drop`. **stop `core` and `server` first.** |
| `scripts/migrate_server.zsh` | one-shot prod-host migration. stops services, dumps `${PROJECT}_postgres_data`, rsyncs to the target, recreates the volume there, patches the target's `docker-compose.prod.yml` to mark `postgres_data` `external`, and brings the stack up. has `--dry-run`. |

## build stages

single dockerfile at `apps/bot/Dockerfile`, four stages:

| stage | base | purpose | used by |
|---|---|---|---|
| `builder` | `rust:bookworm` | `cargo install resvg` for the svg converter binary | copied into `doombox` |
| `git-info` | `alpine:3.21` | sed-stamps `__version__` (suffixes `-${SHORT_SHA}`) and `__build_time__` into `apps/bot/nova_core/__init__.py` | copied into `doombox` |
| `doombox` | `uv:python3.13-trixie-slim` | production runtime - system deps, mongodb-database-tools, `resvg`, `uv sync --no-dev`, app code, version stamp | prod `core` |
| `tester` | `FROM doombox` | copies `tests/`, `scripts/`, and `apps/server/attu_server`, chmods the scripts, runs `uv sync` with dev deps. cmd: `python /home/doom/scripts/run_tests.py` | dev+prod `tests` |

the server image is separate: `apps/server/Dockerfile`, single `server` stage, used by prod `server`.

workspace shape: root `pyproject.toml` declares a uv workspace over `apps/bot`, `apps/server`, `packages/shared-models`, `packages/attu-logging`, and `packages/attu-wiki`. every member manifest is copied into the image so `uv sync` resolves.

## gotchas

- **the docker `tests` service cannot run integration tests.** no `.secrets` mount and no `ATTU_CONFIG_FILE` since `36f6fee` (2026-08-02); `TEST_DB_URL` covers unit and component only. run integration tests from the venv, or mount `.secrets` read-only into that service. tracked in `docs/bugs.md`.
- **`tests` skips the seed.** in dev, the `tests` service depends on `ferret` (not `ferret-init`) by design — tests create their own data and would only be slowed down by waiting for the seed restore. if a test newly needs seed data, that is a test-design issue, not a compose issue.
- **`--profile tests` is not needed for `run`.** `docker compose run tests` auto-activates the profile for that one invocation. only `up` needs `--profile tests`.
- **prod `core` healthcheck reads `/tmp/bot-ready`.** the file is written from `apps/bot/nova_core/client/events.py:_READY_SENTINEL` once the bot reaches ready state. if the prod container is reported unhealthy after a deploy, that is the file to check.
- **mongodb-database-tools is pinned to a literal version** in `apps/bot/Dockerfile`. check for other pinned occurrences in the file when bumping it.
- **never `git push --force` to `main`/`trunk` outside of `scripts/deploy.py --revert`** — that path force-pushes after a clean reset and is the only sanctioned way.

## anti-patterns

- bare `docker compose run tests` anywhere: there is no default compose file to resolve. always use `-f docker-compose.dev.yml` (this is what `scripts/deploy.py` does).
- `docker compose -f docker-compose.dev.yml --profile tests run --build --rm tests` (the older form in some notes): redundant `--profile`, missing `--quiet-build`. use the canonical form above.
- `docker compose run … tests scripts/run_tests.py` with no extra args: redundant — that's already the container `CMD`. only append `scripts/run_tests.py` when you also pass flags to it.
- editing a local `docker-compose.yml`: it is gitignored and at best a symlink. edit `*.dev.yml` or `*.prod.yml` instead, and only in `/home/jhn/Projects/doom-bot` (the prod worktree is read-only).
