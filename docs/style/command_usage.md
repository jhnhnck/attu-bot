# slash command conventions

project patterns for defining slash commands with pycord. covers group structure, options, context usage, and auth guards.

---

## command groups

top-level groups use `SlashCommandGroup`. subgroups use `.create_subgroup()`. commands hang off the group with `@group.command()`.

```python
from discord import SlashCommandGroup

eggs_group = SlashCommandGroup('eggs', description='egg collection game')
leaderboard_group = eggs_group.create_subgroup('leaderboard', 'egg leaderboards')

@eggs_group.command(name='hatch', description='hatch your next ready egg')
async def eggs_hatch(ctx: ApplicationContext): ...

@leaderboard_group.command(name='top', description='top egg collectors')
async def leaderboard_top(ctx: ApplicationContext): ...
```

top-level standalone commands use `@discord.slash_command()`:

```python
@discord.slash_command(name='egg', description='collect an egg!')
async def egg_command(ctx: ApplicationContext): ...
```

register everything in `setup(bot)` at the bottom of the module:

```python
def setup(bot: Bot):
    logger.info(f'registered: {__name__}')
    bot.add_application_command(eggs_group)
    bot.add_application_command(egg_command)
```

---

## options

use `@discord.commands.option` for typed parameters. always provide `name`, `required`, `description`, and `input_type`.

```python
@wiki_group.command(name='lookup', description='search the wiki for relevant pages')
@discord.commands.option(name='query', required=True, description='search query', input_type=str)
async def wiki_lookup(ctx: ApplicationContext, query: str): ...
```

`@discord.commands.option` decorators are applied bottom-up (closest to the function = first param after `ctx`). keep them in the same order as the function signature.

**hard limit**: command and option descriptions are capped at **100 characters** by discord. pycord validates at extension import time — an overrun raises `ValueError` before the bot reaches ready. `TestExtensionImports` in the test suite catches this on every run.

---

## application context

always type `ctx` as `ApplicationContext`. the key methods:

| call | when to use |
|---|---|
| `await ctx.defer()` | any command that does async work before responding; prevents the "thinking" timeout (3s) |
| `await ctx.defer(ephemeral=True)` | defer a response that will be ephemeral |
| `await ctx.respond(...)` | send the initial response (or first followup after defer) |
| `await ctx.edit(...)` | edit the initial response in place |
| `await ctx.respond(..., ephemeral=True)` | send a response only the invoker sees |
| `ctx.user` | the invoking member (`discord.Member` in a guild) |
| `ctx.guild_id` | guild snowflake or `None` (DMs) |
| `ctx.channel_id` | channel snowflake |
| `ctx.interaction.original_response()` | await to get the `discord.Message` handle after a defer+respond |

defer at the top of every command that does any I/O:

```python
@eggs_group.command(name='hatch', description='hatch your next ready egg')
async def eggs_hatch(ctx: ApplicationContext):
    await ctx.defer()
    result = await hatching.hatch_egg(ctx.guild_id, ctx.author.id)
    await ctx.respond(result)
```

---

## guild auth

always check guild authorization before acting. two patterns:

**inline guard** (commands that are guild-only but not in a permission-gated group):

```python
if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
    await ctx.respond('not available here', ephemeral=True)
    return
```

**decorator guard** (admin/moderator commands):

```python
from discord.ext import commands
from nova_core.client.util import is_authorized_guild

@wiki_group.command(name='block', description='block a wiki user (admin only)')
@commands.has_permissions(administrator=True)
@commands.check(is_authorized_guild)
async def wiki_block(ctx: ApplicationContext, ...): ...
```

use `@commands.check(predicate)` from `discord.ext.commands`, not `@discord.commands.check()` — the latter does not exist in pycord. `is_authorized_guild` is the project utility in `nova_core.client.util`.

---

## ephemeral responses

use `ephemeral=True` for:
- error messages (auth failures, cooldowns, validation)
- user-specific confirmations (link codes, settings)
- anything that is noise in a public channel

do not use ephemeral for offer messages, board posts, or any output other users should see.

---

## module structure

the standard layout for a command module:

```python
# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.eggs | egg game slash commands."""

import discord
from discord import ApplicationContext, Bot, SlashCommandGroup

from nova_core.client.core import config

logger = structlog.stdlib.get_logger(__name__)

# --- group definitions ---

eggs_group = SlashCommandGroup('eggs', description='...')

# --- views (if any) ---

class SomeView(discord.ui.View): ...

# --- commands ---

@eggs_group.command(...)
async def some_command(ctx: ApplicationContext): ...

# --- extension def ---

def setup(bot: Bot):
    logger.info(f'registered: {__name__}')
    bot.add_application_command(eggs_group)
```

section dividers (`# --- label ---`) are module-level only. keep them; they're how long command files stay navigable.

---

## metadata

```yaml
last_updated: 2026-08-23
```
