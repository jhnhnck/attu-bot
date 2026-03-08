"""
AttuBot - Stars Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from typing import cast

import discord
from discord import ApplicationCommand, ApplicationContext, Bot, SlashCommandGroup

from attubot import config
from attubot.logging import get_logger
from attubot.util import theme_color


logger = get_logger(__name__)

# page size for leaderboard commands
_PAGE_SIZE = 10

stars_group = SlashCommandGroup('stars', description='Starboard browsing and leaderboards')


def _get_sb_repo():
    from attubot.starboard import _get_repo

    return _get_repo()


def _get_msg_repo():
    from attubot.messages import _get_repo

    return _get_repo()


async def _show_random_message(ctx: ApplicationContext, min_total: int, max_total: int | None = None) -> None:
    """fetch and display a random starred message matching the reaction count range."""
    try:
        sb_repo = _get_sb_repo()
    except RuntimeError:
        await ctx.respond('starboard not initialized yet', ephemeral=True)
        return

    guild_id = ctx.guild.id
    doc = await sb_repo.get_random(guild_id, min_total=min_total, max_total=max_total)

    if doc is None:
        label = 'exactly 1 star' if max_total == 1 else f'{min_total}+ stars'
        await ctx.respond(f'no messages found with {label}', ephemeral=True)
        return

    try:
        guild_config = config.guild(guild_id)
    except Exception:
        await ctx.respond('guild configuration not found', ephemeral=True)
        return

    from attubot.starboard import build_content, build_embeds, dominant_color

    msg_repo = _get_msg_repo()
    msg_doc = await msg_repo.get(doc.message_id)

    if msg_doc is None:
        await ctx.respond('original message not found in database', ephemeral=True)
        return

    sb = guild_config.starboard
    jump_url = f'https://discord.com/channels/{guild_id}/{msg_doc.channel_id}/{msg_doc.message_id}'
    content = build_content(doc.reactions, jump_url, sb.emojis) if doc.reactions else f'⭐ **{doc.total_reactions}** | {jump_url}'
    color = dominant_color(doc.reactions, sb.emojis) if doc.reactions else theme_color()
    embeds = await build_embeds(msg_doc, guild_id, color)

    await ctx.respond(content=content, embeds=embeds)
    try:
        from attubot.messages import build_message_doc

        interaction = ctx.interaction
        if interaction is None:
            raise RuntimeError('missing interaction for random starboard response')
        response_msg = await interaction.original_response()
        response_doc = await build_message_doc(response_msg)
        response_doc.refs.starboard_post = doc.message_id
        await msg_repo.upsert(response_doc)
    except Exception as err:
        logger.warn(f'starboard: could not store random response message - {err}')


@stars_group.command(name='random', description='Shows a random message with 2 or more stars')
async def stars_random(ctx: ApplicationContext):
    await _show_random_message(ctx, min_total=2)


@stars_group.command(name='lost', description='Shows a random message with exactly 1 star')
async def stars_lost(ctx: ApplicationContext):
    await _show_random_message(ctx, min_total=1, max_total=1)


@stars_group.command(name='recheck', description='Force-updates the starboard post for a specific message')
@discord.commands.option(name='message_link', required=True, description='Full Discord message link to recheck')
async def stars_recheck(ctx: ApplicationContext, message_link: str):
    from attubot.starboard import backfill_message_reactions, parse_jump_url

    parsed = parse_jump_url(message_link.strip())
    if parsed is None:
        await ctx.respond('invalid message link - paste the full discord message link', ephemeral=True)
        return

    _link_guild_id, channel_id, message_id = parsed
    if _link_guild_id != ctx.guild.id:
        await ctx.respond('that message link is from a different server', ephemeral=True)
        return

    try:
        _get_sb_repo()
    except RuntimeError:
        await ctx.respond('starboard not initialized yet', ephemeral=True)
        return

    await ctx.defer()

    from attubot import bot as _bot
    from attubot.messages import _get_repo as _get_msg_repo
    from attubot.messages import build_message_doc

    try:
        channel = _bot.get_channel(channel_id) or await _bot.fetch_channel(channel_id)
        discord_msg = await channel.fetch_message(message_id)
    except Exception as err:
        await ctx.respond(f'could not fetch message: {err}', ephemeral=True)
        return

    # ensure the message is stored so build_embeds etc. can find it
    try:
        msg_doc = await build_message_doc(discord_msg)
        await _get_msg_repo().upsert(msg_doc)
    except Exception as err:
        logger.warn(f'recheck: failed to store message {message_id}: {err}')

    await backfill_message_reactions(discord_msg, ctx.guild.id)

    try:
        guild_config = config.guild(ctx.guild.id)
        sb_doc = await _get_sb_repo().get(message_id)
        if sb_doc and sb_doc.starboard_message_id:
            sb_link = f'https://discord.com/channels/{ctx.guild.id}/{guild_config.starboard.channel_id}/{sb_doc.starboard_message_id}'
            await ctx.respond(f'recheck complete - {sb_link}')
            return
    except Exception as err:
        logger.warn(f'recheck: could not resolve starboard post link for message {message_id}: {err}')
    await ctx.respond('recheck complete')


async def _leaderboard_embed(ctx: ApplicationContext, rows: list[dict], value_key: str, value_label: str, title: str) -> None:
    """build and send a numbered leaderboard embed."""
    if not rows:
        await ctx.respond(f'no data yet for {title.lower()}', ephemeral=True)
        return

    lines = []
    for i, row in enumerate(rows[:_PAGE_SIZE], start=1):
        user_id = row['_id']
        value = row[value_key]
        lines.append(f'**{i}.** <@{user_id}> - **{value}** {value_label}')

    embed = discord.Embed(title=title, description='\n'.join(lines), color=theme_color())
    await ctx.respond(embed=embed)


@stars_group.command(name='most-stars', description='Top users by total stars received')
async def stars_most_stars(ctx: ApplicationContext):
    try:
        sb_repo = _get_sb_repo()
    except RuntimeError:
        await ctx.respond('starboard not initialized yet', ephemeral=True)
        return

    rows = await sb_repo.leaderboard_most_stars(ctx.guild.id, limit=_PAGE_SIZE)
    await _leaderboard_embed(ctx, rows, 'total_stars', 'stars received', 'Most Stars Received')


@stars_group.command(name='most-starred', description='Top users by number of messages on the starboard')
async def stars_most_starred(ctx: ApplicationContext):
    try:
        sb_repo = _get_sb_repo()
    except RuntimeError:
        await ctx.respond('starboard not initialized yet', ephemeral=True)
        return

    rows = await sb_repo.leaderboard_most_starred(ctx.guild.id, limit=_PAGE_SIZE)
    await _leaderboard_embed(ctx, rows, 'starred_messages', 'messages starred', 'Most Messages Starred')


@stars_group.command(name='most-given', description='Top users by total stars given')
async def stars_most_given(ctx: ApplicationContext):
    try:
        sb_repo = _get_sb_repo()
    except RuntimeError:
        await ctx.respond('starboard not initialized yet', ephemeral=True)
        return

    rows = await sb_repo.leaderboard_most_given(ctx.guild.id, limit=_PAGE_SIZE)
    await _leaderboard_embed(ctx, rows, 'total_given', 'stars given', 'Most Stars Given')


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(cast(ApplicationCommand, stars_group))
