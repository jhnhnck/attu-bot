# discord select menus - project patterns

project-specific patterns for `discord.ui.Select` and `discord.SelectOption`. the raw api surface (row placement, slot budget) is in `button_usage.md`.

---

## structure

always subclass `discord.ui.Select` as a private class. never instantiate `discord.ui.Select` directly in a view — you need the `callback` override.

```python
class _EggSelectMenu(discord.ui.Select):
    def __init__(self, all_options, offset, from_id, ...):
        page = all_options[offset:offset + PAGE_SIZE]
        super().__init__(placeholder='pick an egg to give', options=page, min_values=1, max_values=1)
        # store state as instance attrs after super().__init__
        self.all_options = all_options
        self.offset = offset
        self.from_id = from_id
        ...

    async def callback(self, interaction: discord.Interaction):
        ...
```

the view wraps the select:

```python
class EggSelectView(discord.ui.View):
    def __init__(self, all_options, offset, ...):
        super().__init__(timeout=120)
        self.add_item(_EggSelectMenu(all_options, offset, ...))
```

---

## hard limits

| limit | value | notes |
|---|---|---|
| options per select | 25 | discord hard cap; slice before passing to `super().__init__` |
| option label | 100 chars | truncate with `label=name[:100]` |
| option value | 100 chars | must be unique within the menu |
| slots per row | 5 | a select takes all 5; no other items can share the row |

---

## options

construct `SelectOption` objects before calling `super().__init__`. pass the list as `options=`.

```python
options = [
    discord.SelectOption(label=t['name'][:100], value=t['id'])
    for t in trees[:25]
]
super().__init__(placeholder='select a tree...', options=options)
```

`SelectOption` fields:
- `label` — displayed text; max 100 chars
- `value` — string returned in `self.values[0]`; max 100 chars; must be unique
- `description` — optional subtitle line; max 100 chars
- `emoji` — optional emoji prefix
- `default` — marks the option pre-selected (cosmetic only)

---

## value encoding

when `value` needs to carry structured data, encode it as a prefixed string. decode in `callback` by splitting on the separator.

```python
# construction
discord.SelectOption(label='a thing', value='unhatched:common')

# callback
prefix, key = self.values[0].split(':', 1)
```

reserve a sentinel value for pagination (see below). keep the separator consistent — `:` is the project convention.

---

## pagination beyond 25 options

when the full option list exceeds 25, render a page of 24 real options plus a "more..." sentinel as the 25th. the sentinel value encodes the next offset.

```python
PAGE_SIZE = 24

page = all_options[offset:offset + PAGE_SIZE]
if len(all_options) > offset + PAGE_SIZE:
    page = [*page, discord.SelectOption(label='more...', value=f'more:{offset + PAGE_SIZE}')]
super().__init__(options=page, ...)
```

in `callback`, detect the sentinel and replace the view with a new page:

```python
async def callback(self, interaction):
    value = self.values[0]
    if value.startswith('more:'):
        new_offset = int(value[5:])
        new_view = EggSelectView(self.all_options, new_offset, ...)
        await interaction.response.edit_message(content='pick one:', view=new_view)
        return
    # handle real selection
    ...
```

---

## user guard

same rule as views — check `interaction.user.id` at the top of `callback` if the select is targeted at a specific user.

```python
async def callback(self, interaction):
    if interaction.user.id != self.from_id:
        await interaction.response.send_message('not yours!', ephemeral=True)
        return
```

---

## response in callback

always call exactly one `interaction.response` method. if the response needs a network fetch, call `defer()` first, then `edit_original_response()`.

```python
async def callback(self, interaction):
    await interaction.response.defer()
    result = await some_async_call()
    await interaction.edit_original_response(content=result, view=None)
```

pass `view=None` when the selection is final and the menu should disappear.

---

## metadata

```yaml
last_updated: 2026-08-23
```
