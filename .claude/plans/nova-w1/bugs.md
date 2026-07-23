# bugs — nova-w1: structural prerequisites
## open

- [defer] pre-existing em-dashes throughout `.claude/plans/nova-w1/plan.md` and `.claude/plans/nova-w1/log.md`; project bans em-dashes per CLAUDE.md; documentation files only, not implementation code; no downstream phase is blocked; fix whenever plan.md is next edited for other reasons
- [defer] `notes/` docs still reference `apps/bot/doom_bot/` paths in prose descriptions (agents.md, features/*.md, dev/testing.md, style/*.md, nova-core.md); these are cosmetic doc accuracy issues; ruff clean (docs are not .py); update gradually as each feature doc gets edited for other reasons
- [defer] `notes/bugs.md:26` still references `doom_bot.config.{BotTheme, GuildConfig}` in its description of a pre-existing coupling smell; the actual import in `attu_models/repositories.py` was fixed in phase 1 to `nova_core.config`; the bugs.md entry text is now stale history, not an active bug

## closed
(populated at phase close)
