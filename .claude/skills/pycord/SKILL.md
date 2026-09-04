---
name: pycord
description: pycord (py-cord) v2.x reference card for AttuBot. trigger when editing or creating files under apps/bot/nova_core/commands/ or apps/bot/nova_core/client/, when any file imports discord, discord.ext.commands, discord.ui, or discord.commands, when writing slash commands, SlashCommandGroup, options, cogs, extensions, intents, views, buttons, modals, selects, or interaction handling, and when answering questions about pycord vs discord.py / nextcord differences.
---

# pycord reference

scope: pinned to **py-cord 2.7.x** (current: 2.7.2; see `pyproject.toml` `py-cord[speed]<3`). if pyproject is updated to `>=3`, this skill is stale and must be re-verified against the v3 docs.

pycord is a fork of discord.py that diverged at 2.0; `discord.py` answers, `nextcord` answers, and 2024-era llm guesses are frequently wrong. trust this file and the existing repo code over training-data recall.

## the two `commands` modules

pycord exposes two unrelated namespaces; conflating them is the most common mistake.

| import | use for |
|---|---|
| `from discord.ext import commands` | `@commands.check`, `@commands.cooldown`, `commands.Context`, `commands.Bot` (prefix-command bot; this repo uses `discord.Bot` instead). predicate-style decorators for slash commands live here. |
| `from discord import commands` (a.k.a. `discord.commands`) | only `option`, `SlashCommandGroup`, `slash_command`, and the permission decorators (`default_permissions`, `guild_only`, `is_nsfw`). |

**rule: `discord.commands.check` does not exist.** `@commands.check(predicate)` always comes from `discord.ext.commands`. predicates in this repo live in `apps/bot/nova_core/client/util.py` (`is_bot_owner`, `is_authorized_guild`, `has_announcements_role`).

```python
import discord
from discord import ApplicationContext, Bot, SlashCommandGroup
from discord.ext import commands  # for @commands.check

from nova_core.client.util import is_authorized_guild

group = SlashCommandGroup('marker', description='...')


@group.command(name='save', description='...')
@discord.commands.option(name='year', required=True, input_type=int, min_value=1)
@commands.check(is_authorized_guild)
async def marker_save(ctx: ApplicationContext, year: int):
    await ctx.respond(...)
```

## extension contract

every file under `apps/bot/nova_core/commands/` is an extension. the loader in `apps/bot/nova_core/client/__init__.py` calls `bot.load_extension(name)` for each module discovered via `pkgutil.iter_modules(nova_core.commands.__path__)`.

- `setup(bot: Bot)` is **synchronous**; not `async def`. pycord rejects coroutine setups.
- one positional arg, the `Bot` instance.
- register `SlashCommandGroup` with `bot.add_application_command(group)`.
- optional `teardown(bot: Bot)` for cleanup; also sync.
- a setup that raises during load aborts the whole bot startup (`_load_extensions()` calls `sys.exit(1)` on first failure).

```python
def setup(bot: Bot):
    logger.info(f'registered: {__name__}')
    bot.add_application_command(my_group)
```

### lifecycle methods on `bot`

| method | when to use |
|---|---|
| `bot.load_extension('nova_core.commands.foo')` | once at startup; called by the auto-loader. |
| `bot.reload_extension('nova_core.commands.foo')` | hot-reload after a code or config change. no code path calls this today; the db-polled reload watcher was removed, and a bridge `/reload` only re-reads config into the existing extensions. |
| `bot.unload_extension('nova_core.commands.foo')` | tear an extension down; also uncalled today. a feature toggled off through the admin api stays loaded and is gated by its config field at command time. |
| `await bot.sync_commands()` | push command tree to discord; called once in `_do_ready_init()` and again after any reload that adds or removes commands. async; only valid after `on_ready`. |

reloading **does not** push the new tree to discord on its own; pair `reload_extension` with `await bot.sync_commands()` if the command set changed.

## bot construction and intents

defined in `apps/bot/nova_core/client/core.py`; do not re-instantiate. import the singleton:

```python
from nova_core.client.core import bot
```

`nova_core/__init__.py` does **not** re-export `bot`; `from nova_core import bot` fails, and tests that patch it there patch nothing.

intents enabled in this repo: `default()` plus `message_content`, `members`, `emojis_and_stickers`, `moderation`. all four are privileged (except `emojis_and_stickers`) and must also be toggled in the discord developer portal. do not silently flip an intent off; check the portal first.

