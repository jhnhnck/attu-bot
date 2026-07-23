# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.query | query commands."""

from datetime import datetime

import discord
import structlog
from discord import ApplicationContext, Bot, MessageType, Permissions, SlashCommandGroup
from discord.ext import commands
from discord.utils import snowflake_time

from nova_core.client.calendar import format_year_line, get_year_span, get_year_status
from nova_core.client.util import format_message_link, is_bot_owner


logger = structlog.stdlib.get_logger(__name__)

# --- Query Commands ---

query_group = SlashCommandGroup('query', default_member_permissions=Permissions.all(), description="Performs searches for specific messages if that's your thing")


@query_group.command(name='pins', description='Finds all the "pinned a message" messages in a channel')
@discord.commands.option(name='channel', required=True, description='Channel', input_type=discord.TextChannel)
@commands.check(is_bot_owner)
async def query_pins(ctx: ApplicationContext, channel: discord.TextChannel):
    _, current_year = get_year_status()
    guild_creation = snowflake_time(ctx.guild.id)

    # this might take a bit so send message to not timeout
    logger.info(f'querying pins in #{channel.name}')
    await ctx.respond(f'## Pins in <#{channel.id}>')

    # for year 1 thru current year
    for year in range(1, current_year + 1):
        year_span = await get_year_span(year)
        start_time = datetime.fromtimestamp(year_span.start_time).astimezone() if year > 0 else guild_creation
        end_time = datetime.fromtimestamp(year_span.end_time).astimezone()
        pins = []

        # search through each years history
        async for message in channel.history(after=start_time, before=end_time, limit=None):
            if message.type == MessageType.pins_add:
                link = format_message_link(ctx.guild.id, message.reference.channel_id, message.reference.message_id or 0)

                logger.info(f'found pin_add in {year} PC at {message.jump_url} -> {link}')
                pins.append(f'{message.jump_url} -> {link}')

        if len(pins) > 0:
            await ctx.channel.send(f'##{format_year_line(year)}\n' + '\n'.join(pins))


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(query_group)
