---
name: code-review
description: AttuBot per-phase qualitative diff review - multi-pass review covering correctness, design, repo-specific bug patterns, tests, documentation, security, and style. trigger when the user says "review this", "review the diff", "review the branch", "code review", "look this over", "is this good", "any issues with this"; before opening a PR or asking for sign-off; after a phase's programmer step finishes and before `integration-check`; when reviewing another agent's output. asks "is this diff right". distinct from `feature-completion` (mechanical did-i-ship-this checklist), `integration-check` (whole-product survival check), and `bug-triage` (cut-line on the bug log). defers to the project style skills for style judgments rather than restating their rules.
---

# code-review

scope: a qualitative pass over a diff or branch. answers "is this code right, well-designed, safe, and consistent with the repo." not a checklist (`feature-completion` is); not a survival check (`integration-check` is); not a triage (`bug-triage` is). run after the programmer reports done and before `integration-check`.

defer style judgments to the style skills. this skill names the *passes* and the *repo-specific bug patterns to look for*; the style skills are canonical for what good actually looks like.

## how to run

walk the diff once per pass, in order. each pass has a question; a finding is anything that fails to satisfy it. record findings as a flat list with severity tags (`blocker` / `important` / `nit`); hand the list to `bug-triage` if the phase is over, or back to the programmer if it's mid-phase.

