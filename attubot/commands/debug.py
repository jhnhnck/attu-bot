"""
AttuBot - Debug Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import io
import json
from datetime import datetime
from platform import freedesktop_os_release as os_release
from platform import python_version
from random import randrange, sample
from typing import Never, cast

import discord
import tomlkit
from discord import ApplicationCommand, ApplicationContext, Bot, Embed, Permissions, SlashCommandGroup
from discord.ext import commands
from discord.utils import snowflake_time

from attubot import __build_time__, __schema__, __title__, __version__, config
from attubot.calendar import get_year_span, get_year_status
from attubot.logging import get_logger
from attubot.tasks import scheduler
from attubot.util import is_bot_owner, theme_color

logger = get_logger(__name__)

# --- Fun Commands ---


@discord.slash_command(name='pong', description='Another simple command to test if the bot is online')
async def command_pong(ctx: ApplicationContext):
    async def wait_random():
        sleep_time = 5 * randrange(25, 240)

        logger.info(f'Pong task sleeping for {sleep_time} seconds')
        await asyncio.sleep(sleep_time)

        await ctx.channel.send(f'{ctx.author.mention}! <:rockball:1308981475114225694>')

    if config.is_owner(ctx.author.id):
        await ctx.respond(f'{ctx.author.mention}! <:rockball:1308981475114225694>')

    else:
        await ctx.respond('Ping! <:rockball:1308981475114225694>')
        from attubot.tasks import scheduler

        scheduler.add_job(wait_random(), f'PongTask[{ctx.author.name}]')


@discord.slash_command(name='test', description='Simple command to test with')
async def command_test(ctx: ApplicationContext):
    """Utility command for debugging - kept unregistered for manual use when needed"""
    if not config.is_owner(ctx.author.id):
        await ctx.respond('Do I know you?', ephemeral=True)
        return

    try:
        pass

    except Exception as err:
        await logger.send_to_webhook(err)

        await ctx.respond('https://discord.com/channels/572148465870700544/1256800104082313257')
        return


# --- Debug Commands ---

debug_group = SlashCommandGroup('debug', default_member_permissions=Permissions.all(), description='Prints out debug information on current bot functionality')
# debug_admin_group = debug_group.create_subgroup('admin', description='Like the normal debug commands except scarier (Admin Only)', )


@debug_group.command(name='version', description='Displays the current version and container build time')
async def debug_version(ctx: ApplicationContext):
    build_format = '%a %b %d %H:%M:%S %Z %Y'
    build_time = datetime.strptime(__build_time__, build_format)
    distro, distro_version = os_release()['ID'].capitalize(), os_release()['VERSION_ID']

    embed = Embed(title='Version Info', color=theme_color())

    embed.add_field(name='Version', value=f'{__title__} {__version__} ({__schema__})', inline=True)
    embed.add_field(name='Python', value=python_version(), inline=True)
    embed.add_field(name='Distro', value=f'{distro} {distro_version}', inline=True)
    embed.add_field(name='Container Build Time', value=f'<t:{int(build_time.timestamp())}:f>', inline=False)

    await ctx.respond(embed=embed)


@debug_group.command(name='scheduler', description='Displays the currently running tasks')
async def debug_scheduler(ctx: ApplicationContext):
    task_names = scheduler.running_tasks

    embed = Embed(title='Tasks', description=', '.join(task_names), color=theme_color())
    embed.add_field(name='Total', value=str(scheduler.count), inline=False)

    await ctx.respond(embed=embed)


@debug_group.command(name='year_stats', description='Returns the current state of time tracking calculations')
async def debug_year_stats(ctx: ApplicationContext):
    guild_config = config.guild(ctx.guild.id)
    elapsed_days, current_year = get_year_status(guild=guild_config.id)
    year_span = await get_year_span(current_year, guild=guild_config.id)

    embed = Embed(title='Year Stats', color=theme_color())

    embed.add_field(name='Current Year', value=f'{current_year} PC', inline=True)
    embed.add_field(name='Time Since Epoch', value=f'{elapsed_days} Days', inline=True)
    embed.add_field(name='Attu Epoch', value=f'<t:{guild_config.epoch.time}:f>\n({guild_config.epoch.year} PC)', inline=True)
    embed.add_field(name='Year Span', value=f'<t:{year_span.start_time}:f> to <t:{year_span.end_time}:f> ({year_span.duration} days)', inline=False)

    await ctx.respond(embed=embed)


@debug_group.command(name='force_error', description='Causes an internal error to be thrown')
@commands.check(is_bot_owner)
async def debug_force_error(ctx: ApplicationContext) -> Never:
    # https://giphy.com/gifs/click-button-8-bit-mx4B7Wui0EL23gwGdq Credit: @OlgaKhatkovskaya
    await ctx.respond('https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExeWpmdGI4YzBudjM0Zm1kN3Q2emZtcGMyaHlyc2J3dWozYXJ6ZzhzYSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/mx4B7Wui0EL23gwGdq/giphy.gif')

    raise Exception(f'Forced error from {ctx.author.name}')


@debug_group.command(name='message', description='Print message info')
@commands.check(is_bot_owner)
@discord.commands.option(name='link', required=True, description='Message Link', input_type=str)
async def debug_message(ctx: ApplicationContext, link):
    if 'discord.com/channels' not in link:
        await ctx.respond('Failed: Not a valid Discord message link', ephemeral=True)
        return

    # unpack url
    ids = link.split('/')[-3:]
    guild, channel, target = int(ids[0]), int(ids[1]), int(ids[2])

    try:
        guild = ctx.bot.get_guild(guild)
        channel = cast(discord.TextChannel, guild.get_channel_or_thread(channel))  # it doesn't really matter

        async for message in channel.history(around=snowflake_time(target), limit=15):
            if message.id == target:
                await ctx.respond(f'```\n{message}\n```')
                return

        await ctx.respond("Couldn't find message! <:rockball_player:1308977543034048552>")
    except Exception as err:
        await ctx.respond('Error locating message! (check logs) <:rockball_player:1308977543034048552>')
        logger.error(err)


@debug_group.command(name='dump_config', description='Prints config to console')
@commands.check(is_bot_owner)
async def debug_dump_config(ctx: ApplicationContext):
    logger.info('Dumping NovaConfig:', tomlkit.dumps(config.to_dict(), sort_keys=True), sep='\n')

    await ctx.respond('Done!')


@debug_group.command(name='message_stats', description='Shows how many messages are stored for a channel or the whole guild')
@commands.check(is_bot_owner)
@discord.commands.option(name='channel', required=False, description='Channel to query (omit for guild total)', input_type=discord.TextChannel)
async def debug_message_stats(ctx: ApplicationContext, channel: discord.TextChannel | None = None):
    from attubot.messages import _get_repo

    try:
        repo = _get_repo()
    except RuntimeError:
        await ctx.respond('message repo not initialized yet', ephemeral=True)
        return

    if channel is not None:
        count = await repo.count_for_channel(ctx.guild.id, channel.id)
        await ctx.respond(f'{count:,} messages stored for <#{channel.id}>')
    else:
        count = await repo.count_for_guild(ctx.guild.id)
        await ctx.respond(f'{count:,} messages stored for this guild')


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(cast(ApplicationCommand, command_pong))
    # bot.add_application_command(cast(ApplicationCommand, command_test))
    bot.add_application_command(debug_group)
