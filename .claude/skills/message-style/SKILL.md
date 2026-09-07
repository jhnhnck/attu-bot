---
name: message-style
description: AttuBot log message and Discord response conventions - tone, capitalization, error format, custom emojis, and the ephemeral rule. trigger when editing or creating files under `apps/bot/nova_core/commands/`, `apps/bot/nova_core/client/`, `apps/bot/nova_core/tasks/`, or `apps/server/attu_server/`; when writing any line containing `logger.`, `await ctx.respond`, `await interaction.response`, or `followup.send`; when drafting any user-facing string the bot will send to Discord; when answering questions about bot voice, log style, or error formatting in this repo. not for python inline comments (that's `comment-style`), not for embed or view construction (that's the `pycord` skill), not for commit subjects (that's `commit-style`).
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
| `'Failed: invalid input'` | ``f'Failed: year {year} PC is already linked to {channel.mention}'`` |
| `'Done!'` on a mutation | ``f'Changed `{key}` from `{old}` to `{new}`'`` |

this applies to Discord responses as much as to logs; the reader there has even less context to fill a gap with.

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
logger.fatal('incompatible config version')
```

**bad messages** - each correction changes exactly what its reason says; none of them quietly drops a fact.

| bad | correct | why |
|---|---|---|
| `'Successfully loaded extension.'` | `f'loaded extension {name}'` | case, period, and a filler word; the name is what makes the line worth having |
| `'Loaded extension successfully!'` | `f'loaded extension {name}'` | exclamation and "successfully"; same missing subject |
| `'An error occurred while updating year.'` | `f'could not update year {year} PC; {err!s}'` | "an error occurred" names nothing; subject and cause restored, not removed |
| `'Updating year %s' % year` | `f'updating year {year} PC'` | `%s` instead of an f-string; case otherwise |
| `'config loaded'` | `f'[{cfg!s}] loaded [{count}] markers'` | no guild and no count; nothing to compare against the next run |
| `'Failed: an error occurred'` | ``f'Failed: year {year} PC is already linked to {channel.mention}'`` | discord errors sit at the same bar; name the constraint that stopped it |

## discord response messages

**tone:** casual, personable, occasionally sarcastic or playful. the bot has a voice; it is never robotic. lift phrasing from the examples below before inventing your own.

### capitalization

- lowercase start for all prose messages
- Title Case for embed titles and embed field names (no punctuation on either)
- `PC` (post-calming) is always uppercase - in-universe proper term

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

## errors - exact shape

every error message starts with `Failed:` followed by a lowercase reason.

```
Failed: <reason in lowercase>
```

- the reason explains the specific constraint, not "an error occurred"
- include actionable suggestions when relevant: `` "if correct, override with `force:true`" ``
- include the underlying exception when it adds information: `"Failed: Couldn't parse value; {err!s}"`
- use a semicolon to join the reason and the underlying detail (personality rule: never em-dashes)
- never place any emoji inside the reason text - emojis only at the end of the top-level message string

**every failure names its subject.** a timeout or a lookup failure that does not say what it waited for or looked up is one message standing in for four different failures:

```python
logger.error(f'timed out after {timeout}s waiting for {what}')
```

**do not log the same failure twice.** when a caller logs each item in a list of problems, the exception it then raises must not be re-logged at the top level as a summary.

log-side errors follow the log rules above (lowercase, no terminal punctuation, brief).

## the ephemeral rule

the rule:

> **ephemeral responses**: use `ephemeral=True` only for errors and validation failures; successful command responses should be public (no `ephemeral` argument).

this is a recurring footgun. defaults to repeat:

```python
# good - error is ephemeral, success is public
await ctx.respond(f'Failed: year {year} PC is already linked', ephemeral=True)
await ctx.respond(f'Linked year {year} PC to {channel.mention}')

# bad - hides a successful mutation from the channel
await ctx.respond('Done!', ephemeral=True)

# bad - leaks an error publicly
await ctx.respond('Failed: not allowed in this channel')
```

## custom emojis

three custom server emojis, each with a distinct role:

| name | full syntax | when to use |
|---|---|---|
| `:rockball:` | `<:rockball:1308981475114225694>` | playful / personality moments - ping responses, permission denial sarcasm, general fun |
| `:rockball_player:` | `<:rockball_player:1308977543034048552>` | errors and unexpected failures - no results, message not found, unhandled exceptions |
| `:tieteran_wave:` | `<:tieteran_wave:1308636215930654801>` | reaction-only; on wiki bot activity messages for blocked / registered events |

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

## cross-references

- `CLAUDE.md` - personality section for semicolons, dashes, and american english; `docs/style/command_usage.md` for the ephemeral rule
- `pycord` skill (`embeds` section) - embed construction (titles, fields, colors)
- `commit-style` skill - related custom-emoji usage in commit subjects
