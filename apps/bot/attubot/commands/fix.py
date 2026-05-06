"""
AttuBot - Fix Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast

import discord
from discord import ApplicationCommand, ApplicationContext, Bot, Permissions, SlashCommandGroup
from discord.ext import commands

from attubot import bot, config
from attubot.client import messages
from attubot.client.starboard import _get_repo as _get_sb_repo
from attubot.client.starboard import _sync_starboard_post
from attubot.client.util import is_bot_owner
from attubot.logging import get_logger
from attubot.tasks import LogoUpdateTask, scheduler
from attubot.tasks.message_backfill import MessageBackfillTask
from attubot.tasks.nova_year import job_construct_year_links


logger = get_logger(__name__)


async def _safe_edit(status_msg: discord.Message | None, content: str) -> discord.Message | None:
    """edit the status message safely; returns None if the edit fails so callers can stop retrying."""
    if status_msg is None:
        return None
    try:
        await status_msg.edit(content=content)
        return status_msg
    except discord.HTTPException as err:
        logger.warn(f'fix: status message edit failed ({err}), further updates disabled')
        return None


async def job_backfill_channel(
    channel_id: int,
    guild_id: int,
    status_msg: discord.Message | None = None,
    *,
    reconcile_recent: bool = False,
    reconcile_lookback: timedelta | None = None,
    task: MessageBackfillTask | None = None,
):
    """scan a channel and backfill any messages not already stored."""
    from attubot import bot

    channel = bot.get_channel(channel_id)

    if channel is None:
        logger.error(f'fix messages: channel {channel_id} not found in cache')
        await _safe_edit(status_msg, f'Error: channel {channel_id} not found')
        return 0, 0

    backfill_task = task or MessageBackfillTask()
    backfilled = 0
    reconciled = 0

    try:
        backfilled = await backfill_task._backfill_channel(guild_id, channel)  # pyright: ignore[reportArgumentType]
    except Exception as err:
        logger.error(f'fix messages: error scanning channel {channel_id}: {err}')
        await _safe_edit(status_msg, f'Error scanning <#{channel_id}>; check logs')
        return 0, 0

    if reconcile_recent:
        try:
            reconciled = await backfill_task._reconcile_recent_channel(guild_id, channel, lookback=reconcile_lookback)  # pyright: ignore[reportArgumentType]
        except Exception as err:
            logger.warn(f'fix messages: recent reconcile failed for {channel_id}: {err}')

    summary = f'Done! Backfilled {backfilled:,} messages in <#{channel_id}>'
    if reconcile_recent:
        summary += f', reconciled {reconciled:,} recent entries'

    await _safe_edit(status_msg, summary)

    return backfilled or 0, reconciled or 0


async def job_fix_author_names(guild_id: int, status_msg: discord.Message | None = None, user_id: int | None = None):
    """resolve current global usernames and bulk-update author_name on all stored messages."""
    from attubot import bot
    from attubot.client.messages import _global_username

    repo = messages._get_repo()

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

        if (i + 1) % 50 == 0:
            status_msg = await _safe_edit(status_msg, f'Progress: {i + 1}/{len(author_ids)} users processed...')

    summary = f'Done - {resolved} users resolved, {updated_msgs:,} messages updated'
    if not_found:
        summary += f', {not_found} users not found'

    logger.info(f'fix author_names: {summary} (guild {guild_id})')

    await _safe_edit(status_msg, summary)


fix_group = SlashCommandGroup('fix', default_member_permissions=Permissions.all(), description='Commands to repair or rebuild bot state')
fix_starboard = fix_group.create_subgroup('starboard', 'Commands to repair starboard state')


@fix_group.command(name='logo', description='Forces the logo update task to run immediately')
@commands.check(is_bot_owner)
async def fix_logo(ctx: ApplicationContext):
    logger.info('logo update forced by admin')
    task = LogoUpdateTask()

    await ctx.respond('Refreshing!')
    await task.run()


@fix_group.command(name='year_links', description='Forces the year links channel to be rebuilt immediately')
@commands.check(is_bot_owner)
async def fix_year_links(ctx: ApplicationContext):
    logger.info('year links update forced by admin')
    cfg = config.guild(ctx.guild.id)

    await ctx.respond(f'starting year links rebuild on <#{cfg.channels.year_links}>')
    scheduler.add_job(job_construct_year_links(ctx.guild.id), 'Job', 'construct_year_links')


@fix_group.command(name='messages', description='Verifies all messages in a channel are stored and backfills any missing ones')
@commands.check(is_bot_owner)
@discord.commands.option(name='channel', required=True, description='Channel to verify', input_type=discord.TextChannel)
async def fix_messages(ctx: ApplicationContext, channel: discord.TextChannel):

    try:
        messages._get_repo()
    except RuntimeError:
        await ctx.respond('Failed: message repo not initialized yet', ephemeral=True)
        return

    await ctx.respond(f'scanning <#{channel.id}>...', ephemeral=True)
    status_msg = await ctx.channel.send(f'Scanning <#{channel.id}>...')
    scheduler.add_job(job_backfill_channel(channel.id, ctx.guild.id, status_msg), 'Job', 'fix_messages', f'#{channel.name}')


@fix_group.command(name='author_names', description='Re-resolves global usernames and updates all stored messages')
@commands.check(is_bot_owner)
@discord.commands.option(name='user', required=False, description='Only update messages from this user', input_type=discord.User)
async def fix_author_names(ctx: ApplicationContext, user: discord.User | None = None):

    try:
        messages._get_repo()
    except RuntimeError:
        await ctx.respond('Failed: message repo not initialized yet', ephemeral=True)
        return

    if user is not None:
        await ctx.respond(f'updating author name for <@{user.id}>...', ephemeral=True)
        status_msg = await ctx.channel.send(f'Updating author name for <@{user.id}>...')
        scheduler.add_job(job_fix_author_names(ctx.guild.id, status_msg=status_msg, user_id=user.id), 'Job', 'fix_author_names', user.id)
    else:
        await ctx.respond('resolving all author names...', ephemeral=True)
        status_msg = await ctx.channel.send('Resolving all author names...')
        scheduler.add_job(job_fix_author_names(ctx.guild.id, status_msg=status_msg), 'Job', 'fix_author_names', 'all')


async def job_recount_starboard(guild_id: int, status_msg: discord.Message | None = None):  # noqa: PLR0912, PLR0915 - live discord fetch loop with many error/skip branches
    """fetch live reaction counts from discord for all starred messages and rebuild per-user reaction lists."""
    from attubot import bot, config
    from attubot.client.starboard import _get_repo as _get_sb_repo
    from attubot.database.models import StarredMessageDocument

    try:
        guild_config = config.guild(guild_id)
    except Exception as err:
        await _safe_edit(status_msg, f'Error: {err}')
        return

    sb = guild_config.starboard
    if not sb.channel_id:
        await _safe_edit(status_msg, 'No starboard channel configured')
        return

    sb_repo = _get_sb_repo()
    all_docs = await sb_repo.all_for_guild(guild_id)

    if not all_docs:
        await _safe_edit(status_msg, 'No starred messages found')
        return

    updated = 0
    skipped = 0
    errors = 0

    for i, doc in enumerate(all_docs):
        try:
            new_reactions: dict[str, set[int]] = {emoji: set() for emoji in sb.emojis}
            author_id = doc.author_id

            # fetch the original message for live reactions
            try:
                orig_channel = bot.get_channel(doc.channel_id)
                if orig_channel is None:
                    orig_channel = await bot.fetch_channel(doc.channel_id)
                orig_msg = await orig_channel.fetch_message(doc.message_id)
                author_id = orig_msg.author.id
                for reaction in orig_msg.reactions:
                    emoji_str = str(reaction.emoji)
                    if emoji_str in sb.emojis:
                        async for user in reaction.users():
                            if user.id != author_id and not user.bot:
                                new_reactions[emoji_str].add(user.id)
            except (discord.NotFound, discord.Forbidden):
                skipped += 1
                continue
            except Exception as err:
                logger.warn(f'recount_starboard: failed to fetch original message {doc.message_id}: {err}')
                errors += 1
                continue

            # also collect reactions from the starboard post if it exists
            if doc.starboard_message_id:
                try:
                    sb_channel = bot.get_channel(sb.channel_id)
                    if sb_channel is None:
                        sb_channel = await bot.fetch_channel(sb.channel_id)
                    sb_msg = await sb_channel.fetch_message(doc.starboard_message_id)
                    for reaction in sb_msg.reactions:
                        emoji_str = str(reaction.emoji)
                        if emoji_str in sb.emojis:
                            async for user in reaction.users():
                                if user.id != author_id and not user.bot:
                                    new_reactions[emoji_str].add(user.id)
                except (discord.NotFound, discord.Forbidden):
                    pass  # starboard post gone or unreadable - skip but don't fail the entry
                except Exception as err:
                    logger.warn(f'recount_starboard: failed to fetch starboard post {doc.starboard_message_id}: {err}')

            reactions_dict = {emoji: sorted(users) for emoji, users in new_reactions.items() if users}
            total = sum(len(v) for v in reactions_dict.values())

            # skip if reactions haven't changed; avoids unnecessary edits (and 401s from old posts)
            old_reactions_dict = {k: sorted(v) for k, v in doc.reactions.items() if v}
            if reactions_dict == old_reactions_dict and total == doc.total_reactions:
                skipped += 1
                continue

            old_total = doc.total_reactions
            logger.info(f'recount_starboard: message {doc.message_id} updated ({old_total} -> {total} stars)')

            updated_doc = StarredMessageDocument(
                message_id=doc.message_id,
                channel_id=doc.channel_id,
                guild_id=doc.guild_id,
                author_id=author_id,
                starboard_message_id=doc.starboard_message_id,
                reactions=reactions_dict,
                total_reactions=total,
            )
            await sb_repo.upsert(updated_doc)
            await _sync_starboard_post(guild_id, updated_doc, guild_config)
            updated += 1

        except Exception as err:
            logger.warn(f'recount_starboard: unexpected error for message {doc.message_id}: {err}')
            errors += 1
        finally:
            # runs on every iteration including those that hit `continue`
            if (i + 1) % 25 == 0:
                status_msg = await _safe_edit(status_msg, f'Progress: {i + 1}/{len(all_docs)} messages recounted...')

    summary = f'Done - {updated} updated, {skipped} skipped, {errors} errors'
    logger.info(f'recount_starboard: {summary} (guild {guild_id})')

    await _safe_edit(status_msg, summary)


async def job_regen_starboard(guild_id: int, status_msg: discord.Message | None = None):
    from attubot import config
    from attubot.client.starboard import _sync_starboard_post

    try:
        guild_config = config.guild(guild_id)
    except Exception as err:
        await _safe_edit(status_msg, f'Error: {err}')
        return

    sb = guild_config.starboard
    if not sb.channel_id:
        await _safe_edit(status_msg, 'No starboard channel configured')
        return

    sb_repo = _get_sb_repo()
    all_docs = await sb_repo.all_for_guild(guild_id)

    if not all_docs:
        await _safe_edit(status_msg, 'No starred messages found; run /fix starboard first')
        return

    processed = 0
    errors = 0

    for i, doc in enumerate(all_docs):
        try:
            await _sync_starboard_post(guild_id, doc, guild_config)
            processed += 1
        except Exception as err:
            logger.warn(f'regen_starboard: failed for message {doc.message_id}: {err}')
            errors += 1
        finally:
            if (i + 1) % 25 == 0:
                status_msg = await _safe_edit(status_msg, f'Progress: {i + 1}/{len(all_docs)} posts regenerated...')

    summary = f'Done - {processed} posts regenerated'
    if errors:
        summary += f', {errors} errors'
    logger.info(f'regen_starboard: {summary} (guild {guild_id})')

    await _safe_edit(status_msg, summary)


async def job_reconcile_guild(guild_id: int, status_msg: discord.Message | None = None, *, lookback: timedelta | None = None):
    """Run a full reconciliation pass across all readable channels and threads."""
    task = MessageBackfillTask()

    guild_obj = bot.get_guild(guild_id)
    if guild_obj is None:
        await _safe_edit(status_msg, 'Guild not in cache')
        return

    me = guild_obj.me
    if me is None:
        await _safe_edit(status_msg, 'Bot member not ready')
        return

    try:
        guild_config = config.guild(guild_id)
    except Exception as err:
        await _safe_edit(status_msg, f'Error: {err}')
        return

    try:
        channels = await task._collect_channels(guild_obj, guild_config.channels.logs, me)
    except Exception as err:
        await _safe_edit(status_msg, f'Unable to collect channels: {err}')
        return

    total_backfilled = 0
    total_reconciled = 0

    for channel in channels:
        status_msg = await _safe_edit(status_msg, f'Scanning <#{channel.id}>...')
        backfilled, reconciled = await job_backfill_channel(
            channel.id,
            guild_id,
            status_msg=status_msg,
            reconcile_recent=True,
            reconcile_lookback=lookback,
            task=task,
        )
        total_backfilled += backfilled or 0
        total_reconciled += reconciled or 0

    summary = f'Reconcile complete: {total_backfilled} backfilled, {total_reconciled} reconciled'
    await _safe_edit(status_msg, summary)


@fix_group.command(name='reconcile', description='Scans the guild and reconciles recent history and starboard state')
@commands.check(is_bot_owner)
@discord.commands.option(name='days', required=False, description='Lookback window in days (default 1)', input_type=int)
async def fix_reconcile(ctx: ApplicationContext, days: int = 1):

    try:
        messages._get_repo()
    except RuntimeError:
        await ctx.respond('Failed: message repo not initialized yet', ephemeral=True)
        return

    await ctx.respond(f'starting full reconciliation (last {days} day(s))...', ephemeral=True)
    status_msg = await ctx.channel.send(f'Starting full reconciliation (last {days} day(s))...')
    scheduler.add_job(job_reconcile_guild(ctx.guild.id, status_msg=status_msg, lookback=timedelta(days=days)), 'Job', 'fix_reconcile')


async def job_recover_starboard_from_channel(guild_id: int, days: int = 7, status_msg: discord.Message | None = None):  # noqa: PLR0912, PLR0915 - recovery scan with many error/skip branches
    """scan the starboard channel for bot posts and restore any missing starred_message docs or broken links."""
    from discord.utils import time_snowflake

    from attubot import bot, config
    from attubot.client.starboard import _get_repo as _get_sb_repo_inner
    from attubot.client.starboard import _sync_starboard_post as _sync_post
    from attubot.client.starboard import parse_jump_url
    from attubot.database.models import StarredMessageDocument

    try:
        guild_config = config.guild(guild_id)
    except Exception as err:
        await _safe_edit(status_msg, f'Error: {err}')
        return

    sb = guild_config.starboard
    if not sb.channel_id:
        await _safe_edit(status_msg, 'No starboard channel configured')
        return

    sb_channel = bot.get_channel(sb.channel_id)
    if sb_channel is None:
        try:
            sb_channel = await bot.fetch_channel(sb.channel_id)
        except Exception as err:
            await _safe_edit(status_msg, f'Could not fetch starboard channel: {err}')
            return

    sb_repo = _get_sb_repo_inner()
    since = datetime.now(tz=UTC) - timedelta(days=days)
    after = discord.Object(id=time_snowflake(since))

    created = 0
    link_fixed = 0
    already_ok = 0
    errors = 0

    try:
        history = sb_channel.history(after=after, oldest_first=True, limit=None)  # type: ignore[union-attr]
        async for sb_msg in history:
            # only consider posts made by this bot
            if bot.user is None or sb_msg.author.id != bot.user.id:
                continue

            # extract the original message jump url from content (format: "⭐ **N** | ... | https://discord.com/channels/G/C/M")
            jump_url = None
            for token in sb_msg.content.split():
                if token.startswith('https://discord.com/channels/'):
                    jump_url = token
                    break
            if not jump_url:
                continue

            parsed = parse_jump_url(jump_url)
            if parsed is None:
                continue

            _guild_id, orig_channel_id, orig_message_id = parsed
            if _guild_id != guild_id:
                continue

            try:
                doc = await sb_repo.get(orig_message_id)

                if doc is not None and doc.starboard_message_id == sb_msg.id:
                    already_ok += 1
                    continue

                if doc is not None:
                    # doc exists but link is wrong or missing; fix the pointer and re-sync
                    await sb_repo.set_starboard_message(doc.message_id, sb_msg.id)
                    updated = await sb_repo.get(doc.message_id)
                    if updated:
                        await _sync_post(guild_id, updated, guild_config)
                    link_fixed += 1
                    logger.info(f'recover_starboard: fixed link for message {orig_message_id} -> post {sb_msg.id}')
                    continue

                # doc does not exist; fetch the original message and build a new doc
                orig_channel = bot.get_channel(orig_channel_id)
                if orig_channel is None:
                    orig_channel = await bot.fetch_channel(orig_channel_id)
                orig_msg = await orig_channel.fetch_message(orig_message_id)  # type: ignore[union-attr]

                # collect per-emoji reaction lists (no auto-removal in recovery mode)
                seen_voters: set[int] = set()
                new_reactions: dict[str, list[int]] = {}
                for reaction in orig_msg.reactions:
                    emoji_str = str(reaction.emoji)
                    if emoji_str not in sb.emojis:
                        continue
                    users: list[int] = []
                    async for user in reaction.users():
                        if user.id == orig_msg.author.id or user.bot:
                            continue
                        if user.id in seen_voters:
                            continue
                        users.append(user.id)
                        seen_voters.add(user.id)
                    if users:
                        new_reactions[emoji_str] = users

                total = sum(len(v) for v in new_reactions.values())
                new_doc = StarredMessageDocument(
                    message_id=orig_message_id,
                    channel_id=orig_channel_id,
                    guild_id=guild_id,
                    author_id=orig_msg.author.id,
                    starboard_message_id=sb_msg.id,
                    reactions=new_reactions,
                    total_reactions=total,
                    weighted_total=float(total),
                )
                await sb_repo.upsert(new_doc)
                await _sync_post(guild_id, new_doc, guild_config)
                created += 1
                logger.info(f'recover_starboard: created doc for message {orig_message_id} from starboard post {sb_msg.id}')

            except (discord.NotFound, discord.Forbidden):
                errors += 1
                logger.warn(f'recover_starboard: could not access original message {orig_message_id}')
            except Exception as err:
                errors += 1
                logger.warn(f'recover_starboard: error processing starboard post {sb_msg.id}: {err}')

    except discord.Forbidden:
        await _safe_edit(status_msg, 'No permission to read starboard channel history')
        return
    except Exception as err:
        await _safe_edit(status_msg, f'Error scanning starboard channel: {err}')
        return

    summary = f'Done - {created} created, {link_fixed} links fixed, {already_ok} already ok'
    if errors:
        summary += f', {errors} errors'
    logger.info(f'recover_starboard: {summary} (guild {guild_id})')
    await _safe_edit(status_msg, summary)


@fix_starboard.command(name='recover', description='Scans the starboard channel for bot posts and restores any missing DB records or broken links')
@commands.check(is_bot_owner)
@discord.commands.option(name='days', required=False, description='How many days back to scan (default 7)', input_type=int)
async def fix_starboard_recover(ctx: ApplicationContext, days: int = 7):
    try:
        _get_sb_repo()
    except RuntimeError:
        await ctx.respond('Failed: starboard repo not initialized yet', ephemeral=True)
        return

    await ctx.respond(f'scanning last {days} days of starboard channel...', ephemeral=True)
    status_msg = await ctx.channel.send(f'Scanning last {days} days of starboard channel...')
    scheduler.add_job(job_recover_starboard_from_channel(ctx.guild.id, days=days, status_msg=status_msg), 'Job', 'fix_starboard_recover')


@fix_starboard.command(name='recount', description='Re-fetches live Discord reactions for all starred messages and updates counts')
@commands.check(is_bot_owner)
async def fix_starboard_recount(ctx: ApplicationContext):
    try:
        from attubot.client.starboard import _get_repo

        _get_repo()
    except RuntimeError:
        await ctx.respond('Failed: starboard repo not initialized yet', ephemeral=True)
        return

    await ctx.respond('starting starboard recount...', ephemeral=True)
    status_msg = await ctx.channel.send('Starting starboard recount...')
    scheduler.add_job(job_recount_starboard(ctx.guild.id, status_msg=status_msg), 'Job', 'fix_starboard_recount')


@fix_starboard.command(name='regen', description='Rebuilds every starboard post for this guild')
@commands.check(is_bot_owner)
async def fix_starboard_regen(ctx: ApplicationContext):
    try:
        _get_sb_repo()
    except RuntimeError:
        await ctx.respond('Failed: starboard repo not initialized yet', ephemeral=True)
        return

    await ctx.respond('starting starboard regeneration...', ephemeral=True)
    status_msg = await ctx.channel.send('Regenerating starboard posts...')
    scheduler.add_job(job_regen_starboard(ctx.guild.id, status_msg=status_msg), 'Job', 'fix_starboard_regen')


@fix_starboard.command(name='purge', description='Removes a message from the starboard database given its message link')
@commands.check(is_bot_owner)
@discord.commands.option(name='message_link', required=True, description='Discord message link to purge', input_type=str)
async def fix_starboard_purge(ctx: ApplicationContext, message_link: str):
    from attubot.client.starboard import parse_jump_url

    parsed = parse_jump_url(message_link)
    if parsed is None:
        await ctx.respond('Failed: invalid message link; expected https://discord.com/channels/GUILD/CHANNEL/MESSAGE', ephemeral=True)
        return

    _guild_id, _channel_id, message_id = parsed

    try:
        sb_repo = _get_sb_repo()
    except RuntimeError:
        await ctx.respond('Failed: starboard repo not initialized yet', ephemeral=True)
        return

    doc = await sb_repo.get(message_id)
    if doc is None:
        doc = await sb_repo.get_by_starboard_message(message_id)
    if doc is None:
        await ctx.respond(f'Failed: no starboard entry found for message {message_id}', ephemeral=True)
        return
    message_id = doc.message_id

    # try to delete the discord starboard post if one is linked
    deleted_post = False
    if doc.starboard_message_id:
        try:
            cfg = config.guild(ctx.guild.id)
            sb_channel = bot.get_channel(cfg.starboard.channel_id)
            if sb_channel:
                sb_msg = sb_channel.get_partial_message(doc.starboard_message_id)
                await sb_msg.delete()
                deleted_post = True
        except discord.NotFound:
            pass  # post already gone
        except Exception as err:
            logger.warn(f'fix starboard purge: could not delete starboard post {doc.starboard_message_id}: {err}')

    deleted = await sb_repo.delete(message_id)

    if deleted:
        parts = [f'Purged starboard entry for message {message_id}']
        if deleted_post:
            parts.append('and deleted the starboard post')
        elif doc.starboard_message_id:
            parts.append('(starboard post could not be deleted; may already be gone)')
        await ctx.respond(', '.join(parts))
    else:
        await ctx.respond(f'Failed: no entry deleted; message {message_id} not found', ephemeral=True)


@fix_group.command(name='emoji', description='Upload and verify all custom emojis (eggs + progress bars) on secondary server')
@commands.check(is_bot_owner)
async def fix_emoji(ctx: ApplicationContext):
    await ctx.defer()

    from attubot.eggs.emojis import ensure_egg_emojis, ensure_progress_emojis

    guild = bot.get_guild(config.secondary_server)
    if guild is None:
        await ctx.respond('secondary server not in cache', ephemeral=True)
        return

    egg_emojis, progress_emojis = await asyncio.gather(
        ensure_egg_emojis(guild),
        ensure_progress_emojis(guild),
    )

    config.theme.egg_emojis = {rarity: e.id for rarity, e in egg_emojis.items()}
    config.theme.progress_emojis = {segment: e.id for segment, e in progress_emojis.items()}
    await config.theme.save()

    egg_names = ', '.join(egg_emojis.keys())
    progress_names = ', '.join(progress_emojis.keys())
    await ctx.respond(f'egg emojis: {egg_names} ({len(egg_emojis)} ok)\nprogress emojis: {progress_names} ({len(progress_emojis)} ok)\nall emojis saved.')


@fix_group.command(name='epoch', description='Prints the primary guild epoch config as a TOML block for use in deploy.py')
@commands.check(is_bot_owner)
async def fix_epoch(ctx: ApplicationContext):
    guild = config.primary()
    epoch = guild.epoch
    rollover_h = epoch.rollover_minutes // 60
    rollover_m = epoch.rollover_minutes % 60
    toml = f'[epoch]\ntime = {epoch.time}\nyear = {epoch.year}\nlength = {epoch.length}\npaused = {"true" if epoch.paused else "false"}\nrollover_minutes = {epoch.rollover_minutes}  # {rollover_h:02d}:{rollover_m:02d}\n'
    await ctx.respond(f'```toml\n{toml}```', ephemeral=True)


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(cast(ApplicationCommand, fix_group))
