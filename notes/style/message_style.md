# message style

conventions for log messages and discord response messages.

---

## log messages

**tone:** purely technical and diagnostic - no personality, no humor.

**rules:**
- always lowercase; never sentence-case
  - exception: in-universe proper terms (e.g. `PC`) and content inside bracket prefixes
  - software/platform names (discord, python, etc.) are also lowercase
- no terminal punctuation - no periods, no ellipses, no exclamation marks
- active voice, present tense - describe what is happening, not what happened
- brief - 8 to 30 words; no prose, just signal
- f-strings for interpolation; never `%s` or `.format()`
- prefer readable names over raw snowflakes - use `.name`, `.global_name`, `.display_name`, etc.; only use `.id` when no human-readable alternative exists
- for per-guild operations, prefix with `[{cfg!s}]` or `[{guild!s}]` to group related log lines
- mutation log pattern: `old={x},{y} new={a},{b}`
- loaded-count pattern: `loaded [{count}] things`

**examples:**
```python
logger.info('pushing commands to discord')
logger.info('starting initial config loading stage')
logger.info(f'command executed: user="{ctx.user.global_name}" command="/{ctx.command}" channel="{ctx.channel.name}"')
logger.debug(f'hit cache for {year} PC in #{channel.name}')
logger.debug(f'closest found: {message.id} (off by {distance}s)')
logger.info(f'[{cfg!s}] advancing to year {year} PC')
logger.warn(f'[{guild.name}] epoch changed: old={old_time},{old_year} new={new_time},{year}')
logger.error(f'could not find channel #{channel_name} for construction')
logger.fatal('incompatible config version')
```

---

## discord response messages

**tone:** casual, personable, occasionally sarcastic or playful. the bot has a personality and a voice; it is never robotic.

### capitalization

- lowercase start for all prose messages
- Title Case for embed titles and embed field names (no punctuation on either)
- "PC" (post-calming) is always uppercase - it's an in-universe proper term

### punctuation

- no terminal period by default
- exclamation mark for genuine excitement only: `"Done!"`, `"Refreshing!"`, `"Happy New Year!"`
- question mark for sarcastic personality moments only: `"Do I know you?"`
- all error messages start with `"Failed:"` - this is the universal error prefix

### personality markers

- `"weap."` is the bot's signature casual sign-off or self-deprecating commentary
- permission denials get sarcasm: `"You're not my real dad!"`, `"Nice try!"`, `"Do I know you?"`
- absurd/impossible inputs get dark humor: `"we'll all be dead; try something sooner maybe"`

### errors (always ephemeral=True)

```
Failed: <reason in lowercase>
```

- reason explains the specific constraint, not just "an error occurred"
- include actionable suggestions when relevant: `"if correct, override with \`force:true\`"`
- include the underlying error when it adds information: `"Failed: Couldn't parse value; {err!s}"`

### success messages (public)

- confirm what changed, not just "ok"
- show before/after for mutations: `` "Changed `x` from `old` to `new`" ``
- very short for trivial completions: `"Done!"`, `"Refreshing!"`

### markdown and discord formatting

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

### custom emojis

three custom server emojis are in use, each with a distinct role:

| name | full syntax | when to use |
|---|---|---|
| `:rockball:` | `<:rockball:1308981475114225694>` | playful/personality moments - ping responses, permission denial sarcasm, general fun |
| `:rockball_player:` | `<:rockball_player:1308977543034048552>` | errors and unexpected failures - no results, message not found, unhandled exceptions |
| `:tieteran_wave:` | `<:tieteran_wave:1308636215930654801>` | reaction-only; used on wiki bot activity messages for blocked/registered events |

standard Discord emoji names (`:ballot_box_with_check:`, `:no_entry:`) are fine for simple status indicators in embeds.

never place any emoji inside error reason text - only at the end of the top-level message string.