skip a pass only when nothing in the diff is in scope for that pass (e.g. no web changes → skip the security pass's web items, not the whole pass).

before starting, run `git diff <base>...HEAD` (or read the staged hunks) so the review is grounded in actual lines, not the conversation's recollection of them.

## pass 1 - correctness

question: does each changed line do what it claims, on the inputs it will actually see?

- the obvious one: walk the happy path, then walk the edge cases the diff *should* have handled (empty inputs, missing config, paused epoch, bot acting on itself, message already deleted, channel gone, role gone)
- async sequencing: anything reading shared state after an `await` may be reading a stale copy; anything writing without `upsert=True` may assume a doc that was deleted between the read and the write
- repository pattern: every db touch must go through a repository class (`packages/shared-models/attu_models/repositories.py`), never raw `db[collection]` calls
- `ConfigDict(extra='ignore')` semantics: adding a field to `GuildConfigDocument` is required *for the field to ever be read* - new fields silently default until they're declared
- `wait_for_*` gates: code that touches the db before `on_init`, the bot before `on_load`, or the guild config before `on_ready` will see partial state; use the appropriate `NovaConfig.wait_for_*` if uncertain

## pass 2 - design

question: does this fit how the rest of the codebase is shaped, or did it grow a parallel structure?

- new slash command? must be a pycord extension with `setup(bot)` registering a `SlashCommandGroup` (see the `pycord` skill); `/ping` is the only intentional exception
- new background task? must extend `BaseTask` and register through `TaskScheduler`; never `asyncio.create_task()` at module import
- new singleton? prefer adding to `client/core.py` rather than a fresh module-level global
- new web mutation? must go through `web_app.audit_logger.log_change(...)` and call `bridge.trigger_reload()` after save
- new config field? must follow the **six-step tier-3 plumbing** if it's per-guild (see `pydantic` skill or `feature-completion` for the full list); skipping any step makes the field a silent default in production
- abstraction temperature: a one-call helper isn't an abstraction, it's a rename - inline it. three near-identical blocks are not yet a generic - copy is fine until pattern #4

## pass 3 - repo-specific bug patterns

these are the failure modes that have actually shipped here. the diff is high-risk if it touches one.

- **snowflake precision in json.** discord ids exceed `Number.MAX_SAFE_INTEGER`; any id sent to or read from the browser must be a string. failure mode shipped twice: `fix(web): parseInt was eating role ids`, `fix(web): trees roles silently zeroed on every save`. check both directions - serialization (`str(id)`) and deserialization (no `parseInt`/`Number()` on snowflakes; use `BigInt` or string compare)
- **float-vs-int on legacy mongo docs.** older writes and ferret round-trips can return `float` where the model expects `int`; `int()` coerce in the model validator if the field comes off disk. failure mode shipped: `fix(eggs): coerce float collected_at and hatches_at to int on load`, `fix(starboard): ... int timestamps`. cross-reference: `ferretdb-quirks` skill
- **per-process shared state.** the bot and server processes share collections; scheduler queues and persistent locks need a per-process key, not a shared one. the scheduler must only be registered in the bot process (`register_bot_tasks()` in `client/events.py`), never at module-import time. failure mode shipped: `fix(signals): bot and ingestor were stealing each other's reload signals`. always scope cross-process db state by target
- **bot-as-actor edge cases.** modlog, starboard, and reaction handlers must check whether the bot itself is the actor before logging or echoing. failure modes shipped: `fix(modlog): bot users were ignored in kick/ban messages`, `fix(modlog): skip modlog post when bot is the delete actor`, `fix(starboard): bot-removal echo suppression prevents self-star cascade`
- **persistent views need rebinding on startup.** any `discord.ui.View` with `timeout=None` must be re-registered (`bot.add_view(...)`) on `on_ready` or buttons die after restart. failure mode shipped: `fix(wiki): lookup buttons don't die on restart`
- **mention scope on relayed user content.** any embed or message that re-renders user-supplied text into a discord message must pass `allowed_mentions=discord.AllowedMentions.none()` (or equivalent), or it can fire pings from quoted text. failure mode shipped: `fix(starboard): notification preview could fire pings from starred message text`
- **migration safety.** every new migration in `client/migrations.py` needs a backup or rollback path before it lands; mass field-population migrations especially. failure mode shipped: `fix(emojis): backup and restore safety for ui_emojis migration`. cross-reference: `mock-compensation` skill (migration test rule)
- **hardcoded asset paths.** anything reaching for assets must go through `config.paths.assets`, not relative paths. failure mode shipped: `fix(svg): use config.paths.assets for asset lookups`
- **schema vs config version.** db migration → bump `__schema__` only; TOML format change → bump both `__schema__` and `__config_version__` *and* update `config/attu-bot.sample.toml`. cross-reference: feedback memory and `feature-completion`

## pass 4 - tests

question: does the change come with the tests it needs, and are the tests testing the behavior rather than the implementation?

- new logic → unit test in `tests/python/unit/`
- new repository method or db operation → component test in `tests/python/component/`
- mocked a framework mechanism (extension loading, permission predicates, migrations) → check the `mock-compensation` skill's standing-cases list; if this case is on it, the compensating real test must exist or be added in the same diff
- new tier-3 config field → roundtrip test that saves a non-default value and asserts it survives `load_guild()`
- new migration → rollback path test
- assert behavior, not call shape: `assert_called_with(...)` on an internal helper is brittle; assert the resulting db state or the message sent
- tests must not depend on real time; freezegun is the convention (`TZ=UTC` is already set in the harness)

defer to: `mock-compensation` skill (the rule + standing cases), `docs/dev/testing.md` (fixtures and harness conventions), `feature-completion` skill (the literal tests checklist).

## pass 5 - documentation

question: would someone touching this area in three months understand it from the repo alone?

- behavior or storage of a documented feature changed → corresponding `docs/features/*.md` updated in the same diff
- new feature spec → `docs/features/` entry plus a nav row in `mkdocs.yml`
- `docs/to-do.md` reflects what landed and what's deferred
- inline comments earn their place per `comment-style`; default is no comment

defer to: `comment-style` skill (case, brevity, todo tags, noqa reasons), `file-header` skill (SPDX + breadcrumb on new files), `feature-completion` skill (literal documentation checklist).

## pass 6 - security

question: does this expose anything to an unauthorized actor, leak anything sensitive, or trust input it shouldn't?

threat model is small: web admin (discord oauth) and discord slash commands (per-guild authorization). this pass watches the seams.

- **web auth gates.** every new route must opt into the right gate (`@login_required`, csrf check on state-changing requests, rate limit on auth endpoints). failure mode shipped: `fix(security): session hardening, xss and open redirect fixes`
- **open redirect via `?next=`.** if you accept a `next` parameter, store and redirect to a *path*, not a full url; rejecting absolute urls is the standing remedy
- **template autoescape.** any `|safe` filter or `Markup(...)` needs a clear reason; user-supplied strings and config values must not flow into the template unescaped
- **validation error leakage.** `pydantic.ValidationError.errors()` includes the offending `input` value, which can leak secrets (webhook urls, tokens) when returned in a json response. surface only `[err['msg'] for err in e.errors()]`, not the full structure
- **secret echoing.** any api response that round-trips a config value containing a secret must mask it (`f'...{value[-6:]}'` is the project convention for webhook urls). check both the success path and the audit log payload
- **per-guild authorization.** new slash commands must check `is_authorized_guild`, `is_bot_owner`, or `has_announcements_role` via `@commands.check(...)` from `discord.ext.commands` - **not** `discord.commands.check`, which doesn't exist (recurring footgun; see `pycord` skill). predicates live in `client/util.py`
- **mention scope.** any message that re-renders user-supplied text needs `allowed_mentions=discord.AllowedMentions.none()` (also in pass 3)
- **ephemeral leak.** errors must be `ephemeral=True`, successful mutations public; the inverse leaks errors and hides successes (see `message-style` skill)
- **audit log coverage.** every web mutation goes through `web_app.audit_logger.log_change(...)`; missing audit on a mutation is a security finding, not a docs finding
- **rule #2.** never call discord apis or webhooks from review tools without explicit instruction; never call `git push` or deploy without explicit instruction (rule #3)

if the diff includes ai/llm tool changes, defer additionally to the `claude-api` skill.

## pass 7 - style

question: does it match how the rest of the repo is written?

this pass does not restate rules. it routes to the canonical skill for each surface and reports any drift those skills would flag. one trip through the diff, one routing decision per touched surface.

- python comments → `comment-style` skill
- log lines (`logger.*`) → `message-style` skill (log section)
- discord response strings (`ctx.respond`, `interaction.response`, `followup.send`) → `message-style` skill (discord section, ephemeral rule, error format, custom emojis)
- new source file → `file-header` skill (SPDX + structured docstring)
- pycord-specific patterns (extensions, slash commands, `discord.ext.commands.check`, embeds, views) → `pycord` skill
- pydantic patterns (document/runtime split, validators, `ConfigDict`) → `pydantic` skill
- mediawiki api code (`packages/attu-wiki/attu_wiki/`) → `mediawiki-api` skill
- ferret/mongo divergence (`packages/shared-models/`, `client/migrations.py`) → `ferretdb-quirks` skill
- docker compose work (`docker-compose.*.yml`, `scripts/`) → `docker-commands` skill
- log-reading recipes during review → `container-logs` skill
- commit message under review → `commit-style` skill
- commit-split staging questions → generic `~/.claude/skills/commit-split/` (this project has no project-specific override)

linting (`uv run ruff check`, `uv run ruff format --check`) and the noqa-reason rule are mechanical - they belong in `feature-completion`, not here. the style pass should still flag any `# noqa` without a reason as a finding (rule #4 is a hard rule; not a style preference).

## output shape

a flat list, one finding per line, in the form:

```
[severity] [pass] file:line - one-sentence finding; one-sentence why it matters
```

severities: `blocker` (don't ship), `important` (fix this phase), `nit` (defer to bug log unless cheap to fix now).

at the end: a one-sentence verdict - `ready for integration-check`, `back to programmer`, or `escalate to plan-revise` (the third only if a finding suggests the phase's premise is wrong).

## scope vs sibling skills

| skill | the question it answers |
|---|---|
| `code-review` (this) | is this diff right, well-designed, safe, consistent with the repo |
| `feature-completion` | did i mechanically check every box this kind of change requires |
| `integration-check` | did the rest of the product survive this phase |
| `phase-retro` | what landed vs spec, what surprised us, what debt remains |
| `bug-triage` | of the bugs we know about, which block ship and which defer |
| `ship-readiness` | is the project ready to release |
| `pre-mortem` | before any work starts, what's the plan likely to get wrong |
| `plan-revise` | given retro + triage, what changes downstream |

run order at a phase boundary: programmer → `feature-completion` → `code-review` → `integration-check` → `phase-retro` → `bug-triage` → `plan-revise`.

## cross-references

- `docs/dev/process.md` - the loop this skill sits inside
- `CLAUDE.md` - rules, pitfalls, and personality conventions this skill draws from; `docs/architecture.md` - package layout and file roles
- canonical style skills: `comment-style`, `message-style`, `commit-style`, `file-header`, `pycord`, `pydantic`, `mediawiki-api`, `ferretdb-quirks`, `mock-compensation`, `docker-commands`, `container-logs`
- shared sibling skills: `pre-mortem`, `integration-check`, `phase-retro`, `bug-triage`, `plan-revise`, `ship-readiness`
