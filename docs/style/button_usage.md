# pycord ui components - deep api reference

project-specific patterns (the `WikiLinkView` / `WikiLookupView` / `EggGiftOfferView` shapes, dynamic `clear_items()` rebuild, `interaction.response` vs `followup` rules, persistent-view restoration) live in the pycord skill (`.claude/skills/pycord/SKILL.md` → `views, buttons, modals, selects`). this file is the deeper api reference - decorator vs `add_item` syntax, full button styles, action-row positioning details, persistent-view requirements.

source: [pycord guide - buttons](https://guide.pycord.dev/interactions/ui-components/buttons).

a view holds up to 5 rows of 5 slots each (max 25 buttons). only one view per message.

---

## decorator syntax (simple cases)

```python
class MyView(discord.ui.View):
    @discord.ui.button(label='Click me!', style=discord.ButtonStyle.primary, emoji='😎')
    async def button_callback(self, button, interaction):
        await interaction.response.send_message('clicked')


@bot.slash_command()
async def button_demo(ctx):
    await ctx.respond('press it', view=MyView())
```

prefer `add_item(discord.ui.Button(...))` with `btn.callback = self._cb` over the decorator whenever a button's label, `disabled`, or count depends on view state. see the `WikiLookupView` pattern in the pycord skill.

---

## button styles

| name | constant | color |
|---|---|---|
| primary | `discord.ButtonStyle.primary` / `.blurple` | blurple |
| secondary | `discord.ButtonStyle.secondary` / `.grey` / `.gray` | grey |
| success | `discord.ButtonStyle.success` / `.green` | green |
| danger | `discord.ButtonStyle.danger` / `.red` | red |
| link | `discord.ButtonStyle.link` / `.url` | grey (no callback fires; opens url) |

---

## action rows

`row=0..4` controls placement. each row holds 5 slots; a button is 1 slot, a select is 5 (full row).

```python
@discord.ui.button(label='Button 1', row=0, style=discord.ButtonStyle.primary)
async def first(self, button, interaction): ...


@discord.ui.button(label='Button 2', row=1, style=discord.ButtonStyle.primary)
async def second(self, button, interaction): ...
```

omit `row=` and pycord auto-assigns based on declaration order.

---

## disabling

```python
# pre-disabled at construction
@discord.ui.button(label='disabled', disabled=True, style=...)
async def cb(self, button, interaction): ...


# disable one on press
async def cb(self, button, interaction):
    button.disabled = True
    button.label = 'no more presses'
    await interaction.response.edit_message(view=self)


# disable all (on press or in on_timeout)
async def cb(self, button, interaction):
    self.disable_all_items()
    await interaction.response.edit_message(view=self)
```

---

## timeouts

```python
class MyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)  # seconds

    async def on_timeout(self):
        self.disable_all_items()
        with contextlib.suppress(Exception):  # message may have been deleted
            await self.message.edit(view=self)
```

if `on_timeout` is not defined, buttons silently stop responding after the timer elapses.

---

## persistent views

persist across bot restarts. requires **all three**:

1. `timeout=None`
2. every item has a `custom_id`
3. `bot.add_view(MyView())` runs in `on_ready` (or restored from db state)

```python
@bot.event
async def on_ready():
    bot.add_view(MyView())


class MyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='press', custom_id='my-btn-1', style=discord.ButtonStyle.primary)
    async def cb(self, button, interaction):
        await interaction.response.send_message('pressed', ephemeral=True)
```

see `_restore_wiki_views` in `apps/bot/nova_core/client/events.py` for the project's restoration pattern.

---

## modals and selects

```python
class MyModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title='example')
        self.add_item(discord.ui.InputText(label='name'))

    async def callback(self, interaction):
        await interaction.response.send_message(self.children[0].value)


# from a slash command
await ctx.send_modal(MyModal())

# from a component callback
await interaction.response.send_modal(MyModal())
```

`discord.ui.Select` (or a subclass with overridden `callback`) takes a full row.

---

## misc

- buttons require no special bot or server permissions
- a select takes all 5 slots in its row; budget accordingly
- `add_item()` lets you mix dynamic and decorated items in the same view
