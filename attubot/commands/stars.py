"""
AttuBot - Stars Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from typing import cast

import discord
from discord import ApplicationCommand, ApplicationContext, Bot, SlashCommandGroup

from attubot import config
from attubot.client.util import theme_color
from attubot.logging import get_logger


logger = get_logger(__name__)

# page size for leaderboard commands
_PAGE_SIZE = 10

stars_group = SlashCommandGroup('stars', description='Starboard browsing and leaderboards')


def _get_sb_repo():
    from attubot.client.starboard import _get_repo

    return _get_repo()


def _get_msg_repo():
    from attubot.client.messages import _get_repo

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

    from attubot.client.starboard import build_content, build_embeds, dominant_color

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
        from attubot.client.messages import build_message_doc

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
    from attubot.client.starboard import backfill_message_reactions, parse_jump_url

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

    try:
        guild_config = config.guild(ctx.guild.id)
    except Exception as err:
        await ctx.respond(f'could not load guild config: {err}', ephemeral=True)
        return

    await ctx.defer()

    from attubot import bot as _bot
    from attubot.client.messages import _get_repo as _get_msg_repo
    from attubot.client.messages import build_message_doc

    logger.debug(f'recheck: message {message_id} in channel {channel_id}')

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

    # handle messages in the starboard channel
    force = False
    sb = guild_config.starboard
    if sb.channel_id and channel_id == sb.channel_id:
        if discord_msg.author.bot:
            # this is a starboard post - redirect recheck to the original message
            sb_doc = await _get_sb_repo().get_by_starboard_message(message_id)
            if sb_doc is None:
                await ctx.respond('that looks like a starboard post but no matching original message was found', ephemeral=True)
                return
            original_id = message_id
            channel_id = sb_doc.channel_id
            message_id = sb_doc.message_id
            logger.info(f'recheck: bot message in starboard channel - redirecting to original {message_id} (was {original_id})')
            try:
                orig_channel = _bot.get_channel(channel_id) or await _bot.fetch_channel(channel_id)
                discord_msg = await orig_channel.fetch_message(message_id)
                orig_doc = await build_message_doc(discord_msg)
                await _get_msg_repo().upsert(orig_doc)
            except Exception as err:
                await ctx.respond(f'could not fetch original message: {err}', ephemeral=True)
                return
        else:
            # non-bot message in the starboard channel - force-bypass the channel guard
            logger.info(f'recheck: non-bot message in starboard channel - force backfilling {message_id}')
            force = True

    doc_before = await _get_sb_repo().get(message_id)

    await backfill_message_reactions(discord_msg, ctx.guild.id, force=force)

    doc_after = await _get_sb_repo().get(message_id)

    # determine update status
    if doc_after is None or (not doc_after.reactions and not doc_after.super_reactions):
        status = 'no stars counted'
    elif doc_before is None and doc_after.starboard_message_id is not None:
        status = 'post created'
    elif doc_before is not None and doc_before.starboard_message_id is None and doc_after.starboard_message_id is not None:
        status = 'post created'
    elif doc_before is None or doc_before.total_reactions != doc_after.total_reactions:
        status = 'updated'
    else:
        status = 'no change'

    logger.info(f'recheck: complete for {message_id} - status={status} weighted_total={doc_after.weighted_total if doc_after else 0}')

    if doc_after is None or (not doc_after.reactions and not doc_after.super_reactions):
        await ctx.respond(f'recheck complete - {status}')
        return

    # format emoji breakdown
    emoji_parts = []
    all_emojis = set(doc_after.reactions) | set(doc_after.super_reactions)
    for emoji in sorted(all_emojis, key=lambda e: -(len(doc_after.reactions.get(e, [])) + len(doc_after.super_reactions.get(e, [])))):
        normal = len(doc_after.reactions.get(emoji, []))
        super_ = len(doc_after.super_reactions.get(emoji, []))
        if normal + super_ == 0:
            continue
        if super_:
            emoji_parts.append(f'{emoji} {normal + super_} ({super_} super)')
        else:
            emoji_parts.append(f'{emoji} {normal}')
    count_str = ' | '.join(emoji_parts) if emoji_parts else 'no stars counted'

    if doc_after.starboard_message_id and sb.channel_id:
        sb_link = f'https://discord.com/channels/{ctx.guild.id}/{sb.channel_id}/{doc_after.starboard_message_id}'
        await ctx.respond(f'recheck complete - {status} - {count_str} | {sb_link}')
    elif doc_after.weighted_total < 2:
        await ctx.respond(f'recheck complete - {status} - {count_str} (below threshold, no post)')
    else:
        await ctx.respond(f'recheck complete - {status} - {count_str}')


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
