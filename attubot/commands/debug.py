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
from discord import ApplicationCommand, ApplicationContext, Bot, Permissions, SlashCommandGroup
from discord.ext import commands
from discord.utils import snowflake_time

from attubot import __build_time__, __schema__, __title__, __version__, config
from attubot.client.calendar import get_year_span, get_year_status
from attubot.client.embeds import make_embed, ui_emoji
from attubot.client.util import is_bot_owner
from attubot.logging import get_logger
from attubot.tasks import scheduler


logger = get_logger(__name__)

# --- Fun Commands ---


@discord.slash_command(name='color', description='Shows the current bot theme color')
async def command_color(ctx: ApplicationContext):
    if not config.theme:
        await ctx.respond('Failed: no theme color configured', ephemeral=True)
        return

    hex_color = config.theme.bot_color
    embed = make_embed('Bot Color', description=f'`{hex_color}`')
    await ctx.respond(embed=embed)


@discord.slash_command(name='pong', description='Another simple command to test if the bot is online')
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
        from attubot.tasks import scheduler

        scheduler.add_job(wait_random(), 'PongTask', ctx.author.name)


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
debug_eggs = debug_group.create_subgroup('eggs', 'Egg game debug commands')


@debug_group.command(name='version', description='Displays the current version and container build time')
async def debug_version(ctx: ApplicationContext):
    build_format = '%a %b %d %H:%M:%S %Z %Y'
    build_time = datetime.strptime(__build_time__, build_format)
    distro, distro_version = os_release()['ID'].capitalize(), os_release()['VERSION_ID']

    embed = make_embed('Version Info')

    embed.add_field(name='Version', value=f'{__title__} {__version__} ({__schema__})', inline=True)
    embed.add_field(name='Python', value=python_version(), inline=True)
    embed.add_field(name='Distro', value=f'{distro} {distro_version}', inline=True)
    embed.add_field(name='Container Build Time', value=f'<t:{int(build_time.timestamp())}:f>', inline=False)

    await ctx.respond(embed=embed)


@debug_group.command(name='scheduler', description='Displays the currently running tasks')
async def debug_scheduler(ctx: ApplicationContext):
    task_names = scheduler.running_tasks

    embed = make_embed('Tasks', description=', '.join(task_names))
    embed.add_field(name='Total', value=str(scheduler.count), inline=False)

    await ctx.respond(embed=embed)


@debug_group.command(name='year_stats', description='Returns the current state of time tracking calculations')
async def debug_year_stats(ctx: ApplicationContext):
    guild_config = config.guild(ctx.guild.id)
    elapsed_days, current_year = get_year_status(guild=guild_config.id)
    year_span = await get_year_span(current_year, guild=guild_config.id)

    embed = make_embed('Year Stats')

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


def _embed_summary(e: discord.Embed, index: int) -> tuple[str, str]:
    """build a (name, value) pair summarizing a single embed for the debug response."""
    parts = []
    if e.title:
        parts.append(f'**{e.title}**')
    if e.description:
        snippet = (e.description[:120] + '...') if len(e.description) > 120 else e.description
        parts.append(snippet)
    if e.fields:
        parts.append(f'*{len(e.fields)} field(s)*')
    if e.image and e.image.url:
        parts.append(f'image: {e.image.url}')
    return f'embed {index} [{e.type}]', '\n'.join(parts) if parts else '*empty*'


def _message_dump(message: discord.Message, channel_id: int, guild_id: int) -> dict:
    """serialize a message to a dict for json export."""
    return {
        'id': str(message.id),
        'author': {'id': str(message.author.id), 'name': str(message.author)},
        'channel_id': str(channel_id),
        'guild_id': str(guild_id),
        'timestamp': message.created_at.isoformat(),
        'edited_at': message.edited_at.isoformat() if message.edited_at else None,
        'pinned': message.pinned,
        'content': message.content,
        'embeds': [e.to_dict() for e in message.embeds],
        'attachments': [{'id': str(a.id), 'filename': a.filename, 'url': a.url} for a in message.attachments],
        'reactions': [{'emoji': str(r.emoji), 'count': r.count} for r in message.reactions],
        'stickers': [{'id': str(s.id), 'name': s.name} for s in message.stickers],
    }


