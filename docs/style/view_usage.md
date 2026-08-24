# discord views - project patterns

project-specific patterns for `discord.ui.View` subclasses. the raw api reference (timeout, persistent-view requirements, decorator vs `add_item`, button styles) lives in `docs/style/button_usage.md`.

---

## naming

| class | name pattern | example |
|---|---|---|
| public view | `<Noun><Purpose>View` | `EggGiftOfferView`, `WikiLookupView` |
| private select component | `_<Noun>SelectMenu` | `_EggSelectMenu`, `_TreeSelectMenu` |

use a leading underscore on any `discord.ui.Select` or `discord.ui.Button` subclass that is an internal implementation detail — not directly instantiated by command handlers.

---

## timeout

always pass an explicit timeout. never rely on the pycord default (180s).

| pattern | timeout | use when |
|---|---|---|
| short-lived ephemeral | `30` - `120` | picker/confirmation shown to one user |
| long-lived offer | `1800` - `3600` | offer or prompt shown in a public channel |
| persistent across reboots | `None` | paginated results stored in db |

always implement `on_timeout` when the view posts a public-channel message. the message must be cleaned up — edit out the buttons and replace with a summary line.

```python
async def on_timeout(self):
    if self.message:
        with contextlib.suppress(discord.NotFound):
            await self.message.edit(content=f'{self.to_mention} took too long', view=None)
```

store the message handle in `self.message` immediately after sending, before awaiting anything else:

```python
msg = await ctx.channel.send(content, view=offer_view)
offer_view.message = msg
```

---

## state

keep all view state as instance attributes set in `__init__`. do not read from `interaction` to reconstruct state in a callback — it may have changed between renders.

```python
class EggGiftOfferView(discord.ui.View):
    def __init__(self, egg, from_id, from_mention, to_id, to_mention, ...):
        super().__init__(timeout=3600)
        self.egg = egg
        self.from_id = from_id
        ...
        self.message: discord.Message | None = None
```

---

## user guard

when a view is targeted at a specific user, check `interaction.user.id` at the top of every callback. respond ephemeral and return — do not raise.

```python
async def accept(self, button, interaction):
    if interaction.user.id != self.to_id:
        await interaction.response.send_message('not for you!', ephemeral=True)
        return
    ...
```

prefer `interaction_check` when the guard applies uniformly to all items in the view:

```python
async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self._invoker_user_id:
        await interaction.response.send_message("those aren't yours to press", ephemeral=True)
        return False
    return True
```

---

## dynamic button rebuild

when button state depends on view data (disabled flag, label with count, url that changes), use `clear_items()` + `add_item()` in a `_build_buttons()` helper rather than decorator-defined buttons. call `_build_buttons()` from `__init__` and from every callback before editing the message.

```python
def _build_buttons(self) -> None:
    self.clear_items()
    self.add_item(discord.ui.Button(label='Open Wiki!', style=discord.ButtonStyle.link, url=self._current_url, row=0))
    if len(self._pages) > 1:
        prev_btn = discord.ui.Button(
            label='Previous',
            style=discord.ButtonStyle.secondary,
            disabled=self._index == 0,
            custom_id=f'wiki_prev_{self._message_id}',
            row=0,
        )
        prev_btn.callback = self._prev_callback
        self.add_item(prev_btn)
```

use `.callback = self._method` to attach callbacks to dynamically constructed buttons. decorator syntax only works on class-level defined items.

---

## stopping

call `self.stop()` when a one-shot interaction completes (accepted, declined, selection made). this releases the internal waiter immediately instead of waiting for timeout.

```python
async def accept(self, button, interaction):
    ...
    self.stop()
    await interaction.response.edit_message(content='sent!', view=None)
```

pass `view=None` in the response edit to remove the buttons from discord after stopping.

---

## persistent views

see `button_usage.md` for the three requirements (timeout=None, custom_id on every item, `bot.add_view()` on ready). the project pattern for per-message restoration is in `nova_core.client.events` - look at how wiki view restoration works there before writing a new persistent view.

---

## metadata

```yaml
last_updated: 2026-08-23
```
