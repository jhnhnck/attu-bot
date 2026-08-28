# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.eggs | egg game slash commands."""

from typing import cast

import discord
import structlog
from discord import ApplicationCommand, ApplicationContext, Bot, SlashCommandGroup

from nova_core.client.core import config
from nova_core.client.embeds import make_embed, ui_emoji
from nova_core.eggs import hatching
from nova_core.eggs.documents import EggDocument


logger = structlog.stdlib.get_logger(__name__)

eggs_group = SlashCommandGroup('eggs', description='egg collection game')
leaderboard_group = eggs_group.create_subgroup('leaderboard', 'Egg leaderboards')

_give_filter_choices = ['hatched', 'unhatched']
_give_page_size = 24


# --- Views ---


def _offer_text(from_mention: str, to_mention: str, egg: EggDocument, egg_jump_url: str) -> str:
    """Build the public offer message content."""
    if egg.hatched:
        creature = egg.result or '?'
        content = f'{from_mention} wants to give {to_mention} a {creature}. accept?'
    else:
        from nova_core.eggs.hatching import _egg_emoji_str

        emoji = _egg_emoji_str(egg.rarity)
        content = f'{from_mention} wants to give {to_mention} a {emoji} {egg.rarity} egg. accept?'
    if egg_jump_url:
        content += f'\n{egg_jump_url}'
    return content


