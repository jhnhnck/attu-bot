# Discord Embed Usage (Pycord)

Reference for constructing and sending Discord embeds via `discord.Embed`.

---

## `make_embed()` Wrapper (preferred)

Most bot code should use the project wrapper from `attubot/client/embeds.py` rather than constructing `discord.Embed` directly. It auto-applies the guild theme color and timestamps.

```python
from attubot.client.embeds import make_embed

embed = make_embed(
    'Member Joined',
    description=f'{member.mention} joined the server',
    color=discord.Color.green(),  # optional - defaults to theme_color()
    footer=f'user id: {member.id}',
    author_name='display name',
    author_icon_url='https://cdn.discordapp.com/...',
    author_url='https://example.com',
    thumbnail='https://example.com/icon.png',
    url='https://example.com',    # makes the title a hyperlink
    timestamp=True,               # default - uses current utc time
)
```

### signature

```python
def make_embed(
    title: str | None = None,
    *,
    description: str | None = None,
    url: str | None = None,
    color: int | Color | None = None,
    footer: str | None = None,
    thumbnail: str | None = None,
    author_name: str | None = None,
    author_icon_url: str | None = None,
    author_url: str | None = None,
    timestamp: bool | datetime = True,
) -> Embed:
```

All params are keyword-only except `title`. Unset params are omitted from the embed entirely.

### `timestamp` behavior

| value | result |
|---|---|
| `True` (default) | current UTC time |
| `False` | no timestamp |
| `datetime` instance | that specific time |

### adding fields after construction

`make_embed()` returns a regular `discord.Embed` - call `.add_field()` on it normally:

```python
embed = make_embed('Role Updated', footer=f'role id: {role.id}')
embed.add_field(name='Role', value=role.mention, inline=False)
embed.add_field(name='Before', value=old_name, inline=True)
embed.add_field(name='After', value=new_name, inline=True)
```

### theme color

`color` defaults to `theme_color()` from `attubot/util.py`, which reads the guild theme from config and falls back to discord blurple (`0x5865F2`). Pass an explicit `color` to override - e.g. `color=Color.red()` for destructive events.

---

## Raw `discord.Embed` (reference)

Use directly only when you need something `make_embed()` doesn't support (e.g. `set_image()`).

```python
import discord

embed = discord.Embed(
    title='embed title',          # max 256 chars
    description='embed body',     # max 4096 chars
    url='https://example.com',    # makes title a hyperlink
    color=discord.Color.blurple(), # or int: 0x5865F2
    timestamp=datetime.now(UTC),  # adds a timestamp to the footer row
)
```

All constructor params are optional. You can also set `title`, `description`, `url`, etc. as attributes after construction.

---

## Setter Methods (chainable)

All setters return the embed instance, so you can chain them:

```python
embed = (
    discord.Embed(title='example')
    .set_author(name='attu bot', url='https://attu.wiki', icon_url='https://...')
    .set_footer(text='footer text', icon_url='https://...')
    .set_image(url='https://example.com/banner.png')
    .set_thumbnail(url='https://example.com/icon.png')
    .add_field(name='field 1', value='some value', inline=False)
    .add_field(name='field 2', value='another value', inline=True)
)
```

### `set_author(*, name, url=None, icon_url=None)`
Adds the small author row at the top. `name` is required, max 256 chars.

### `set_footer(*, text=None, icon_url=None)`
Adds the footer row at the bottom. `text` max 2048 chars. Only HTTP(S) for `icon_url`.

### `set_image(*, url)`
Large image below the description/fields. Pass `None` to remove.

### `set_thumbnail(*, url)`
Small image anchored to the top-right. Pass `None` to remove.

---

## Fields

```python
embed.add_field(name='label', value='content', inline=True)
embed.insert_field_at(0, name='prepend', value='...', inline=False)
embed.set_field_at(1, name='updated', value='new content', inline=True)
embed.remove_field(0)   # silently ignored if index out of range
embed.clear_fields()
```

`inline=True` causes adjacent fields to appear side-by-side (Discord groups them in rows of 3). Useful for columns of stats.

You can also use `EmbedField` objects directly:

```python
from discord import EmbedField

embed.append_field(EmbedField(name='key', value='val', inline=False))
```

---

## Remove Helpers

```python
embed.remove_author()
embed.remove_footer()
embed.remove_image()
embed.remove_thumbnail()
```

---

## Reading Back Values

All component accessors return a typed dataclass or `None`:

```python
embed.author     # EmbedAuthor | None  (.name, .url, .icon_url, .proxy_icon_url)
embed.footer     # EmbedFooter | None  (.text, .icon_url, .proxy_icon_url)
embed.image      # EmbedMedia  | None  (.url, .proxy_url, .height, .width)
embed.thumbnail  # EmbedMedia  | None
embed.video      # EmbedMedia  | None  (read-only; set by Discord for non-rich embeds)
embed.provider   # EmbedProvider | None (.name, .url; also read-only)
embed.fields     # list[EmbedField]    (.name, .value, .inline)
```

`len(embed)` returns the total character count across all text fields - useful for checking against the 6000 char cap before sending.

---

## Discord API Limits

Violating any of these returns a `400 Bad Request`:

| field | limit |
|---|---|
| `title` | 256 chars |
| `description` | 4096 chars |
| `author.name` | 256 chars |
| `footer.text` | 2048 chars |
| `field.name` | 256 chars |
| `field.value` | 1024 chars |
| number of fields | 25 |
| total chars across all text fields (single embed) | 6000 |
| total chars across **all embeds in one message** | 6000 |
| embeds per message | 10 |

The 6000 char total is the most common surprise - it counts `title + description + all field names + all field values + footer.text + author.name` combined.

Leading/trailing whitespace is trimmed before counting.

---

## Fields You Cannot Set

These are filled in by Discord and are ignored if you provide them:

- `type` - always `"rich"` for bot-created embeds
- `provider` - set automatically for link embeds
- `video` - set automatically for video embeds
- `proxy_url`, `height`, `width` on image/thumbnail

---

## Sending an Embed

```python
@bot.slash_command(name='info')
async def info(ctx: discord.ApplicationContext):
    embed = make_embed(
        'Attu Bot Info',
        description='timekeeping for the attu project',
        footer='attu-bot v1.0',
    )
    embed.add_field(name='guilds', value=str(len(ctx.bot.guilds)), inline=True)
    await ctx.respond(embed=embed)
```

To send multiple embeds at once (up to 10):

```python
await ctx.respond(embeds=[embed_a, embed_b])
```

To send alongside a regular message:

```python
await ctx.respond(content='here is the info:', embed=embed)
```

---

## Dict Roundtrip

```python
data = embed.to_dict()   # -> dict[str, ...]
embed2 = discord.Embed.from_dict(data)
```

Useful for caching, logging, or constructing embeds from stored templates.

---

## Sources

- [Pycord v2.7 - `discord.Embed`](https://docs.pycord.dev/en/v2.7.0/api/data_classes.html#embed)
- [Discord API - Embed Object](https://discord.com/developers/docs/resources/message#embed-object)