@debug_group.command(name='message', description='Print message info')
@commands.check(is_bot_owner)
@discord.commands.option(name='link', required=True, description='Message Link', input_type=str)
async def debug_message(ctx: ApplicationContext, link):
    if 'discord.com/channels' not in link:
        await ctx.respond('Failed: not a valid discord message link', ephemeral=True)
        return

    # unpack url
    ids = link.split('/')[-3:]
    guild_id, channel_id, target = int(ids[0]), int(ids[1]), int(ids[2])

    try:
        guild = ctx.bot.get_guild(guild_id)
        channel = cast(discord.TextChannel, guild.get_channel_or_thread(channel_id))

        message: discord.Message | None = None
        async for msg in channel.history(around=snowflake_time(target), limit=15):
            if msg.id == target:
                message = msg
                break

        if message is None:
            await ctx.respond(f"Couldn't find message! {ui_emoji('rockball_player')}")
            return

        # build summary embed
        content_preview = (message.content[:500] + '...') if len(message.content) > 500 else message.content
        embed = make_embed(
            f'Message {message.id}',
            description=content_preview or '*no content*',
            url=message.jump_url,
            timestamp=message.created_at,
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)

        for i, e in enumerate(message.embeds):
            name, value = _embed_summary(e, i + 1)
            embed.add_field(name=name, value=value, inline=False)

        if message.attachments:
            attachment_lines = [f'[{a.filename}]({a.url})' for a in message.attachments]
            embed.add_field(name=f'attachments ({len(message.attachments)})', value='\n'.join(attachment_lines), inline=False)

        meta_parts = [f'channel: <#{channel_id}>', f'edited: {bool(message.edited_at)}', f'pinned: {message.pinned}']
        if message.reactions:
            meta_parts.append('reactions: ' + ' '.join(f'{r.emoji}x{r.count}' for r in message.reactions))
        embed.add_field(name='meta', value='\n'.join(meta_parts), inline=False)

        # full dump as json attachment
        buf = io.BytesIO(json.dumps(_message_dump(message, channel_id, guild_id), indent=2).encode())
        buf.seek(0)

        await ctx.respond(embed=embed, file=discord.File(buf, filename=f'message_{message.id}.json'))

    except Exception as err:
        await ctx.respond(f'could not locate message (check logs) {ui_emoji("rockball_player")}')
        logger.error(f'debug message: {err}')


@debug_group.command(name='dump_config', description='Prints config to console')
@commands.check(is_bot_owner)
async def debug_dump_config(ctx: ApplicationContext):
    logger.info(f'dumping NovaConfig:\n{tomlkit.dumps(config.to_dict(), sort_keys=True)}')

    await ctx.respond('Done!')


@debug_group.command(name='message_stats', description='Shows how many messages are stored for a channel or the whole guild')
@commands.check(is_bot_owner)
@discord.commands.option(name='channel', required=False, description='Channel to query (omit for guild total)', input_type=discord.TextChannel)
async def debug_message_stats(ctx: ApplicationContext, channel: discord.TextChannel | None = None):
    from attubot.client.messages import _get_repo

    try:
        repo = _get_repo()
    except RuntimeError:
        await ctx.respond('Failed: message repo not initialized yet', ephemeral=True)
        return

    if channel is not None:
        count = await repo.count_for_channel(ctx.guild.id, channel.id)
        await ctx.respond(f'{count:,} messages stored for <#{channel.id}>')
    else:
        count = await repo.count_for_guild(ctx.guild.id)
        await ctx.respond(f'{count:,} messages stored for this guild')


