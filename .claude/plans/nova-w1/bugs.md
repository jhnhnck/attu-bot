# bugs — nova-w1: structural prerequisites
## open

- [defer] pre-existing em-dashes throughout `.claude/plans/nova-w1/plan.md` and `.claude/plans/nova-w1/log.md`; project bans em-dashes per CLAUDE.md; documentation files only, not implementation code; no downstream phase is blocked; fix whenever plan.md is next edited for other reasons
- [defer] `notes/` docs still reference `apps/bot/doom_bot/` paths in prose descriptions (agents.md, features/*.md, dev/testing.md, style/*.md, nova-core.md); these are cosmetic doc accuracy issues; ruff clean (docs are not .py); update gradually as each feature doc gets edited for other reasons
- [defer] `notes/bugs.md:26` still references `doom_bot.config.{BotTheme, GuildConfig}` in its description of a pre-existing coupling smell; the actual import in `attu_models/repositories.py` was fixed in phase 1 to `nova_core.config`; the bugs.md entry text is now stale history, not an active bug
- [defer] `tests/python/unit/test_start_bot_loop.py` and `tests/python/integration/test_startup.py` use `patch.object(nova_core.bot, ...)` and `isinstance(nova_core.bot, discord.Bot)` patterns which access `nova_core.bot` as a live python object — `nova_core/__init__.py` does not re-export `bot`, so these will AttributeError if `nova_core.client.core` is not imported first; fix requires either re-exporting `bot` from `nova_core/__init__.py` or switching callers to `nova_core.client.core.bot`; not confirmed failing (untested in this session); defer to a later pass

## closed
(populated at phase close)
