"""
AttuBot - Egg game slash commands (loaded dynamically on hatch day)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from typing import cast

import discord
from discord import ApplicationCommand, ApplicationContext, Bot, SlashCommandGroup

from attubot import config
from attubot.database.models import EggDocument
from attubot.eggs import hatching
from attubot.logging import get_logger


logger = get_logger(__name__)

eggs_group = SlashCommandGroup('eggs', description='egg collection game')

_GIVE_RARITY_CHOICES = ['common', 'uncommon', 'rare', 'legendary', 'mythical', 'hatched']


# --- Views ---


def _offer_text(from_mention: str, to_mention: str, egg: EggDocument, egg_jump_url: str) -> str:
    """Build the public offer message content."""
    if egg.hatched:
        creature = egg.result or '?'
        content = f'{from_mention} wants to give {to_mention} a {creature}. accept?'
    else:
        from attubot.eggs.hatching import _egg_emoji_str

        emoji = _egg_emoji_str(egg.rarity)
        content = f'{from_mention} wants to give {to_mention} a {emoji} {egg.rarity} egg. accept?'
    if egg_jump_url:
        content += f'\n{egg_jump_url}'
    return content


class EggGiftOfferView(discord.ui.View):
    """Public offer message with Accept/Decline buttons for egg gifting."""

    def __init__(self, egg: EggDocument, from_id: int, from_mention: str, to_id: int, to_mention: str, to_display: str, guild_id: int):
        super().__init__(timeout=300)
        self.egg = egg
        self.from_id = from_id
        self.from_mention = from_mention
        self.to_id = to_id
        self.to_mention = to_mention
        self.to_display = to_display
        self.guild_id = guild_id
        self.message: discord.Message | None = None

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.success)
    async def accept(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.to_id:
            await interaction.response.send_message('this offer is not for you', ephemeral=True)
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
            await interaction.response.edit_message(content='this egg is no longer available.', view=None)
            return
        await interaction.response.edit_message(content=f'sent! {new_jump_url}', view=None)

    @discord.ui.button(label='Decline', style=discord.ButtonStyle.danger)
    async def decline(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.to_id:
            await interaction.response.send_message('this offer is not for you', ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(content='offer declined.', view=None)

    async def on_timeout(self):
        import contextlib

        if self.message:
            with contextlib.suppress(discord.NotFound):
                await self.message.edit(content='offer expired.', view=None)


class _EggSelectMenu(discord.ui.Select):
    """Select menu populated with a user's unique eggs for gifting."""

    def __init__(self, options: list[discord.SelectOption], from_id: int, from_mention: str, to_id: int, to_mention: str, to_display: str, guild_id: int):
        self.from_id = from_id
        self.from_mention = from_mention
        self.to_id = to_id
        self.to_mention = to_mention
        self.to_display = to_display
        self.guild_id = guild_id
        super().__init__(placeholder='pick an egg to give', options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.from_id:
            await interaction.response.send_message('not your selection', ephemeral=True)
            return

        value = self.values[0]
        prefix, key = value.split(':', 1)

        from attubot.eggs.hatching import _egg_repo, _egg_user_repo

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

    def __init__(self, options: list[discord.SelectOption], from_id: int, from_mention: str, to_id: int, to_mention: str, to_display: str, guild_id: int):
        super().__init__(timeout=120)
        self.add_item(_EggSelectMenu(options, from_id, from_mention, to_id, to_mention, to_display, guild_id))


# --- Commands ---


@discord.slash_command(name='egg', description='Collect an egg!')
async def egg_command(ctx: ApplicationContext):
    await ctx.defer(ephemeral=True)

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    try:
        jump_url = await hatching.collect_egg(
            guild_id=ctx.guild_id,
            user_id=ctx.author.id,
            username=ctx.author.display_name,
        )
    except ValueError as err:
        await ctx.respond(str(err), ephemeral=True)
        return

    await ctx.respond(f'you received an egg. {jump_url}', ephemeral=True)


@eggs_group.command(name='hatch', description='Hatch your next ready egg')
async def eggs_hatch(ctx: ApplicationContext):
    await ctx.defer(ephemeral=True)

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    result, next_ts = await hatching.hatch_egg(ctx.guild_id, ctx.author.id)

    if result == 'no_eggs':
        await ctx.respond('you have no eggs', ephemeral=True)
    elif result == '':
        assert next_ts is not None  # noqa: S101 - guaranteed float when result is empty string by contract
        await ctx.respond(f'your next egg hatches <t:{int(next_ts)}:R>', ephemeral=True)
    else:
        await ctx.respond(f'hatching! {result}', ephemeral=True)


@eggs_group.command(name='view', description='View your egg collection thread')
async def eggs_view(ctx: ApplicationContext):
    await ctx.defer(ephemeral=True)

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    from attubot.eggs.hatching import _egg_user_repo

    user_doc = await _egg_user_repo.get(ctx.guild_id, ctx.author.id)

    if user_doc is None or not user_doc.thread_id:
        await ctx.respond("you haven't collected any eggs yet", ephemeral=True)
        return

    guild = ctx.guild
    thread_url = f'https://discord.com/channels/{guild.id}/{user_doc.thread_id}'
    await ctx.respond(thread_url, ephemeral=True)


@eggs_group.command(name='give', description='Give one of your eggs to another user')
@discord.commands.option(name='user', required=True, description='who to give the egg to', input_type=discord.Member)
@discord.commands.option(name='rarity', required=False, description='which rarity to give (omit to pick from a list)', choices=_GIVE_RARITY_CHOICES)
async def eggs_give(ctx: ApplicationContext, user: discord.Member, rarity: str | None = None):
    await ctx.defer(ephemeral=True)

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    if ctx.author.id == user.id:
        await ctx.respond('you cannot give eggs to yourself', ephemeral=True)
        return

    from attubot.eggs.hatching import _egg_repo, _egg_user_repo

    guild_id = ctx.guild_id
    from_mention = ctx.author.mention
    to_mention = user.mention
    to_display = user.display_name

    if rarity and rarity != 'hatched':
        # specific unhatched rarity requested - go straight to offer
        egg = await _egg_repo.get_oldest_unhatched_by_rarity(guild_id, ctx.author.id, rarity)
        if egg is None:
            await ctx.respond(f'you have no {rarity} eggs', ephemeral=True)
            return
        from_user_doc = await _egg_user_repo.get(guild_id, ctx.author.id)
        egg_jump_url = ''
        if from_user_doc and from_user_doc.thread_id and egg.message_id:
            egg_jump_url = f'https://discord.com/channels/{guild_id}/{from_user_doc.thread_id}/{egg.message_id}'
        offer_content = _offer_text(from_mention, to_mention, egg, egg_jump_url)
        offer_view = EggGiftOfferView(egg, ctx.author.id, from_mention, user.id, to_mention, to_display, guild_id)
        offer_msg = await ctx.channel.send(offer_content, view=offer_view)
        offer_view.message = offer_msg
        await ctx.respond('offer sent!', ephemeral=True)
        return

    # build select menu with deduplicated entries
    options: list[discord.SelectOption] = []

    if not rarity:
        # include unhatched eggs (unique by rarity)
        unhatched = await _egg_repo.list_unhatched(guild_id, ctx.author.id)
        seen_rarities: set[str] = set()
        for egg in unhatched:
            if egg.rarity not in seen_rarities:
                seen_rarities.add(egg.rarity)
                options.append(discord.SelectOption(label=f'{egg.rarity} egg', value=f'unhatched:{egg.rarity}'))

    # include hatched creatures (unique by result emoji)
    hatched_eggs = await _egg_repo.list_hatched(guild_id, ctx.author.id)
    seen_results: set[str] = set()
    for egg in hatched_eggs:
        if egg.result and egg.result not in seen_results:
            seen_results.add(egg.result)
            options.append(discord.SelectOption(label=egg.result, value=f'hatched:{egg.result}'))

    if not options:
        label = 'hatched eggs' if rarity == 'hatched' else 'eggs'
        await ctx.respond(f'you have no {label}', ephemeral=True)
        return

    select_view = EggSelectView(options, ctx.author.id, from_mention, user.id, to_mention, to_display, guild_id)
    await ctx.respond('pick an egg to give:', view=select_view, ephemeral=True)


@eggs_group.command(name='progress', description='View your egg collection progress')
async def eggs_progress(ctx: ApplicationContext):
    await ctx.defer()

    if not ctx.guild_id or ctx.guild_id not in config.authorized_guilds:
        await ctx.respond('not available here', ephemeral=True)
        return

    from attubot.eggs.data import hatch_pools, rarities
    from attubot.eggs.emojis import render_progress_bar
    from attubot.eggs.hatching import _egg_repo

    total_collected, total_hatched, unique_by_rarity = await _egg_repo.get_user_egg_stats(ctx.guild_id, ctx.author.id)
    total_possible = sum(len(hatch_pools[r]) for r in rarities)
    total_unique = sum(unique_by_rarity.get(r, 0) for r in rarities)

    lines = []
    for rarity in rarities:
        pool_size = len(hatch_pools[rarity])
        collected = unique_by_rarity.get(rarity, 0)
        bar = render_progress_bar(collected, pool_size)
        lines.append(f'{rarity}: {bar} {collected}/{pool_size}')

    total_bar = render_progress_bar(total_unique, total_possible)
    lines.append(f'total: {total_bar} {total_unique}/{total_possible}')
    lines.append(f'{total_collected} eggs collected; {total_hatched} eggs hatched')

    await ctx.respond('\n'.join(lines))


# --- Extension Def ---


def setup(bot: Bot):
    from datetime import datetime

    from attubot.eggs.hatching import hatch_date

    today = datetime.now(tz=config.timezone).date()
    if today < hatch_date(today.year):
        logger.debug(f'{__name__}: before hatch day, skipping registration')
        return

    logger.info(f'registered: {__name__}')
    bot.add_application_command(cast(ApplicationCommand, egg_command))
    bot.add_application_command(cast(ApplicationCommand, eggs_group))