class EggGiftOfferView(discord.ui.View):
    """Public offer message with Accept/Decline buttons for egg gifting."""

    def __init__(self, egg: EggDocument, from_id: int, from_mention: str, to_id: int, to_mention: str, to_display: str, guild_id: int):
        super().__init__(timeout=3600)
        self.egg = egg
        self.from_id = from_id
        self.from_mention = from_mention
        self.to_id = to_id
        self.to_mention = to_mention
        self.to_display = to_display
        self.guild_id = guild_id
        self.message: discord.Message | None = None

    @discord.ui.button(label='Decline', style=discord.ButtonStyle.secondary)
    async def decline(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.to_id:
            await interaction.response.send_message(f'not for you! {ui_emoji("crackerpeaty")}', ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(content=f'{self.to_mention} said no', view=None)

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.primary)
    async def accept(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.to_id:
            await interaction.response.send_message(f'not for you! {ui_emoji("crackerpeaty")}', ephemeral=True)
            return
        self.stop()
        try:
            new_jump_url = await hatching.transfer_egg(
                guild_id=self.guild_id,
                egg_id=self.egg.egg_id,
                from_user_id=self.from_id,
                to_user_id=self.to_id,
                to_username=self.to_display,
            )
        except ValueError:
            await interaction.response.edit_message(content='this egg is no longer available', view=None)
            return
        await interaction.response.edit_message(content=f'sent! {new_jump_url}', view=None)

    async def on_timeout(self):
        import contextlib

        if self.message:
            with contextlib.suppress(discord.NotFound):
                await self.message.edit(content=f'{self.to_mention} took too long', view=None)


class _EggSelectMenu(discord.ui.Select):
    """Select menu populated with a user's unique eggs for gifting."""

    def __init__(self, all_options: list[discord.SelectOption], offset: int, from_id: int, from_mention: str, to_id: int, to_mention: str, to_display: str, guild_id: int):
        self.all_options = all_options
        self.offset = offset
        self.from_id = from_id
        self.from_mention = from_mention
        self.to_id = to_id
        self.to_mention = to_mention
        self.to_display = to_display
        self.guild_id = guild_id
        page = all_options[offset : offset + _give_page_size]
        if len(all_options) > offset + _give_page_size:
            page = [*page, discord.SelectOption(label='more...', value=f'more:{offset + _give_page_size}')]
        super().__init__(placeholder='pick an egg to give', options=page, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.from_id:
            await interaction.response.send_message(f'not yours! {ui_emoji("crackerpeaty")}', ephemeral=True)
            return

        value = self.values[0]

        if value.startswith('more:'):
            new_offset = int(value[5:])
            new_view = EggSelectView(self.all_options, new_offset, self.from_id, self.from_mention, self.to_id, self.to_mention, self.to_display, self.guild_id)
            await interaction.response.edit_message(content='pick an egg to give:', view=new_view)
            return

        prefix, key = value.split(':', 1)

        from nova_core.eggs.hatching import _egg_repo, _egg_user_repo

        if prefix == 'unhatched':
            egg = await _egg_repo.get_oldest_unhatched_by_rarity(self.guild_id, self.from_id, key)
        else:
            egg = await _egg_repo.get_oldest_hatched_by_result(self.guild_id, self.from_id, key)

        if egg is None:
            await interaction.response.edit_message(content='that egg is no longer available', view=None)
            return

        from_user_doc = await _egg_user_repo.get(self.guild_id, self.from_id)
        egg_jump_url = ''
        if from_user_doc and from_user_doc.thread_id and egg.message_id:
            egg_jump_url = f'https://discord.com/channels/{self.guild_id}/{from_user_doc.thread_id}/{egg.message_id}'

        offer_content = _offer_text(self.from_mention, self.to_mention, egg, egg_jump_url)
        offer_view = EggGiftOfferView(egg, self.from_id, self.from_mention, self.to_id, self.to_mention, self.to_display, self.guild_id)
        offer_msg = await interaction.channel.send(offer_content, view=offer_view)
        offer_view.message = offer_msg

        await interaction.response.edit_message(content='offer sent!', view=None)


class EggSelectView(discord.ui.View):
    """Ephemeral view wrapping _EggSelectMenu."""

    def __init__(self, all_options: list[discord.SelectOption], offset: int, from_id: int, from_mention: str, to_id: int, to_mention: str, to_display: str, guild_id: int):
        super().__init__(timeout=120)
        self.add_item(_EggSelectMenu(all_options, offset, from_id, from_mention, to_id, to_mention, to_display, guild_id))


# --- Commands ---


@discord.slash_command(name='egg', description='Collect an egg!')
async def egg_command(ctx: ApplicationContext):
    await ctx.defer()

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    result, remaining = await hatching.collect_egg(
        guild_id=ctx.guild_id,
        user_id=ctx.author.id,
        username=ctx.author.display_name,
    )
    if result == 'cooldown':
        assert remaining is not None  # noqa: S101 - guaranteed by cooldown sentinel
        await ctx.respond(f'try again <t:{int(remaining)}:R>', ephemeral=True)
        return

    if result == 'no_channel':
        return

    await ctx.respond(f'you received an egg: {result}')


@eggs_group.command(name='hatch', description='Hatch your next ready egg')
async def eggs_hatch(ctx: ApplicationContext):
    await ctx.defer()

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    result, next_ts = await hatching.hatch_egg(ctx.guild_id, ctx.author.id)

    if result == 'cooldown':
        assert next_ts is not None  # noqa: S101 - guaranteed by cooldown sentinel
        await ctx.respond(f'slow down, try again <t:{int(next_ts)}:R>', ephemeral=True)
    elif result == 'no_eggs':
        await ctx.respond('you have no eggs')
    elif result == '':
        assert next_ts is not None  # noqa: S101 - guaranteed float when result is empty string by contract
        await ctx.respond(f'your next egg hatches <t:{int(next_ts)}:R>')
    else:
        await ctx.respond(f'hatching! {result}')


@eggs_group.command(name='view', description='View your egg collection thread')
async def eggs_view(ctx: ApplicationContext):
    await ctx.defer()

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    from nova_core.eggs.hatching import _egg_user_repo

    user_doc = await _egg_user_repo.get(ctx.guild_id, ctx.author.id)

    if user_doc is None or not user_doc.thread_id:
        await ctx.respond("you haven't collected any eggs yet")
        return

    guild = ctx.guild
    thread_url = f'https://discord.com/channels/{guild.id}/{user_doc.thread_id}'
    await ctx.respond(thread_url)


@eggs_group.command(name='give', description='Give one of your eggs to another user')
@discord.commands.option(name='user', required=True, description='who to give the egg to', input_type=discord.Member)
@discord.commands.option(name='filter', required=False, description='show only hatched or unhatched eggs (omit for all)', choices=_give_filter_choices)
async def eggs_give(ctx: ApplicationContext, user: discord.Member, filter: str | None = None):  # noqa: A002 - pycord maps slash option name to parameter name; user-facing option must stay `filter`
    await ctx.defer()

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    if ctx.author.id == user.id:
        await ctx.respond('you cannot give eggs to yourself')
        return

    from nova_core.eggs.hatching import _egg_repo

    guild_id = ctx.guild_id
    from_mention = ctx.author.mention
    to_mention = user.mention
    to_display = user.display_name

    options: list[discord.SelectOption] = []

    if filter != 'hatched':
        unhatched = await _egg_repo.list_unhatched(guild_id, ctx.author.id)
        rarity_counts: dict[str, int] = {}
        for egg in unhatched:
            rarity_counts[egg.rarity] = rarity_counts.get(egg.rarity, 0) + 1
        seen: set[str] = set()
        for egg in unhatched:
            if egg.rarity not in seen:
                seen.add(egg.rarity)
                count = rarity_counts[egg.rarity]
                label = f'{egg.rarity} egg' + (f' x{count}' if count > 1 else '')
                options.append(discord.SelectOption(label=label, value=f'unhatched:{egg.rarity}'))

    if filter != 'unhatched':
        hatched_eggs = await _egg_repo.list_hatched(guild_id, ctx.author.id)
        result_counts: dict[str, int] = {}
        for egg in hatched_eggs:
            if egg.result:
                result_counts[egg.result] = result_counts.get(egg.result, 0) + 1
        seen_r: set[str] = set()
        for egg in hatched_eggs:
            if egg.result and egg.result not in seen_r:
                seen_r.add(egg.result)
                count = result_counts[egg.result]
                label = egg.result + (f' x{count}' if count > 1 else '')
                options.append(discord.SelectOption(label=label, value=f'hatched:{egg.result}'))

    if not options:
        no_eggs_label = 'hatched eggs' if filter == 'hatched' else ('unhatched eggs' if filter == 'unhatched' else 'eggs')
        await ctx.respond(f'you have no {no_eggs_label}', ephemeral=True)
        return

    select_view = EggSelectView(options, 0, ctx.author.id, from_mention, user.id, to_mention, to_display, guild_id)
    await ctx.respond('pick an egg to give:', view=select_view, ephemeral=True)


@eggs_group.command(name='progress', description='View your egg collection progress')
async def eggs_progress(ctx: ApplicationContext):
    await ctx.defer()

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    from nova_core.eggs.emojis import render_progress_bar
    from nova_core.eggs.hatching import _egg_repo

    total_collected, total_hatched, unique_by_rarity = await _egg_repo.get_user_egg_stats(ctx.guild_id, ctx.author.id)
    total_possible = sum(len(config.hatch.pools[r]) for r in config.hatch.rarities)
    total_unique = sum(unique_by_rarity.get(r, 0) for r in config.hatch.rarities)

    lines = []
    for rarity in config.hatch.rarities:
        pool_size = len(config.hatch.pools[rarity])
        collected = unique_by_rarity.get(rarity, 0)
        bar = render_progress_bar(collected, pool_size)
        lines.append(f'{rarity}: {bar} {collected}/{pool_size}')

    total_bar = render_progress_bar(total_unique, total_possible)
    lines.append(f'total: {total_bar} {total_unique}/{total_possible}')
    lines.append(f'{total_collected} eggs collected; {total_hatched} eggs hatched')

    embed = make_embed(f"{ctx.author.display_name}'s egg collection", description='\n'.join(lines), timestamp=False)
    await ctx.respond(embed=embed)


def _fmt_leaderboard(rows: list[dict], value_key: str, label: str) -> str:
    if not rows:
        return 'no data yet'
    lines = []
    for i, row in enumerate(rows[:10], start=1):
        lines.append(f'**{i}.** <@{row["_id"]}> - **{row[value_key]}** {label}')
    return '\n'.join(lines)


@leaderboard_group.command(name='hatched', description='Top egg collectors by total hatched')
async def eggs_leaderboard_hatched(ctx: ApplicationContext):
    await ctx.defer()

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    from nova_core.eggs.hatching import _egg_repo

    rows = await _egg_repo.leaderboard_most_hatched(ctx.guild_id)
    embed = make_embed('most hatched', description=_fmt_leaderboard(rows, 'total', 'hatched'), timestamp=False)
    await ctx.respond(embed=embed)


@leaderboard_group.command(name='collected', description='Top egg collectors by most complete set')
async def eggs_leaderboard_collected(ctx: ApplicationContext):
    await ctx.defer()

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    from nova_core.eggs.hatching import _egg_repo

    rows = await _egg_repo.leaderboard_most_unique(ctx.guild_id)
    embed = make_embed('most complete set', description=_fmt_leaderboard(rows, 'unique', 'unique'), timestamp=False)
    await ctx.respond(embed=embed)


# --- Extension Def ---


def setup(bot: Bot):
    active_guilds = list(config.authorized_guilds)
    egg_command.guild_ids = active_guilds
    eggs_group.guild_ids = active_guilds
    logger.info(f'registered: {__name__} for guilds {active_guilds}')
    bot.add_application_command(cast(ApplicationCommand, egg_command))
    bot.add_application_command(cast(ApplicationCommand, eggs_group))
