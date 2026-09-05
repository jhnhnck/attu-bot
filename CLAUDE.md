# AttuBot / Doom Bot

Additional docs are in `docs/` (architecture in `docs/architecture.md`, config system in `docs/config-system.md`, style guides in `docs/style/`, feature specs in `docs/features/`; backlog in `docs/to-do.md`, bug log in `docs/bugs.md`, active plans in `.claude/plans/`).

## rules

1. do not edit the rules.
1. do not perform any interactions with Discord without asking.
1. do not push or deploy without being explicitly asked to.
1. all noqa comments must include a valid reason.

## must report

report immediately and stop; do not diverge down less optimal paths.

1. a tool or app is missing, misconfigured, or malfunctioning.
1. an unrelated bug surfaces during the current task.
1. a file appears moved or deleted unexpectedly.
1. a build error occurs.

## completion checklist

walk this before reporting any feature, fix, or refactor as done, and before drafting a commit message. answer each as a literal yes/no; finish any applicable item that is no. the `feature-completion` skill holds the full version with rationale.

- **tests** - unit tests for new logic in `tests/python/unit/`; component tests for new repository methods or DB operations in `tests/python/component/`; full suite green via `uv run python scripts/run_tests.py`
- **mock compensation** - a new file under `nova_core/commands/` keeps `TestExtensionImports.test_extension_imports_cleanly` passing; a new `@commands.check` predicate gets a predicate test
- **new migration** - has a rollback path test before merging
- **new config field** - has a roundtrip test that saves a non-default value, reloads via `load_guild()`, and asserts it survives
- **tier-3 config field** - all three plumbing steps done (`GuildConfigDocument`, runtime `GuildConfig`, and passed explicitly in `NovaConfig.load_guild()`); missing any one silently uses the default in production. if it gates a feature, add it to `_FEATURE_FIELDS`
- **admin api** - every mutation calls `bridge.trigger_reload(...)` (plus `bridge.invalidate_guild_cache()` for guild config); snowflakes serialized as strings; new route registered under the `/admin` router; unit tests added
- **docs** - feature spec in `docs/features/` updated with a bumped `last_updated`; `README.md` and `docs/architecture.md` tables updated for new slash commands or admin routes; `docs/to-do.md` and `docs/bugs.md` updated per the `to-do` skill
- **lint** - `uv run ruff check .` and `uv run ruff format --check .` clean for touched files; every `noqa` has a reason (rule #4); no em-dashes in the diff
- **final gate** - nothing pushed or deployed without explicit instruction (rule #3); local commits inside a worktree branch are fine

## sub-agents

when operating as a sub-agent (spawned via the agent tool), assume other agents may be working concurrently in the same repository:

- **work off the `trunk` branch** - the main checkout lives at `/home/jhn/Projects/doom-bot`; when isolated in a worktree, ensure it is based on `trunk`, not `prod`
- do not run git operations that modify shared state (`checkout`, `reset`, `merge`, `rebase`, `stash`) unless isolated in a worktree
- do not assume exclusive access to any file or the working directory
- prefer additive changes; avoid deleting or overwriting files without checking for concurrent edits
- if isolated git work is needed, use a worktree (`EnterWorktree`) rather than modifying the main tree
- **tests are allowed** - run them from the venv, in your own worktree: `uv run python scripts/run_tests.py`. component suites need a reachable mongo and `TEST_DB_URL`
- **do not run docker commands** - never invoke `docker`, `docker compose`, or any container tooling; ask the main agent to bring up `mongo` if a component suite needs it

## pitfalls

- **config singletons**: `bot`, `config`, and `db` are defined in `apps/bot/nova_core/client/core.py`; always import from `nova_core.client.core` directly - `nova_core/__init__.py` does not re-export these; tests that use `patch.object(nova_core, 'bot', ...)` fail silently
- **permission checks**: use `@commands.check(predicate)` from `discord.ext.commands`, not `@discord.commands.check()` - that does not exist in pycord; all command modules use `from discord.ext import commands`
- **rollover storage**: stored as `rollover_minutes` (int, minutes since midnight) in MongoDB; the legacy string format `"17:00"` is handled by a `model_validator` in `GuildEpoch`
- **snowflake precision**: Discord IDs exceed JavaScript's safe integer range - serialize as strings in any JSON API response
- **guild authorization**: always check `guild_id in config.authorized_guilds` before acting; `config.guild(id)` raises `UnauthorizedGuild` for unknown guilds
- **`resvg` dependency**: the bot checks for `/usr/local/bin/resvg` at startup and exits if missing - it is bundled in the Docker image only
- **`TEST_MODE` env var**: when set, the bot exits cleanly after reaching ready state without a 60-second restart delay; migrations are also skipped
- **`wip/` directory**: excluded from all linting and type checks; use it for exploratory or in-progress work

## personality

- use semicolons or regular dashes (-); never em-dashes
  - semicolon: joins two independent clauses or a cause and consequence (`"migration failed; refusing to continue"`)
  - dash: trailing aside, parenthetical, or annotation
- do not include any extraneous punctuation
- write code comments in all lowercase including at the beginning of sentences, except where it would be unclear; prefer to be brief
- use american english spelling and grammar
- use spaces for indentation always; avoid formats that require tabs
- prefer brief statements over long explanations
