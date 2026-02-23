"""
AttuBot - Bot Event Handlers
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import sys
from datetime import UTC, datetime

import anyio
from discord import ApplicationContext, Color, Embed, Member, Message, RawBulkMessageDeleteEvent, RawMessageDeleteEvent, RawMessageUpdateEvent
from discord.errors import CheckFailure
from discord.ext.commands import MissingPermissions

from attubot import bot, config
from attubot.config import UnauthorizedGuild
from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Helpers ---


_READY_SENTINEL = '/tmp/bot-ready'  # noqa: S108


async def _shutdown(exit_code: int = 1):
    """close db connections and stop the event loop cleanly"""
    import contextlib

    from attubot import db

    if db.client:
        await db.client.close()

    with contextlib.suppress(FileNotFoundError):
        await anyio.Path(_READY_SENTINEL).unlink()

    asyncio.get_running_loop().stop()
    sys.exit(exit_code)


# --- Events ---


@bot.event
async def on_application_command_error(ctx: ApplicationContext, error: Exception):
    logger.error(f'Error sent to `on_application_command_error()` from `{ctx.command.name}` error={error!s}')

    if isinstance(error, CheckFailure | UnauthorizedGuild):
        if ctx.guild.id in config.authorized_guilds:
            await ctx.respond("You're not my real dad!")
        else:
            # catch all for if bot gets added to another discord guild
            await ctx.respond('This feature requires DoomBot(tm) Premium')

    elif isinstance(error, MissingPermissions):
        await ctx.respond('Nice try! <:rockball:1308981475114225694>')

    else:
        if ctx.command.name != 'force_error':
            await ctx.respond('An unexpected error occurred! <:rockball_player:1308977543034048552>')

        if hasattr(ctx.response, 'jump_url'):
            link = ctx.response.jump_url
        elif hasattr(ctx.channel, 'jump_url'):
            link = ctx.channel.jump_url
        elif hasattr(ctx.guild, 'jump_url'):
            link = ctx.guild.jump_url
        else:
            link = '`fuck idk man`'

        await logger.send_to_webhook(error, location=f'triggered by `{ctx.user.global_name}` at {link}')


@bot.event
async def on_ready():
    perms = '292595117136'

    if not hasattr(on_ready, 'has_run'):
        on_ready.has_run = False

    if not on_ready.has_run:
        on_ready.has_run = True

        logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})!')
        logger.info(f'Add to a server:\n\thttps://discord.com/oauth2/authorize?client_id={bot.application_id}&scope=bot&permissions={perms}')

        try:
            logger.info('Connecting to database and initializing repositories...')
            from attubot.database import init_database

            await init_database(config.database.url, config.database.name)

            logger.info('Loading configuration from database...')
            await config.on_load()
        except Exception as err:
            logger.fatal('Exception caught initializing database; exiting', err)
            await logger.send_to_webhook(err)
            await _shutdown(exit_code=1)
            return

        try:
            await config.on_ready()
        except Exception as err:
            logger.fatal('Exception caught in on_ready() event; exiting', err)
            await logger.send_to_webhook(err)
            await _shutdown(exit_code=1)
            return

        if config.test_mode:
            logger.fatal('Reached ready state')
            await _shutdown(exit_code=0)
            return

        # start task scheduler
        try:
            from attubot.tasks import scheduler

            await scheduler.start_all()
        except Exception as err:
            logger.fatal('Exception caught starting task scheduler; exiting', err)
            await logger.send_to_webhook(err)
            await _shutdown(exit_code=1)
            return

        # signal healthcheck: bot is fully ready
        try:
            await anyio.Path(_READY_SENTINEL).write_text('ready\n')
        except Exception as err:
            logger.warn(f'Could not write ready sentinel: {err}')

        logger.info('Pushing commands to Discord')
        await bot.sync_commands()

    else:
        logger.info(f'Reconnected as {bot.user} (ID: {bot.user.id})!')


@bot.event
async def on_message(message: Message):
    if message.guild is None:
        logger.debug(f'Skipping checks for message from "{message.author.name}" with blank guild')
        return

    if message.guild.id not in config.valid_guilds:
        logger.debug(f'Skipping checks for message from "{message.author.name}" in "{message.guild.name}" (invalidated guild)')
        return

    guild_config = config.guild(message.guild.id)

    # store the message unless it's in the logs channel
    if message.channel.id != guild_config.channels.logs:
        from attubot.messages import store_message

        await store_message(message)

    activity_channel = guild_config.channels.activity

    if message.channel.id == activity_channel and message.content.startswith(f'[{config.wiki.user.split("@")[0]}]'):
        if 'blocked' in message.content or 'registered' in message.content:
            await message.add_reaction('<:tieteran_wave:1308636215930654801>')
        else:
            await message.add_reaction('💖')


@bot.event
async def on_raw_message_edit(payload: RawMessageUpdateEvent):
    if payload.guild_id is None:
        logger.debug('raw_message_edit: dropping - guild_id is None')
        return

    if payload.guild_id not in config.valid_guilds:
        logger.debug(f'raw_message_edit: dropping - guild_id={payload.guild_id} not in valid_guilds')
        return

    # skip edits in the logs channel
    try:
        logs_channel_id = config.guild(payload.guild_id).channels.logs
        if payload.channel_id == logs_channel_id:
            logger.debug('raw_message_edit: dropping - channel is logs channel')
            return
    except Exception as err:
        logger.debug(f'raw_message_edit: dropping - exception resolving logs channel: {err}')
        return

    logger.debug('raw_message_edit: passing to log_edit')
    from attubot.messages import log_edit

    await log_edit(payload)


@bot.event
async def on_raw_message_delete(payload: RawMessageDeleteEvent):
    if payload.guild_id is None or payload.guild_id not in config.valid_guilds:
        return

    # skip deletions in the logs channel
    try:
        logs_channel_id = config.guild(payload.guild_id).channels.logs
        if payload.channel_id == logs_channel_id:
            return
    except Exception:
        return

    from attubot.messages import log_delete

    await log_delete(payload)


@bot.event
async def on_raw_bulk_message_delete(payload: RawBulkMessageDeleteEvent):
    if payload.guild_id is None or payload.guild_id not in config.valid_guilds:
        return

    # skip bulk deletions in the logs channel
    try:
        logs_channel_id = config.guild(payload.guild_id).channels.logs
        if payload.channel_id == logs_channel_id:
            return
    except Exception:
        return

    from attubot.messages import log_bulk_delete

    await log_bulk_delete(payload)


@bot.event
async def on_member_join(member: Member):
    if member.guild.id not in config.valid_guilds:
        return

    guild_config = config.guild(member.guild.id)

    async def send_welcome():
        channel_id = guild_config.channels.general
        if channel_id == 0:
            logger.debug(f'no general channel configured for guild {member.guild.id}, skipping welcome')
            return
        channel = member.guild.get_channel(channel_id)
        if channel is None:
            logger.warn(f'general channel {channel_id} not found in guild {member.guild.id}')
            return
        await channel.send(f'welcome to the archipelago {member.mention}')

    async def send_log():
        channel_id = guild_config.channels.logs
        if channel_id == 0:
            logger.debug(f'no logs channel configured for guild {member.guild.id}, skipping member log')
            return
        channel = member.guild.get_channel(channel_id)
        if channel is None:
            logger.warn(f'logs channel {channel_id} not found in guild {member.guild.id}')
            return

        created_at = member.created_at.replace(tzinfo=UTC) if member.created_at.tzinfo is None else member.created_at
        now = datetime.now(tz=UTC)
        age_days = (now - created_at).days
        age_str = f'{age_days // 365}y {age_days % 365}d' if age_days >= 365 else f'{age_days}d'

        color_hex = int(config.theme.bot_color.lstrip('#'), 16) if config.theme else Color.blurple().value
        embed = Embed(title='Member Joined', color=color_hex)
        embed.add_field(name='Mention', value=member.mention, inline=True)
        embed.add_field(name='Username', value=member.name, inline=True)
        embed.add_field(name='Account Created', value=f'<t:{int(created_at.timestamp())}:f>', inline=False)
        embed.add_field(name='Account Age', value=age_str, inline=True)

        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        await channel.send(embed=embed)

    await asyncio.gather(send_welcome(), send_log())


@bot.before_invoke
async def on_application_command(ctx: ApplicationContext):
    logger.info(f'Command executed: user="{ctx.user.global_name}" command="/{ctx.command}" channel="{ctx.channel.name}" data={ctx.interaction.data}')


logger.info('Registered event handlers')
