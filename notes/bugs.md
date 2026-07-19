# bug log

reported bugs live here, separate from the feature backlog in `notes/to-do.md`. run the `bug-triage` skill (`~/.claude/skills/bug-triage/`) to assign severity (`blocker` / `important` / `nit`) and disposition (`fix-now` / `fix-in-phase-N` / `defer` / `won't-fix`) — the skill is the cut-line authority and does not fix code itself.

format and conventions match `notes/to-do.md` (all lowercase, `- ⭕` for open / `- 🔴` for resolved). see the [meta](#meta) section for the format reference.

---

## untriaged

### starboard

- ⭕ `bug` starboard doesn't render multiple images from messages with more than one attachment (from cowboy)
- ⭕ `bug` stickers and voice memos still have rendering issues; voice memos don't show the no-preview text either; gif links include a png instead of the gif/gifv

### wiki

- ⭕ `bug` `commands/wiki.py` wiki lookup pagination allows negative index via rapid button clicks — `_prev_callback`/`_next_callback` have no bounds check; the `disabled` state only rebuilds after the async wiki fetch, so concurrent clicks bypass it; corrupted index persists to db (from banarnar)

### scheduling

- ⭕ `bug` `commands/time.py:34` `time_advance` passes `cfg.guild.id` to `scheduler.add_job` but `GuildConfig` has no `.guild` attr; should be `cfg.id`

### architecture

- ⭕ `smell` `packages/shared-models/attu_models/repositories.py:36` `attu_models` imports `doom_bot.config.{BotTheme, GuildConfig}` inside a `TYPE_CHECKING` block; the runtime cycle is broken (verified by structlog phase 1 cross-phase check) but the type-hint coupling means shared-models still knows about `doom_bot.config`. fix would either move `BotTheme` / `GuildConfig` into shared-models or generalize the repository signatures to accept protocols (from structlog phase 1 retro)

### upstream / dependencies

- ⭕ `bug` `discord/client.py:250` pycord `DeprecationWarning` on python 3.13 — `asyncio.get_event_loop()` called without a running loop; will break on a future python version; may need a pycord upgrade or workaround

### deploy

- ⭕ `smell` `scripts/deploy.py:37-44` the attu-year epoch snapshot (`_epoch_toml`) is hardcoded inline and manually re-pasted from `/fix epoch` whenever it changes. tree-editor's `publish-package.zsh` (attu-standalone-packaging plan) now reads the same epoch from a shared `~/.attu-epoch.toml` file on the host instead of duplicating the snapshot a third time. `deploy.py` should migrate `compute_attu_year()` to read that same file instead of `_epoch_toml`, so there's one canonical epoch copy on the host, not two independently-updated ones (from cross-repo work in tree-editor, not yet actioned here)

---

## triaged

_(empty — populate via the `bug-triage` skill)_

---

## resolved

_(empty)_

---

## meta

### format

untriaged: `- ⭕ \`bug\` [optional file:line] description (optional source/reporter)`

triaged: `- [<severity>] <title> → <disposition> · <note>` per the `bug-triage` skill emit format; group by severity under the `## triaged` heading

resolved: `- 🔴 \`<date>\` description`; sort chronologically (oldest first), prune entries no longer referenced

### severity (highest to lowest)

- `blocker` — ship is unsafe with this present (data loss, security, broken core flow, regression of a shipped feature)
- `important` — correctness gap or real annoyance; workaround exists or impact is bounded
- `nit` — polish, minor inconsistency, low-value cleanup

severity is about impact, not effort.

### disposition

- `fix-now` — interrupt current work; rare, only true blockers found mid-phase
- `fix-in-phase-N` — schedule into a specific upcoming phase; name the phase
- `defer` — keep in the log; revisit at next triage or before ship
- `won't-fix` — explicitly close, with a one-line reason (mandatory)

defaults: blockers → fix-now or fix-in-phase-N (never defer); important → fix-in-phase-N or defer; nits → defer or won't-fix.

### triage workflow

invoke the `bug-triage` skill when:

- the untriaged list grows after a phase wraps
- before `ship-readiness` is run
- the user asks to "triage", "go through the bugs", "what's blocking ship", etc.

the skill reads every entry in full, assigns severity + disposition, and surfaces patterns when 3+ items cluster around the same area, premise, or root cause. cluster patterns get handed to `plan-revise` for phase-level rework.

### sections

- **untriaged** — open bugs awaiting triage
- **triaged** — open bugs with a severity + disposition assigned
- **resolved** — fixed bugs kept for reference; pruned when no longer relevant
- **meta** — this section; describes the doc format and triage workflow

### metadata

```yaml
last_updated: 10 May 2026
total_resolved: 0
```
