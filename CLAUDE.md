# AttuBot / Doom Bot

Additional docs are in `notes/` (architecture in `notes/architecture.md`, config system in `notes/config-system.md`, style guides in `notes/style/`, feature specs in `notes/features/`, dev guides in `notes/dev/`).

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

## sub-agents

when operating as a sub-agent (spawned via the agent tool), assume other agents may be working concurrently in the same repository:

- **work off the `trunk` branch** - the main checkout lives at `/home/jhn/Projects/doom-bot`; when isolated in a worktree, ensure it is based on `trunk`, not `prod`
- do not run git operations that modify shared state (`checkout`, `reset`, `merge`, `rebase`, `stash`) unless isolated in a worktree
- do not assume exclusive access to any file or the working directory
- prefer additive changes; avoid deleting or overwriting files without checking for concurrent edits
- if isolated git work is needed, use a worktree (`EnterWorktree`) rather than modifying the main tree
- **do not run tests** - never invoke `pytest`, `docker compose run ... tests`, `npm test`, or any test runner; testing is the responsibility of the main agent only
- **do not run docker commands** - never invoke `docker`, `docker compose`, or any container tooling

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
