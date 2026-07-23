# bugs — nova-w1: structural prerequisites
## open

- [defer] `notes/` docs still reference `apps/bot/doom_bot/` paths in prose descriptions (agents.md, features/*.md, dev/testing.md, style/*.md, nova-core.md); these are cosmetic doc accuracy issues; ruff clean (docs are not .py); update gradually as each feature doc gets edited for other reasons
- [defer] `notes/bugs.md:26` still references `doom_bot.config.{BotTheme, GuildConfig}` in its description of a pre-existing coupling smell; the actual import in `attu_models/repositories.py` was fixed in phase 1 to `nova_core.config`; the bugs.md entry text is now stale history, not an active bug
- [defer] `tests/python/unit/test_start_bot_loop.py` and `tests/python/integration/test_startup.py` use `patch.object(nova_core.bot, ...)` and `isinstance(nova_core.bot, discord.Bot)` patterns which access `nova_core.bot` as a live python object; `nova_core/__init__.py` does not re-export `bot`; confirmed still present after phase 1 (cab68f3 fixed the same pattern in test_commands_stars, test_messages, test_starboard but not these two files); in pre-existing unit/integration baseline, not blocking component tests; fix requires switching callers to `nova_core.client.core.bot`; defer to a later pass

## closed
- em-dashes throughout `plan.md` and `log.md`; fixed in phase 1 close pass (plan.md edited for plan-revise, triggering the deferred condition)
