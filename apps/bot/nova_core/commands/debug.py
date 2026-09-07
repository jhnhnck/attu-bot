# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.debug | fun and version commands."""

import asyncio
from datetime import datetime
from platform import freedesktop_os_release as os_release
from platform import python_version
from random import randrange
from typing import cast

import discord
import structlog
from discord import ApplicationCommand, ApplicationContext, Bot

from nova_core import __build_time__, __schema__, __title__, __version__
from nova_core.client.core import config
from nova_core.client.embeds import make_embed, ui_emoji


logger = structlog.stdlib.get_logger(__name__)


@discord.slash_command(name='color', description='show the current theme color')
async def command_color(ctx: ApplicationContext):
    if not config.theme:
        await ctx.respond('no theme color is configured for this server', ephemeral=True)
        return

    hex_color = config.theme.bot_color
    embed = make_embed('Bot Color', description=f'`{hex_color}`')
    await ctx.respond(embed=embed)


# message-style wants an imperative fragment; /ping and /pong are third person and
# matched word-for-word on purpose, and the delayed reply below stays unadvertised
@discord.slash_command(name='pong', description='pongs you')
async def command_pong(ctx: ApplicationContext):
    async def wait_random():
        sleep_time = 5 * randrange(25, 240)

        logger.info(f'pong task sleeping for {sleep_time} seconds')
        await asyncio.sleep(sleep_time)

        await ctx.channel.send(f'{ctx.author.mention}! {ui_emoji("rockball")}')

    if config.is_owner(ctx.author.id):
        await ctx.respond(f'{ctx.author.mention}! {ui_emoji("rockball")}')

    else:
        await ctx.respond(f'Ping! {ui_emoji("rockball")}')
        from nova_core.tasks import scheduler

        scheduler.add_job(wait_random(), 'PongTask', ctx.author.name)


@discord.slash_command(name='version', description='show the bot version and container build time')
async def command_version(ctx: ApplicationContext):
    build_format = '%a %b %d %H:%M:%S %Z %Y'
    build_time = datetime.strptime(__build_time__, build_format)
    distro, distro_version = os_release()['ID'].capitalize(), os_release()['VERSION_ID']

    embed = make_embed('Version Info')

    embed.add_field(name='Version', value=f'{__title__} {__version__} ({__schema__})', inline=True)
    embed.add_field(name='Python', value=python_version(), inline=True)
    embed.add_field(name='Distro', value=f'{distro} {distro_version}', inline=True)
    embed.add_field(name='Container Build Time', value=f'<t:{int(build_time.timestamp())}:f>', inline=False)

    await ctx.respond(embed=embed)


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(cast('ApplicationCommand', command_color))
    bot.add_application_command(cast('ApplicationCommand', command_pong))
    bot.add_application_command(cast('ApplicationCommand', command_version))
