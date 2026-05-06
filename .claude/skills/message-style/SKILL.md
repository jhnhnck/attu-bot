---
name: message-style
description: AttuBot log message and Discord response conventions - tone, capitalization, error format, custom emojis, and the ephemeral rule. trigger when editing or creating files under `doom_bot/commands/`, `doom_bot/client/`, `doom_bot/tasks/`, or `doom_bot/web/`; when writing any line containing `logger.`, `await ctx.respond`, `await interaction.response`, or `followup.send`; when drafting any user-facing string the bot will send to Discord; when answering questions about bot voice, log style, or error formatting in this repo.
---

# message-style

Authoritative reference for log messages and Discord response strings in this repo. This skill is canonical; update it directly.

The model's default register - formal, capitalized, complete-sentence ("Successfully updated configuration.") - is wrong here for both logs and Discord. Lift tone from the examples below; do not paraphrase into something more polished.

## log messages

**tone:** purely technical and diagnostic. no personality, no humor.

**hard rules:**
- always lowercase; never sentence-case
  - exception: in-universe proper terms (e.g. `PC`) and content inside bracket prefixes
  - software/platform names (discord, python, etc.) are also lowercase
- no terminal punctuation - no periods, no ellipses, no exclamation marks
- active voice, present tense - what is happening, not what happened
- brief - 8 to 30 words; signal only, no prose
- f-strings for interpolation; never `%s` or `.format()`
- prefer readable names over raw snowflakes - `.name`, `.global_name`, `.display_name`; only fall back to `.id` when no human-readable alternative exists
- per-guild operations: prefix with `[{cfg!s}]` or `[{guild!s}]` to group related lines
- mutation log pattern: `old={x},{y} new={a},{b}`
- loaded-count pattern: `loaded [{count}] things`

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

**anti-patterns** - do not write any of these:
```python
logger.info('Successfully loaded extension.')  # capitalized, period, formal
logger.info('Loaded extension successfully!')  # exclamation, "successfully"
logger.error('An error occurred while updating year.')  # vague, capitalized, period
logger.info('Updating year %s' % year)  # %s instead of f-string
```

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

log-side errors follow the log rules above (lowercase, no terminal punctuation, brief).

## the ephemeral rule

from `notes/agents.md` (coding conventions, discord section):

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

- `notes/agents.md` - ephemeral rule (discord coding conventions section); personality section for semicolons / dashes / american english
- `pycord` skill (`embeds` section) - embed construction (titles, fields, colors)
- `commit-style` skill - related custom-emoji usage in commit subjects