`discord.Bot` is pycord's slash-command-only bot; it does **not** inherit prefix-command behavior. don't add `command_prefix=` (that's `commands.Bot`).

## SlashCommandGroup

```python
group = SlashCommandGroup(
    'name',  # required
    description='...',
    default_member_permissions=Permissions.all(),  # discord-side perm gate
    guild_ids=[123, 456],  # optional; omit for global
)

sub = group.create_subgroup('leaderboard', 'description')  # nested group; one level deep max
```

attach commands with the group decorator, not `@bot.slash_command`:

```python
@group.command(name='set', description='...')
async def group_set(ctx: ApplicationContext, ...): ...
```

## `@discord.commands.option`

```python
@discord.commands.option(
    name='year',
    description='year number',
    input_type=int,        # str, int, bool, float, discord.Member, discord.TextChannel, ...
    required=True,
    default=None,
    min_value=1, max_value=9999,            # numeric only
    min_length=1, max_length=100,           # str only
    choices=['a', 'b'],                     # or list[OptionChoice]
    autocomplete=my_autocomplete_function,  # async callable returning list[str|OptionChoice]
)
```

decorator order matters: `@group.command(...)` outermost, then `@discord.commands.option(...)` (one per param), then `@commands.check(...)` innermost. options apply bottom-up to the function signature.

## ApplicationContext basics

| call | semantics |
|---|---|
| `await ctx.respond(content, embed=, view=, ephemeral=False)` | initial reply; must happen within 3s of invocation or discord drops it. |
| `await ctx.defer(ephemeral=False)` | reserves the response slot; gives you up to 15 minutes to call `ctx.followup.send(...)` or `ctx.edit(...)`. defer first if any awaited work might exceed 3s. |
| `await ctx.followup.send(...)` | additional messages after `respond` or `defer`. |
| `await ctx.edit(content=, embed=, view=)` | edit the original response. |
| `ctx.author`, `ctx.user` | invoker; in slash commands these are the same. |
| `ctx.guild`, `ctx.channel`, `ctx.interaction` | usual discord refs. |

**ephemeral rule (see `docs/style/command_usage.md`)**: `ephemeral=True` is only for errors and validation failures. successful responses are public; do not pass `ephemeral` at all.

## error handling

global handler is `on_application_command_error` in `apps/bot/nova_core/client/events.py`. **extension commands should raise naturally**; do not wrap every command body in a try/except. the global handler dispatches on `CheckFailure`, `UnauthorizedGuild`, `MissingPermissions`, and a generic fallback that posts to the error webhook via `attu_logging.webhook.send_to_webhook`.

if you need command-local recovery (e.g. a 404 from an external api becomes a friendly response), catch the specific exception and respond; let everything else propagate.

## embeds

prefer `make_embed(...)` from `nova_core.client.embeds` over raw `discord.Embed(...)`. the wrapper auto-applies the guild theme color and a utc timestamp; bare `discord.Embed(...)` skips both and drifts from house style. drop down to raw `discord.Embed` only when you need something the wrapper does not expose (e.g. `set_image()`).

```python
from nova_core.client.embeds import make_embed

embed = make_embed(
    'Member Joined',
    description=f'{member.mention} joined the server',
    footer=f'user id: {member.id}',
    # color, thumbnail, author_name, author_icon_url, author_url, url, timestamp are kw-only
)
embed.add_field(name='Role', value=role.mention, inline=False)
```

- `color` defaults to `theme_color()` (guild config, blurple fallback). override per-event: `color=Color.red()` for destructive, `Color.green()` for additive.
- `timestamp=True` (default) stamps now-utc. pass a `datetime` for a specific time, or `False` to omit.
- unset kwargs are omitted entirely - no empty fields rendered.
- `make_embed()` returns a regular `discord.Embed`; chain `.add_field()`, `.set_image()`, etc. as normal.

### fields

`add_field(name, value, inline=True)`. inline fields lay out three-per-row; use `inline=False` for full-width labelled blocks. fields are appended in call order. `clear_fields()`, `remove_field(i)`, `set_field_at(i, ...)`, `insert_field_at(i, ...)` all available.

### limits worth remembering

| | |
|---|---|
| title / description | 256 / 4096 |
| field name / value | 256 / 1024 |
| field count | 25 |
| total chars in one embed | 6000 |
| total chars across all embeds in one message | 6000 |
| embeds per message | 10 |

the 6000-char total counts `title + description + all field names + all field values + footer.text + author.name` combined. `len(embed)` returns this; check before sending dynamic content.

reference: `docs/style/embed_usage.md`.

## views, buttons, modals, selects

`discord.ui.View(timeout=180.0, disable_on_timeout=False)`. attach via `await ctx.respond('...', view=MyView())`. if you need `view.message` later (for `on_timeout` cleanup), grab it after responding: `view.message = await ctx.interaction.original_response()`.

### lifecycle

- `timeout=None` → persistent view; otherwise the view stops accepting interactions after `timeout` seconds.
- `on_timeout(self)` runs once when the timer elapses. always wrap any `self.message.edit(...)` in `contextlib.suppress(Exception)` because the message may have been deleted.
- `interaction_check(self, interaction)` runs before every item callback; return `False` to block. pin a view to its invoker by comparing `interaction.user.id != self._ctx.user.id` and replying ephemerally on mismatch.
- persistent views require all three: `timeout=None`, every item has a `custom_id`, and `bot.add_view(MyView())` runs in `on_ready` (or restored from db, see `_restore_wiki_views` in `events.py`).

### project view patterns

- **`WikiLinkView`** — single static link button, `timeout=None`, no callbacks. use when you only need a url button on a response.
- **`WikiLookupView`** — paginated results (`timeout=1800`), invoker-pinned via `interaction_check`, rebuilds buttons on every state change via `self.clear_items()` + `self._build_buttons()`. `on_timeout` disables all items.
- **`EggGiftOfferView`** — accept/decline flow with state.

prefer dynamic construction (`add_item(discord.ui.Button(...))` plus `btn.callback = self._cb`) over `@discord.ui.button` decorators whenever a button's label, `disabled`, or count depends on view state. the `clear_items()` + rebuild pattern is the cleanest way to update buttons after state changes.

### disabling

- pre-disable: `discord.ui.Button(..., disabled=True)` or `@discord.ui.button(..., disabled=True)`.
- disable one on press: `button.disabled = True; await interaction.response.edit_message(view=self)`.
- disable all (on press or timeout): `self.disable_all_items()` then edit the message.

### rows

`row` kwarg `0-4`. each row holds 5 slots; a button takes 1, a select takes a full row. keep paginator nav (prev/next) on the same row as the canonical action where possible (see `WikiLookupView._build_buttons`).

### interaction.response vs followup

- `interaction.response.send_message(...)` — first reply; must happen within 3s.
- `interaction.response.defer()` — extend the deadline before any awaited work that might exceed 3s. defer first if a callback fetches data.
- `interaction.response.edit_message(...)` — update the message the component lives on. only valid before defer/respond.
- after `defer()` or `send_message()`: only `interaction.followup.send(...)` and `interaction.edit_original_response(...)` work; `response.*` calls raise.

### modals and selects

- `discord.ui.Modal` with `discord.ui.InputText` items; submit via `await ctx.send_modal(MyModal())` from a slash command, or `await interaction.response.send_modal(...)` from a component callback.
- `discord.ui.Select` (or subclass and override `callback`); a select takes a full row (5 slots).

reference: `docs/style/button_usage.md`.

## events

register with `@bot.event` (one handler per event name) or `@bot.listen()` (multiple handlers stack). raw events (`on_raw_message_edit`, `on_raw_reaction_add`, etc.) fire even when the message isn't in cache; prefer them for anything older than the current session.

```python
@bot.listen()
async def on_raw_reaction_add(payload: RawReactionActionEvent): ...
```

## footguns and common confusions

- `@discord.commands.check(...)` does not exist. always `@commands.check(...)` from `discord.ext.commands`.
- `discord.Bot` (pycord) ≠ `commands.Bot` (discord.py-style prefix bot). this repo uses `discord.Bot`.
- `setup(bot)` is sync. async `setup` is a discord.py 2.x thing; pycord refuses it.
- `bot.tree` is discord.py's command tree; pycord uses `bot.application_commands` and `bot.add_application_command(...)`.
- `app_commands.command` / `app_commands.Group` are discord.py imports; pycord equivalents are `discord.slash_command` and `discord.SlashCommandGroup`.
- 3s response window: any awaited io before `respond` or `defer` risks the interaction timing out.
- changing the command tree (new command, renamed group, changed option) requires `await bot.sync_commands()` to take effect in the discord client.
- discord snowflake ids exceed js's safe int range; serialize them as strings in any json response.
- never start a discord interaction during testing; `CLAUDE.md` rule #2 forbids it without explicit user approval.

## quick links

- pycord docs (stable): https://docs.pycord.dev/en/stable/
- pycord guide: https://guide.pycord.dev/
- pycord github: https://github.com/Pycord-Development/pycord
- repo conventions: `docs/style/command_usage.md`, `docs/style/embed_usage.md`, `docs/style/button_usage.md`, `docs/style/view_usage.md`, `docs/style/select_usage.md`