_STARBOARD_BOT_ID = 655390915325591629
_STARBOARD_CHANNEL_ID = 1064335304011554877


@debug_group.command(name='dump_starboard', description='Dump 50 random starboard bot messages to a file')
@commands.check(is_bot_owner)
async def debug_dump_starboard(ctx: ApplicationContext):
    await ctx.defer()

    channel = cast(discord.TextChannel, ctx.bot.get_channel(_STARBOARD_CHANNEL_ID))
    if channel is None:
        await ctx.respond('Failed: could not find starboard channel', ephemeral=True)
        return

    # collect all messages from the starboard bot
    found = []
    async for msg in channel.history(limit=None):
        if msg.author.id == _STARBOARD_BOT_ID:
            found.append({
                'id': str(msg.id),
                'timestamp': msg.created_at.isoformat(),
                'content': msg.content,
                'embeds': [e.to_dict() for e in msg.embeds],
                'attachments': [{'id': str(a.id), 'filename': a.filename, 'url': a.url} for a in msg.attachments],
            })

    picked = sample(found, min(50, len(found)))
    picked.sort(key=lambda m: m['timestamp'])

    buf = io.BytesIO(json.dumps(picked, indent=2).encode())
    buf.seek(0)

    await ctx.respond(f'found {len(found)} total, dumping {len(picked)}', file=discord.File(buf, filename='starboard_dump.json'))


_RARITY_CHOICES = ['common', 'uncommon', 'rare', 'legendary', 'mythical']


@debug_eggs.command(name='show', description='Show rarity egg emoji and hatch pool')
@commands.check(is_bot_owner)
@discord.commands.option(name='rarity', required=True, description='Egg rarity', choices=_RARITY_CHOICES, input_type=str)
async def debug_eggs_show(ctx: ApplicationContext, rarity: str):
    emoji_id = config.theme.egg_emojis.get(rarity)
    egg_str = f'<:{rarity}_egg:{emoji_id}>' if emoji_id else f':{rarity}_egg:'
    pool_str = ' '.join(config.hatch.pools[rarity])

    await ctx.respond(f'{egg_str}\n{pool_str}')


@debug_eggs.command(name='preview', description='Run the full hatch animation in this channel (no DB writes)')
@commands.check(is_bot_owner)
@discord.commands.option(name='rarity', required=True, description='Egg rarity', choices=_RARITY_CHOICES, input_type=str)
async def debug_eggs_preview(ctx: ApplicationContext, rarity: str):
    import random as _random

    from attubot.eggs.hatching import run_hatch_animation

    emoji_id = config.theme.egg_emojis.get(rarity)
    egg_str = f'<:{rarity}_egg:{emoji_id}>' if emoji_id else f':{rarity}_egg:'
    result = _random.choice(config.hatch.pools[rarity])

    # post the egg message and run animation (no db writes)
    msg = await ctx.channel.send(egg_str)
    await ctx.respond('hatching preview started', ephemeral=True)
    await run_hatch_animation(msg, result, rarity)


@debug_group.command(name='progress_bar', description='Preview the progress bar at each 10% increment')
@commands.check(is_bot_owner)
async def debug_progress_bar(ctx: ApplicationContext):
    from attubot.eggs.emojis import render_progress_bar

    bar = render_progress_bar(1, 10)
    msg = await ctx.channel.send(f'10% {bar}')
    await ctx.respond('progress bar preview started', ephemeral=True)

    for step in range(2, 11):
        await asyncio.sleep(2)
        bar = render_progress_bar(step, 10)
        await msg.edit(content=f'{step * 10}% {bar}')


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(cast(ApplicationCommand, command_color))
    bot.add_application_command(cast(ApplicationCommand, command_pong))
    # bot.add_application_command(cast(ApplicationCommand, command_test))
    bot.add_application_command(debug_group)
