---
name: message-style
description: AttuBot log message and Discord response conventions - tone, capitalization, error format, custom emojis, and the ephemeral rule. trigger when editing or creating files under `apps/bot/nova_core/commands/`, `apps/bot/nova_core/client/`, `apps/bot/nova_core/tasks/`, or `apps/server/attu_server/`; when writing any line containing `logger.`, `await ctx.respond`, `await interaction.response`, or `followup.send`; when drafting any user-facing string the bot will send to Discord; when answering questions about bot voice, log style, which log level to use, or error formatting in this repo. not for python inline comments (that's `comment-style`), not for embed or view construction (that's the `pycord` skill), not for commit subjects (that's `commit-style`).
---

# message-style (AttuBot overlay)

read `~/.claude/skills/message-style/SKILL.md` once for the universal floor: what a message must tell the reader, then lowercase, no terminal punctuation, f-strings only, embed variables in the message. this skill is canonical for AttuBot; update it directly.

the model's default register - formal, capitalized, complete-sentence ("Successfully updated configuration.") - is wrong here for both logs and Discord. lift tone from the examples below.

## the requirement

**a message must leave the reader knowing what happened and what state things are in; if they have to act on it, it must say what to do.**

that is the bar. every other rule in this file trims a message that already clears it. none of them is a reason to fall below it; not the 8 to 30 word range, not the bad-message table.

before dropping a word, ask what the reader loses. if it names something they would need in order to retry, recover, or diagnose - a guild, a channel, a year, a config key, the value that failed validation - it stays. brevity breaks ties between two messages that both clear the bar; it is not a goal on its own.

the failure this rule exists to prevent is a message that is short, lowercase, correctly punctuated, and useless.

| under-informed | clears the bar |
|---|---|
| `'config loaded'` | `f'[{cfg!s}] loaded [{count}] markers'` |
| `'epoch changed'` | `f'[{guild.name}] epoch changed: old={old_time},{old_year} new={new_time},{year}'` |
| `'could not find channel'` | `f'could not find channel #{channel_name} for construction'` |
| `'invalid input'` | ``f'year {year} PC is already linked to {channel.mention}'`` |
| `'Done!'` on a mutation | ``f'Changed `{key}` from `{old}` to `{new}`'`` |

this applies to Discord responses as much as to logs; the reader there has even less context to fill a gap with.

## log levels

plain `structlog.stdlib.BoundLogger` over stdlib logging; there is no custom level. pick by what the line means, not by how urgent it feels.

| level | means | typical content |
|---|---|---|
| `debug` | our internals and the wire | payloads, cache hits, query shapes, parsed values |
| `info` | a state change an operator wants without turning the level up | config loaded, year advanced, task registered, guild reloaded |
| `warning` | degraded or skipped; the bot carried on | a backfill chunk that failed, a lookup that missed, a retry |
| `error` | an operation failed and something asked for did not happen | a command handler raised, a write was rejected, a fetch gave up |
| `critical` | the process is exiting | migration refused, extensions failed to load, incompatible config version |

**`critical` means exiting; say so in the message.** the level is the claim and the message is the evidence for it. a `critical` that does not name the exit reads as a false alarm, and one that does not name what it was doing leaves nothing to act on.

**do not use the aliases.** `logger.warn` is a deprecated alias for `warning`, `logger.fatal` one for `critical`. both split greps over our own logs; write `logger.warning` and `logger.critical`.

**attach the traceback when logging inside an `except` block** - `logger.exception(...)`, or `exc_info=err` on an `error` call. a bare `error` in an exception handler throws away the only part that locates the failure.

two mechanisms ride on the level, so it is not a free choice:

- `attu_logging.config` routes below `warning` to stdout and `warning` and above to stderr; that boundary is the operator-attention line
- `pymongo`, `aiohttp.access`, `discord.gateway`, and `discord.http` are pinned to `warning`, so our own lines below that are most of what a default run shows

the discord error webhook is **not** level-triggered; `attu_logging.webhook.send_to_webhook(err)` is an explicit call. raising a line to `error` notifies nobody on its own.

## log messages - AttuBot additions

universal rules apply. AttuBot-specific patterns on top:

- exception: in-universe proper terms (e.g. `PC`) and content inside bracket prefixes may be capitalized
- brief - 8 to 30 words, once the requirement above is met
- prefer readable names over raw snowflakes - `.name`, `.global_name`, `.display_name`; only fall back to `.id` when no human-readable alternative exists
- per-guild operations: prefix with `[{cfg!s}]` or `[{guild!s}]` to group related lines
- mutation log pattern: `old={x},{y} new={a},{b}`
- loaded-count pattern: `loaded [{count}] things`

**completion lines report state, not step completion.** "the step ended" is not information; "the bot is now in state X" is.

- `'attu_server startup complete'` says a function returned
- `f'attu_server ready; connected to {cfg.database.name}'` says where the server stands

**do not remove a name without putting something in its place.** if a guild, channel, or key is too noisy for the level it sits at, move it down a level; do not drop the fact.

**examples - lift directly:**
```python
logger.info('pushing commands to discord')
logger.info('starting initial config loading stage')
logger.debug(f'hit cache for {year} PC in #{channel.name}')
logger.info(f'[{cfg!s}] advancing to year {year} PC')
logger.warn(f'[{guild.name}] epoch changed: old={old_time},{old_year} new={new_time},{year}')
logger.error(f'could not find channel #{channel_name} for construction')
logger.critical(f'incompatible config version: file={file_version} required>={__config_version__}; exiting')
```

**bad messages** - each correction changes exactly what its reason says; none of them quietly drops a fact.

| bad | correct | why |
|---|---|---|
| `'Successfully loaded extension.'` | `f'loaded extension {name}'` | case, period, and a filler word; the name is what makes the line worth having |
| `'Loaded extension successfully!'` | `f'loaded extension {name}'` | exclamation and "successfully"; same missing subject |
| `'An error occurred while updating year.'` | `f'could not update year {year} PC; {err!s}'` | "an error occurred" names nothing; subject and cause restored, not removed |
| `'Updating year %s' % year` | `f'updating year {year} PC'` | `%s` instead of an f-string; case otherwise |
| `'config loaded'` | `f'[{cfg!s}] loaded [{count}] markers'` | no guild and no count; nothing to compare against the next run |
| `'An unexpected error occurred'` | ``f'year {year} PC is already linked to {channel.mention}'`` | discord errors sit at the same bar; name the constraint that stopped it |

## discord response messages

**tone:** casual, personable, occasionally sarcastic or playful. the bot has a voice; it is never robotic. lift phrasing from the examples below before inventing your own.

### capitalization

- lowercase start for all prose messages
- Title Case for embed titles and embed field names (no punctuation on either)
- `PC` (post-calming) is always uppercase - in-universe proper term
- **years are the number and the era, nothing else**: `7 PC`, `9 TT`. never `Year 7 PC`. this also removes the sentence-initial capital problem, since a year reference now opens with a digit
  - the one exception is `format_year_line()` in `client/calendar.py`. it is not output; `markers.py` feeds it to `find_bot_header()` as a search prefix that has to keep matching year headers already posted in discord. changing it breaks marker resolution for every past year

### punctuation

- no terminal period by default
- exclamation mark for genuine excitement only: `"Done!"`, `"Refreshing!"`, `"Happy New Year!"`
- question mark for sarcastic personality moments only: `"Do I know you?"`

### personality markers - quote-worthy examples

- `"weap."` is the bot's signature casual sign-off / self-deprecating commentary
- permission denials: `"You're not my real dad!"`, `"Nice try!"`, `"Do I know you?"`
- absurd / impossible inputs get dark humor: `"we'll all be dead; try something sooner maybe"`

### success messages (public)

- confirm what changed, not just "ok"
- show before/after for mutations: `` "Changed `x` from `old` to `new`" ``
- very short for trivial completions: `"Done!"`, `"Refreshing!"`

## errors

**no prefix.** an error carries no `Failed:` marker and no required emoji; the message itself says what went wrong. two things already separate a failure from a success without a label: errors are ephemeral and successes are public (see the ephemeral rule), and the wording names the failure.

**the bot owns its own failures, not yours.** who actually failed decides the register:

| what happened | register | example |
|---|---|---|
| something broke on our side | first person, bot as subject; say it was reported when the webhook fired | `I couldn't get at that message; {err!s}` |
| the request was invalid | state the constraint; the bot is not at fault and does not apologize for it | `year {year} PC hasn't happened yet; I only go up to {current_year} PC` |
| the caller is not allowed | a refusal, not a failure; this is where the aggressive register belongs | `Nice try! {ui_emoji("rockball")}` |

false humility is its own failure. never write "I couldn't" about a value the user typed wrong; the bot did not fail there, and pretending otherwise buries the constraint the reader needs.

**never print an exception to discord.** `{err}` and friends stay out of the response; the traceback belongs in `logger.exception(...)` and the error webhook. a stack trace or a driver message tells the reader nothing they can act on and leaks our internals into a channel.

**one clause.** an error says the one thing that went wrong and stops. no trailing "; try again in a moment", no restating the constraint a second way. the sole exception is a remedy the reader cannot discover anywhere else - `; if correct, override with `force:true`` names a flag that appears in no other place.

- the reason explains the specific constraint, not "an error occurred"
- include actionable suggestions when relevant: `` "if correct, override with `force:true`" ``
- include the underlying exception when it adds information
- use a semicolon to join the reason and the underlying detail (personality rule: never em-dashes)
- never place any emoji inside the reason text - an emoji, when there is one, goes at the end of the message

**every failure names its subject.** a timeout or a lookup failure that does not say what it waited for or looked up is one message standing in for four different failures:

```python
logger.error(f'timed out after {timeout}s waiting for {what}')
```

**do not log the same failure twice.** when a caller logs each item in a list of problems, the exception it then raises must not be re-logged at the top level as a summary.

log-side errors follow the log rules above (lowercase, no terminal punctuation, brief).

## energy and stakes

the bot's excitement runs inverse to what is at risk. it is thrilled about an egg and goes flat when a guild's timeline is about to change; when it stops playing, something real is happening.

| tier | what it covers | shape |
|---|---|---|
| loud | personal, reversible, fun - `/egg`, `/eggs *`, `/ping`, `/pong`, `/color`, `/version`, `/wiki random`, `/wiki lookup`, `/stars random`, `/stars lost`, leaderboards | exclamation mark; an emoji where one already fits |
| plain | ordinary state changes - `/remind *`, `/link family *`, `/query pins`, `/stars recheck`, `/year *` | lowercase, no exclamation, no emoji |
| quiet | irreversible or affects other people - `/marker save`, `/marker set`, `/marker clear`, `/time *`, `/wiki block`, ccboard purge and regen | no exclamation, no emoji; name what changed or what was lost |

the quiet tier is the characterizing move, not a lapse in voice. a flat line on a destructive command is the bot telling the reader this one counts.

**sanctioned exception.** `/time advance` answers `Weap. No longer going to try my best, just forcing new year instead`. that is a loud line on a quiet-tier command on purpose; the bot is being petulant about being overridden. leave it alone.

## the ephemeral rule

the rule:

> **ephemeral responses**: use `ephemeral=True` only for errors and validation failures; successful command responses should be public (no `ephemeral` argument).

this is a recurring footgun. defaults to repeat:

```python
# good - error is ephemeral, success is public
await ctx.respond(f'year {year} PC is already linked to {channel.mention}', ephemeral=True)
await ctx.respond(f'Linked year {year} PC to {channel.mention}')

# bad - hides a successful mutation from the channel
await ctx.respond('Done!', ephemeral=True)

# bad - leaks an error publicly
await ctx.respond('not allowed in this channel')
```

## custom emojis

read them from config with `ui_emoji(name)`; never hardcode `<:name:id>`. migration 2.5.4 seeds four into `config.theme.ui_emojis`.

| name | role |
|---|---|
| `rockball` | aggressive and cheeky - denials, permission refusals, ping and pong banter |
| `rockball_player` | failure and empty results - no matches, nothing found, unexpected errors |
| `crackerpeaty` | possessive refusal - "that one is not yours to touch" |
| `tieteran_wave` | reaction-only; on wiki bot activity messages for blocked / registered events |

**emoji are sparse affect, not markers.** most messages carry none, and an error is never required to have one. use one only where it already earns its place; do not add emoji to a message to signal that it failed.

standard Discord emoji names (`:ballot_box_with_check:`, `:no_entry:`) are fine for simple status indicators in embeds.

**never place any emoji inside error reason text** - only at the end of the top-level message string.

## markdown and discord formatting

| syntax | use for |
|---|---|
| `**text**` | important values or status in informational messages |
| `` `token` `` | identifiers, config keys, flag names |
| `__query__` | user-supplied search terms |
| `<#{channel.id}>` | channel references |
| `<@&{role.id}>` | role pings |
| `<t:{unix}:d>` | date-only timestamps |
| `<t:{unix}:f>` | full date+time timestamps |
| `<t:{unix}:R>` | relative timestamps ("in 3 days") |
| `## Heading` | headers for list-style or multi-section responses |

## help text (slash commands)

group, command, and option descriptions are what a user reads in the picker before they know what anything does. same bar as every other message: say what it does, and what the user has to decide.

- **all lowercase**, first word included; in-universe terms keep their case (`PC`, `Haracalnde`)
- **no trailing period and no exclamation mark**
- **imperative fragment** - `collect an egg`, never `Collects an egg` and never `Egg collection`
- **describe the effect, not the mechanism**
- **100 characters hard.** discord refuses to register a longer description; `/year info` currently sits at exactly 100, so there is no room left in it
- every group, command, and option takes one, and it has to say something the name does not; discord already renders the name beside it

**groups name the area, not the fact that they are a group.** `Link utilities` and `Utilities related to managing year markers` spend the whole line saying "these are commands".

**options say what the value does to the command,** with bounds, format, source, or default in parentheses:

| bad | correct | why |
|---|---|---|
| `Year Number` | `which year to move the marker to (1 to current)` | restates the option name; the bound is what validation actually enforces |
| `Override Mode` | `accept a link far from the expected time` | names the mode but never what it overrides |
| `Search Query` | `what to search the wiki for` | restates the option name |
| `Wiki Username (case sensitive probably)` | `who to block (case sensitive)` | "probably" hands our uncertainty to the user |

**mark admin-only once, on the group,** as `(admin only)`. repeating it on every child command is noise, and `default_member_permissions` already hides them.

**never ship internal state.** `(phase 2 stub)` and `walking-skeleton stub; replaced by real /cc stars commands in phase 2.6+` name our plan structure to end users. a command that is not ready says what the user gets instead: `not implemented yet`.

changed descriptions reach discord when the bot next starts and pushes its command definitions; they are not inert.

## cross-references

- `CLAUDE.md` - personality section for semicolons, dashes, and american english; `docs/style/command_usage.md` for the ephemeral rule
- `pycord` skill (`embeds` section) - embed construction (titles, fields, colors)
- `commit-style` skill - related custom-emoji usage in commit subjects
