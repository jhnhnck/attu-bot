"""
AttuBot - Administrative and Debug Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""
from datetime import datetime
from os import getenv

import discord
from discord import Permissions
from discord.ext import commands

from attubot import __version__
from attubot.config import Config
from attubot.logging import get_logger
from attubot.util import get_year_span, get_year_status, move_epoch
from attubot.wiki import AttuWiki

logger = get_logger(__name__)

# --- Commands ---

@discord.slash_command(guilds_only=True, default_member_permissions=Permissions.all())
@discord.commands.option(name='option', required=True, description='Admin Option to Run', input_type=str)
@discord.commands.option(name='number', required=False, description='Arguments', input_type=int)
async def admin(ctx, option: str, number):
    options = ['force_year', 'time_dilate', 'time_pause', 'time_resume']
    options.sort()

    if ctx.user.id != Config.bot_owner:
        await ctx.respond("You're not my real dad!")
        return

    if option == 'force_year':
        forced_year = len(Config.timestamps) + 1
        _, year = get_year_status()
        cog = ctx.bot.get_cog('NewYearEvent')

        logger.info(f'Weap. Year forced by admin: expected: {year} doing: {forced_year}')
        await ctx.respond('Weap. No longer going to try my best, just forcing new year instead')
        await cog.advance_year(forced_year)

    elif option == 'time_pause':
        await ctx.respond('The passage of time has been stopped')
        Config.pause_time()

    elif option == 'time_resume':
        move_epoch(Config.epoch_length)

        await ctx.respond(f'The passage of time has been resumed with Attu epoch moved to **{Config.epoch_year} PC** at **<t:{Config.epoch_time}:f>**')
        Config.resume_time()

    elif option == 'time_dilate':
        if number is None:
            await ctx.respond('Failed: Submit dilation amount (in days) in number field', ephemeral=True)
            return

        if Config.time_paused:
            Config.set_epoch_length(number)
            await ctx.respond(f'The passage of time has been set to **{Config.epoch_length} days per year**')
        else:
            move_epoch(number)
            await ctx.respond(f'The passage of time has been set to **{Config.epoch_length} days per year** with Attu epoch moved to **{Config.epoch_year} PC** at **<t:{Config.epoch_time}:f>**')

    else:
        await ctx.respond(f'Failed: Options are {", ".join(options)}', ephemeral=True)

@discord.slash_command(guilds_only=True, default_member_permissions=Permissions.all())
@discord.commands.option(name='option', required=True, description='Debug Option to Run', input_type=str)
async def debug(ctx, option: str):
    options = ['version', 'year_stats', 'force_error']
    options.sort()

    if ctx.user.id != Config.bot_owner:
        await ctx.respond("You're not my real dad!")
        return

    if option == 'version':
        build_format = '%a %b %d %H:%M:%S %Z %Y'
        build_time = datetime.strptime(getenv('BUILD_TIME'), build_format)

        await ctx.respond('\n'.join([
            f'Version: {__version__}',
            f'Container Build Time: <t:{int(build_time.timestamp())}:f>',
        ]))

    elif option == 'year_stats':
        elapsed_days, current_year = get_year_status()
        year_span = get_year_span(current_year)
        cog = ctx.bot.get_cog('NewYearEvent')

        await ctx.respond('\n'.join([
            f'Current Year: {current_year} PC',
            f'Year Span: <t:{year_span.start_time}:f> to <t:{year_span.end_time}:f> ({year_span.duration} days)',
            f'Attu Epoch: {Config.epoch_year} PC at <t:{Config.epoch_time}:f>',
            f'Time Since Epoch: {elapsed_days} Days',
            f'Next Task Iteration: <t:{int(cog.task_year_check.next_iteration.timestamp())}:f>',
        ]))

    elif option == 'force_error':
        await ctx.respond('Forcing an error message')
        math = 10 / 0  # noqa: F841

    else:
        await ctx.respond(f'Failed: Options are {", ".join(options)}', ephemeral=True)

@discord.slash_command(guilds_only=True, default_member_permissions=Permissions.all())
@discord.commands.option(name='user', required=True, description='Wiki Username (case sensitive probably)', input_type=str)
@discord.commands.option(name='reason', required=True, description='Reason for blocking', input_type=str)
async def wiki_block(ctx, user, reason):
    # TODO: allow sending a link to the user profile instead
    await ctx.respond(f'Blocking user "{user}": {reason}')

    wiki = AttuWiki()
    wiki.authenticate(Config.wiki_user, Config.wiki_key)
    wiki.block(user, f'{reason} (on behalf of {ctx.user.global_name})')

# --- Extension Def ---

def setup(bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(admin)
    bot.add_application_command(debug)
    bot.add_application_command(wiki_block)
