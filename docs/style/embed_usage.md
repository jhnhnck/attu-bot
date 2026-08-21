# discord embed - deep api reference

project-specific rules (always use `make_embed()`, theme color, field conventions, the 6000-char total cap) live in the pycord skill (`.claude/skills/pycord/SKILL.md` → `embeds`). this file is the deeper api reference for cases the wrapper does not cover - drop down to raw `discord.Embed` only when you need something `make_embed()` does not expose.

source: [pycord v2.7 - `discord.Embed`](https://docs.pycord.dev/en/v2.7.0/api/data_classes.html#embed); [discord api - embed object](https://discord.com/developers/docs/resources/message#embed-object).

---

## raw construction

```python
import discord

embed = discord.Embed(
    title='embed title',  # max 256 chars
    description='embed body',  # max 4096 chars
    url='https://example.com',  # makes title a hyperlink
    color=discord.Color.blurple(),  # or int: 0x5865F2
    timestamp=datetime.now(UTC),  # adds a timestamp to the footer row
)
```

all constructor params are optional. `title`, `description`, `url`, `color`, `timestamp` are also settable as attributes after construction.

---

## chainable setters

all setters return the embed instance:

```python
embed = (
    discord
    .Embed(title='example')
    .set_author(name='attu bot', url='https://attu.wiki', icon_url='https://...')
    .set_footer(text='footer text', icon_url='https://...')
    .set_image(url='https://example.com/banner.png')
    .set_thumbnail(url='https://example.com/icon.png')
    .add_field(name='field 1', value='some value', inline=False)
    .add_field(name='field 2', value='another value', inline=True)
)
```

| setter | signature | notes |
|---|---|---|
| `set_author` | `(*, name, url=None, icon_url=None)` | `name` required, max 256 chars |
| `set_footer` | `(*, text=None, icon_url=None)` | `text` max 2048 chars; http(s) only for `icon_url` |
| `set_image` | `(*, url)` | full-width image below description/fields; `None` removes |
| `set_thumbnail` | `(*, url)` | small image, top-right; `None` removes |

remove helpers: `embed.remove_author()`, `embed.remove_footer()`, `embed.remove_image()`, `embed.remove_thumbnail()`.

---

## fields

```python
embed.add_field(name='label', value='content', inline=True)
embed.insert_field_at(0, name='prepend', value='...', inline=False)
embed.set_field_at(1, name='updated', value='new content', inline=True)
embed.remove_field(0)  # silently ignored if index out of range
embed.clear_fields()
```

`inline=True` groups adjacent inline fields into rows of 3. you can also append `EmbedField` objects directly:

```python
from discord import EmbedField

embed.append_field(EmbedField(name='key', value='val', inline=False))
```

---

## reading back values

all component accessors return a typed dataclass or `None`:

| attribute | type | fields |
|---|---|---|
| `embed.author` | `EmbedAuthor \| None` | `.name`, `.url`, `.icon_url`, `.proxy_icon_url` |
| `embed.footer` | `EmbedFooter \| None` | `.text`, `.icon_url`, `.proxy_icon_url` |
| `embed.image` | `EmbedMedia \| None` | `.url`, `.proxy_url`, `.height`, `.width` |
| `embed.thumbnail` | `EmbedMedia \| None` | same as image |
| `embed.video` | `EmbedMedia \| None` | read-only; set by discord for non-rich embeds |
| `embed.provider` | `EmbedProvider \| None` | `.name`, `.url`; read-only |
| `embed.fields` | `list[EmbedField]` | `.name`, `.value`, `.inline` |

`len(embed)` returns the total character count across all text fields - useful for checking against the 6000 char cap before sending. leading/trailing whitespace is trimmed before counting.

---

## fields you cannot set

these are filled in by discord and are ignored if you provide them:

- `type` - always `"rich"` for bot-created embeds
- `provider` - set automatically for link embeds
- `video` - set automatically for video embeds
- `proxy_url`, `height`, `width` on image/thumbnail

---

## sending

```python
await ctx.respond(embed=embed)  # single
await ctx.respond(embeds=[embed_a, embed_b])  # up to 10
await ctx.respond(content='intro text:', embed=embed)
```

---

## dict roundtrip

```python
data = embed.to_dict()  # -> dict[str, ...]
embed2 = discord.Embed.from_dict(data)
```

useful for caching, logging, or constructing embeds from stored templates.
