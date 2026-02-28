"""
AttuBot - Fix Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from typing import cast

import discord
from discord import ApplicationCommand, ApplicationContext, Bot, Interaction, Permissions, SlashCommandGroup
from discord.ext import commands

from attubot import config
from attubot.logging import get_logger
from attubot.tasks import LogoUpdateTask, scheduler
from attubot.tasks.nova_year import job_construct_year_links
from attubot.util import is_bot_owner

logger = get_logger(__name__)

async def job_backfill_channel(channel_id: int, guild_id: int, interaction: discord.Interaction | None = None):
    """scan a channel and backfill any messages not already stored."""
    from attubot import bot
    from attubot.messages import _get_repo, build_message_doc

    repo = _get_repo()
    channel = bot.get_channel(channel_id)

    if channel is None:
        logger.error(f'fix messages: channel {channel_id} not found in cache')
        if interaction is not None:
            await interaction.edit_original_response(content=f'Error: channel {channel_id} not found')
        return

    # fetch all known ids upfront to avoid a db roundtrip per message
    stored_ids = await repo.get_all_message_ids_in_channel(guild_id, channel.id)
    stored = 0
    backfilled = 0

    try:
        async for message in channel.history(oldest_first=True, limit=None):
            if message.id in stored_ids:
                stored += 1
            else:
                try:
                    doc = await build_message_doc(message)
                    await repo.upsert(doc)
                    backfilled += 1
                except Exception as err:
                    logger.warn(f'fix messages: failed to store message {message.id}: {err}')

            total = stored + backfilled
            if total % 1000 == 0:
                logger.debug(f'fix messages #{channel.name}: scanned {total:,} messages, {backfilled:,} backfilled so far')

    except discord.Forbidden:
        logger.warn(f'fix messages: no permission to read history in #{channel.name} ({channel_id})')
        if interaction is not None:
            await interaction.edit_original_response(content=f'No permission to read history in <#{channel_id}>')
        return
    except Exception as err:
        logger.error(f'fix messages: error scanning channel {channel_id}: {err}')
        if interaction is not None:
            await interaction.edit_original_response(content=f'Error scanning <#{channel_id}> - check logs')
        return

    total = stored + backfilled
    logger.info(f'fix messages #{channel.name}: done - {total:,} scanned, {backfilled:,} backfilled')

    if interaction is not None:
        await interaction.edit_original_response(content=f'Done! Scanned {total:,} messages in <#{channel_id}>: {stored:,} already stored, {backfilled:,} backfilled')


async def job_fix_author_names(guild_id: int, interaction: discord.Interaction | None = None, user_id: int | None = None):
    """resolve current global usernames and bulk-update author_name on all stored messages."""
    from attubot import bot
    from attubot.messages import _get_repo, _global_username

    repo = _get_repo()

    if user_id is not None:
        author_ids = [user_id]
    else:
        author_ids = await repo.distinct_author_ids(guild_id)
        logger.info(f'fix author_names: found {len(author_ids)} distinct authors for guild {guild_id}')

    updated_msgs = 0
    resolved = 0
    not_found = 0

    for i, author_id in enumerate(author_ids):
        try:
            user = await bot.get_or_fetch(discord.User, author_id)
            if user is None:
                not_found += 1
                logger.warn(f'fix author_names: could not resolve user {author_id}: user not found')
                continue
            name = _global_username(user)
            count = await repo.update_author_name(author_id, name)
            updated_msgs += count
            resolved += 1
        except Exception as err:
            not_found += 1
            logger.warn(f'fix author_names: could not resolve user {author_id}: {err}')

        if (i + 1) % 50 == 0 and interaction is not None:
            await interaction.edit_original_response(content=f'Progress: {i + 1}/{len(author_ids)} users processed...')

    summary = f'Done - {resolved} users resolved, {updated_msgs:,} messages updated'
    if not_found:
        summary += f', {not_found} users not found'

    logger.info(f'fix author_names: {summary} (guild {guild_id})')

    if interaction is not None:
        await interaction.edit_original_response(content=summary)


fix_group = SlashCommandGroup('fix', default_member_permissions=Permissions.all(), description='Commands to repair or rebuild bot state')


@fix_group.command(name='logo', description='Forces the logo update task to run immediately')
@commands.check(is_bot_owner)
async def fix_logo(ctx: ApplicationContext):
    logger.info('logo update forced by admin')
    task = LogoUpdateTask()

    await ctx.respond('Refreshing logo!')
    await task.run()


@fix_group.command(name='year_links', description='Forces the year links channel to be rebuilt immediately')
@commands.check(is_bot_owner)
async def fix_year_links(ctx: ApplicationContext):
    logger.info('year links update forced by admin')
    cfg = config.guild(ctx.guild.id)

    await ctx.respond(f'Starting year links rebuild on <#{cfg.channels.year_links}>')
    scheduler.add_job(job_construct_year_links(ctx.guild.id), 'Job[construct_year_links]')


@fix_group.command(name='messages', description='Verifies all messages in a channel are stored and backfills any missing ones')
@commands.check(is_bot_owner)
@discord.commands.option(name='channel', required=True, description='Channel to verify', input_type=discord.TextChannel)
async def fix_messages(ctx: ApplicationContext, channel: discord.TextChannel):
    from attubot.messages import _get_repo

    try:
        _get_repo()
    except RuntimeError:
        await ctx.respond('message repo not initialized yet', ephemeral=True)
        return

    response = await ctx.respond(f'Scanning <#{channel.id}>...')
    scheduler.add_job(job_backfill_channel(channel.id, ctx.guild.id, response if isinstance(response, Interaction) else None), f'Job[fix_messages:#{channel.name}]')


@fix_group.command(name='author_names', description='Re-resolves global usernames and updates all stored messages')
@commands.check(is_bot_owner)
@discord.commands.option(name='user', required=False, description='Only update messages from this user', input_type=discord.User)
async def fix_author_names(ctx: ApplicationContext, user: discord.User | None = None):
    from attubot.messages import _get_repo

    try:
        _get_repo()
    except RuntimeError:
        await ctx.respond('message repo not initialized yet', ephemeral=True)
        return

    if user is not None:
        msg = f'Updating author name for <@{user.id}>...'
        label = f'Job[fix_author_names:{user.id}]'
        _response = await ctx.respond(msg)
        coro = job_fix_author_names(ctx.guild.id, interaction=_response if isinstance(_response, Interaction) else None, user_id=user.id)
    else:
        msg = 'Resolving all author names...'
        label = 'Job[fix_author_names:all]'
        _response = await ctx.respond(msg)
        coro = job_fix_author_names(ctx.guild.id, interaction=_response if isinstance(_response, Interaction) else None)

    scheduler.add_job(coro, label)


async def job_learn_starboard(guild_id: int, interaction: discord.Interaction | None = None):
    """two-step ingestion: backfill the starboard channel, then parse stored messages into starboard documents."""
    from attubot import config
    from attubot.messages import _get_repo as _get_msg_repo
    from attubot.starboard import _get_repo as _get_sb_repo, parse_jump_url, parse_starboard_content

    try:
        guild_config = config.guild(guild_id)
    except Exception as err:
        if interaction is not None:
            await interaction.edit_original_response(content=f'Error: {err}')
        return

    sb = guild_config.starboard
    if not sb.channel_id:
        if interaction is not None:
            await interaction.edit_original_response(content='No starboard channel configured')
        return

    # step 1: ensure all starboard channel messages are stored locally
    if interaction is not None:
        await interaction.edit_original_response(content=f'Step 1/2: backfilling <#{sb.channel_id}>...')

    await job_backfill_channel(sb.channel_id, guild_id)

    # step 2: scan all stored starboard messages and build StarredMessageDocument records
    if interaction is not None:
        await interaction.edit_original_response(content='Step 2/2: parsing starboard messages...')

    msg_repo = _get_msg_repo()
    sb_repo = _get_sb_repo()

    # fetch all stored messages from the starboard channel
    from attubot.database.repositories import MessageRepository
    cursor = msg_repo.db[MessageRepository.COLLECTION].find({'guild_id': guild_id, 'channel_id': sb.channel_id})
    stored_msgs = await cursor.to_list(length=None)

    created = 0
    skipped = 0
    errors = 0

    for raw in stored_msgs:
        try:
            content = raw.get('content', '')
            if not content:
                skipped += 1
                continue

            emoji_counts, jump_url = parse_starboard_content(content)
            if not jump_url or not emoji_counts:
                skipped += 1
                continue

            parsed = parse_jump_url(jump_url)
            if parsed is None:
                skipped += 1
                continue

            _orig_guild_id, orig_channel_id, orig_message_id = parsed

            # skip if we already have this starboard document
            if await sb_repo.get(orig_message_id) is not None:
                skipped += 1
                continue

            # look up the original message to get author_id
            orig_doc = await msg_repo.get(orig_message_id)
            author_id = orig_doc.author_id if orig_doc else 0

            from attubot.database.models import StarredMessageDocument

            total = sum(emoji_counts.values())
            doc = StarredMessageDocument(
                message_id=orig_message_id,
                channel_id=orig_channel_id,
                guild_id=guild_id,
                author_id=author_id,
                starboard_message_id=int(raw['message_id']),
                reactions={},       # individual starrer IDs not available from legacy data
                total_reactions=total,
            )
            await sb_repo.upsert(doc)
            created += 1

        except Exception as err:
            logger.warn(f'learn_starboard: error processing message {raw.get("message_id")}: {err}')
            errors += 1

    summary = f'Done - {created} entries created, {skipped} skipped, {errors} errors'
    logger.info(f'learn_starboard: {summary} (guild {guild_id})')

    if interaction is not None:
        await interaction.edit_original_response(content=summary)


@fix_group.command(name='starboard', description='Backfills the starboard channel then ingests all entries into the database')
@commands.check(is_bot_owner)
async def fix_starboard(ctx: ApplicationContext):
    try:
        from attubot.starboard import _get_repo
        _get_repo()
    except RuntimeError:
        await ctx.respond('starboard repo not initialized yet', ephemeral=True)
        return

    _response = await ctx.respond('Starting starboard ingestion...')
    scheduler.add_job(
        job_learn_starboard(ctx.guild.id, interaction=_response if isinstance(_response, Interaction) else None),
        'Job[fix_starboard]',
    )


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(cast(ApplicationCommand, fix_group))
