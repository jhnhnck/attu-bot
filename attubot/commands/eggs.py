"""
AttuBot - Egg game slash commands (loaded dynamically on hatch day)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from typing import cast

import discord
from discord import ApplicationCommand, ApplicationContext, Bot, SlashCommandGroup

from attubot import config
from attubot.eggs import hatching
from attubot.logging import get_logger


logger = get_logger(__name__)

eggs_group = SlashCommandGroup('eggs', description='egg collection game')


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
