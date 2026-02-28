# pycord buttons reference

source: https://guide.pycord.dev/interactions/ui-components/buttons

buttons are a discord ui component that live inside a `discord.ui.View`. each view can have up to 5 rows of 5 slots each, for a max of 25 buttons per message. only one view per message is allowed.

---

## project view patterns

### `WikiLinkView` - simple link button

a minimal view with a single persistent link button. use this pattern when you only need to attach a url button to a response.

```python
class WikiLinkView(discord.ui.View):
    """simple view with a single link button to open a wiki page"""

    def __init__(self, url: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label='Open Wiki!', style=discord.ButtonStyle.link, url=url, row=0))
```

- `timeout=None` - persists across restarts (no state to restore, so this is fine)
- `add_item()` with a `discord.ui.Button` instance instead of a decorator - use this pattern when buttons are constructed dynamically
- link buttons don't fire a callback; `url` takes the user directly to the page

### `WikiLookupView` - paginated results with prev/next

a stateful view for cycling through a list of results. shows the relevant page in the pattern for restricting interactions to the original invoker and graceful timeout.

```python
class WikiLookupView(discord.ui.View):
    def __init__(self, ctx: ApplicationContext, pages: list[SearchResult], ...):
        super().__init__(timeout=_VIEW_TIMEOUT)  # 1800 seconds (30 min)
        self._ctx = ctx
        self._index = 0
        ...
        self._build_buttons()

    def _build_buttons(self):
        """clear and rebuild buttons for the current state"""
        self.clear_items()

        # link button is always first
        self.add_item(discord.ui.Button(label='Open Wiki!', style=discord.ButtonStyle.link, url=self._current_url, row=0))

        total = len(self._pages)
        if total > 1:
            prev_btn = discord.ui.Button(
                label='Previous',
                style=discord.ButtonStyle.secondary,
                disabled=self._index == 0,
                row=0,
            )
            prev_btn.callback = self._prev_callback  # assign callback directly
            self.add_item(prev_btn)

            next_btn = discord.ui.Button(
                label=f'Next ({self._index + 1}/{total})',
                style=discord.ButtonStyle.primary,
                disabled=self._index >= total - 1,
                row=0,
            )
            next_btn.callback = self._next_callback
            self.add_item(next_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # restrict buttons to the original command invoker
        if interaction.user.id != self._ctx.user.id:
            await interaction.response.send_message('only the command executor can use these buttons', ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.disable_all_items()
        with contextlib.suppress(Exception):
            await self.message.edit(view=self)

    async def _prev_callback(self, interaction: discord.Interaction):
        self._index -= 1
        await self._fetch_and_update(interaction)

    async def _next_callback(self, interaction: discord.Interaction):
        self._index += 1
        await self._fetch_and_update(interaction)

    async def _fetch_and_update(self, interaction: discord.Interaction):
        await interaction.response.defer()  # defer first - fetching takes time
        # ... fetch data, update self._current_embed and self._current_url ...
        self._build_buttons()  # rebuild to update labels/disabled state
        await interaction.edit_original_response(embed=self._current_embed, view=self)
```

key points:
- call `self.clear_items()` then rebuild in `_build_buttons()` each time state changes - this is the cleanest way to update button labels/disabled state
- assign `.callback` on a button instance to wire it without decorators
- `interaction_check` is called automatically before any button callback - return `False` to block
- `on_timeout` - always suppress exceptions from `self.message.edit()`; the message may have been deleted
- `interaction.response.defer()` before any async work to avoid the 3-second discord timeout

---

## basic usage

```python
class MyView(discord.ui.View):
    @discord.ui.button(label='Click me!', style=discord.ButtonStyle.primary, emoji='😎')
    async def button_callback(self, button, interaction):
        await interaction.response.send_message('You clicked the button!')

@bot.slash_command()
async def button(ctx):
    await ctx.respond('This is a button!', view=MyView())
```

---

## button styles

| name      | constant                                                    | color   |
|-----------|-------------------------------------------------------------|---------|
| primary   | `discord.ButtonStyle.primary` / `.blurple`                  | blurple |
| secondary | `discord.ButtonStyle.secondary` / `.grey` / `.gray`         | grey    |
| success   | `discord.ButtonStyle.success` / `.green`                    | green   |
| danger    | `discord.ButtonStyle.danger` / `.red`                       | red     |
| link      | `discord.ButtonStyle.link` / `.url`                         | grey    |

set via the `style` kwarg on `@discord.ui.button(...)`.

---

## action rows (positioning)

use the `row` kwarg (0-4) to control which row a button appears in. default is automatic ordering.

```python
@discord.ui.button(label='Button 1', row=0, style=discord.ButtonStyle.primary)
async def first_button_callback(self, button, interaction): ...

@discord.ui.button(label='Button 2', row=1, style=discord.ButtonStyle.primary)
async def second_button_callback(self, button, interaction): ...
```

---

## disabling buttons

### pre-disabled (on creation)

```python
@discord.ui.button(label='A button', style=discord.ButtonStyle.primary, disabled=True)
async def button_callback(self, button, interaction): ...
```

### disable on press (single button)

```python
async def button_callback(self, button, interaction):
    button.disabled = True
    button.label = 'No more pressing!'
    await interaction.response.edit_message(view=self)
```

### disable all on press

```python
async def button_callback(self, button, interaction):
    self.disable_all_items()
    await interaction.response.edit_message(view=self)
```

---

## timeouts

specify how long (in seconds) before the view stops accepting interactions. override `on_timeout` to handle cleanup.

```python
class MyView(discord.ui.View):
    async def on_timeout(self):
        self.disable_all_items()
        await self.message.edit(content='Timed out.', view=self)

    @discord.ui.button(...)
    async def button_callback(self, button, interaction): ...

# pass timeout when constructing the view
await ctx.send('Press the button!', view=MyView(timeout=30))
```

or set it in `__init__`:

```python
def __init__(self):
    super().__init__(timeout=10)
```

note: if `on_timeout` is not defined, buttons simply stop working after the timeout.

---

## persistent views

persist across bot restarts. requires:
1. `timeout=None`
2. every button must have a `custom_id`
3. register the view in `on_ready` via `bot.add_view(MyView())`

```python
@bot.event
async def on_ready():
    bot.add_view(MyView())

class MyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='A button', custom_id='button-1', style=discord.ButtonStyle.primary)
    async def button_callback(self, button, interaction):
        await interaction.response.send_message('Button was pressed', ephemeral=True)
```

---

## miscellaneous

- buttons require no special bot or server permissions
- select menus take up all 5 slots in a row; buttons take 1 slot each
- use `add_item()` on a view to add dynamically subclassed button instances instead of decorators
