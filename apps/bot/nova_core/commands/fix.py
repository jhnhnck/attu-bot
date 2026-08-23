# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.fix | fix commands."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast

import discord
import structlog
from discord import ApplicationCommand, ApplicationContext, Bot, Permissions, SlashCommandGroup
from discord.ext import commands

from nova_core.client import messages
from nova_core.client.core import bot, config
from nova_core.client.util import is_bot_owner
from nova_core.starboard.handlers import _get_repo as _get_sb_repo
from nova_core.starboard.handlers import _sync_starboard_post
from nova_core.tasks import LogoUpdateTask, scheduler
from nova_core.tasks.message_backfill import MessageBackfillTask
from nova_core.tasks.nova_year import job_construct_year_links


logger = structlog.stdlib.get_logger(__name__)


async def _safe_edit(status_msg: discord.Message | None, content: str) -> discord.Message | None:
    """edit the status message safely; returns None if the edit fails so callers can stop retrying."""
    if status_msg is None:
        return None
    try:
        await status_msg.edit(content=content)
        return status_msg
    except discord.HTTPException as err:
        logger.warning(f'fix: status message edit failed ({err}), further updates disabled')
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
    from nova_core.client.core import bot

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
            logger.warning(f'fix messages: recent reconcile failed for {channel_id}: {err}')

    summary = f'Done! Backfilled {backfilled:,} messages in <#{channel_id}>'
    if reconcile_recent:
        summary += f', reconciled {reconciled:,} recent entries'

    await _safe_edit(status_msg, summary)

    return backfilled or 0, reconciled or 0


async def job_fix_author_names(guild_id: int, status_msg: discord.Message | None = None, user_id: int | None = None):
    """resolve current global usernames and bulk-update author_name on all stored messages."""
    from nova_core.client.core import bot
    from nova_core.client.messages import _global_username

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
                logger.warning(f'fix author_names: could not resolve user {author_id}: user not found')
                continue
            name = _global_username(user)
            count = await repo.update_author_name(author_id, name)
            updated_msgs += count
            resolved += 1
        except Exception as err:
            not_found += 1
            logger.warning(f'fix author_names: could not resolve user {author_id}: {err}')

        if (i + 1) % 50 == 0:
            status_msg = await _safe_edit(status_msg, f'Progress: {i + 1}/{len(author_ids)} users processed...')

    summary = f'Done - {resolved} users resolved, {updated_msgs:,} messages updated'
    if not_found:
        summary += f', {not_found} users not found'

    logger.info(f'fix author_names: {summary} (guild {guild_id})')

    await _safe_edit(status_msg, summary)


fix_group = SlashCommandGroup('fix', default_member_permissions=Permissions.all(), description='Commands to repair or rebuild bot state')
fix_starboard = fix_group.create_subgroup('starboard', 'Commands to repair starboard state')
fix_stars = fix_group.create_subgroup('stars', 'One-shot migration helpers from starboard to ccboard')
fix_ccboard = fix_group.create_subgroup('ccboard', 'Commands to repair ccboard state')


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
    from nova_core.client.core import bot, config
    from nova_core.database.models import StarredMessageDocument
    from nova_core.starboard.handlers import _get_repo as _get_sb_repo

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
                logger.warning(f'recount_starboard: failed to fetch original message {doc.message_id}: {err}')
                errors += 1
                continue

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
                    logger.warning(f'recount_starboard: failed to fetch starboard post {doc.starboard_message_id}: {err}')

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
            logger.warning(f'recount_starboard: unexpected error for message {doc.message_id}: {err}')
            errors += 1
        finally:
            # runs on every iteration including those that hit `continue`
            if (i + 1) % 25 == 0:
                status_msg = await _safe_edit(status_msg, f'Progress: {i + 1}/{len(all_docs)} messages recounted...')

    summary = f'Done - {updated} updated, {skipped} skipped, {errors} errors'
    logger.info(f'recount_starboard: {summary} (guild {guild_id})')

    await _safe_edit(status_msg, summary)


async def job_regen_starboard(guild_id: int, status_msg: discord.Message | None = None):
    from nova_core.client.core import config
    from nova_core.starboard.handlers import _sync_starboard_post

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
            logger.warning(f'regen_starboard: failed for message {doc.message_id}: {err}')
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

    from nova_core.client.core import bot, config
    from nova_core.database.models import StarredMessageDocument
    from nova_core.starboard.handlers import _get_repo as _get_sb_repo_inner
    from nova_core.starboard.handlers import _sync_starboard_post as _sync_post
    from nova_core.starboard.handlers import parse_jump_url

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
                    await sb_repo.set_starboard_message(doc.message_id, sb_msg.id)
                    updated = await sb_repo.get(doc.message_id)
                    if updated:
                        await _sync_post(guild_id, updated, guild_config)
                    link_fixed += 1
                    logger.info(f'recover_starboard: fixed link for message {orig_message_id} -> post {sb_msg.id}')
                    continue

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
                logger.warning(f'recover_starboard: could not access original message {orig_message_id}')
            except Exception as err:
                errors += 1
                logger.warning(f'recover_starboard: error processing starboard post {sb_msg.id}: {err}')

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
        from nova_core.starboard.handlers import _get_repo

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
    from nova_core.starboard.handlers import parse_jump_url

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
            logger.warning(f'fix starboard purge: could not delete starboard post {doc.starboard_message_id}: {err}')

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


@fix_stars.command(name='convert', description='One-shot migration from the legacy starboard collection to ccboard_reactions and ccboard_entries')
@commands.check(is_bot_owner)
@discord.commands.option(name='confirm', required=True, description='Set true to actually run the migration; false will refuse', input_type=bool)
async def fix_stars_convert(ctx: ApplicationContext, confirm: bool):
    if not confirm:
        await ctx.respond('Failed: pass confirm=True to run the migration; this is a one-shot data copy', ephemeral=True)
        return

    cfg = config.guild(ctx.guild.id).ccboard
    if not cfg.emojis:
        await ctx.respond('Failed: ccboard.emojis is empty; configure emoji weights before running the migration', ephemeral=True)
        return

    try:
        _get_sb_repo()
    except RuntimeError:
        await ctx.respond('Failed: starboard repo not initialized yet', ephemeral=True)
        return

    from nova_core.ccboard.migration import job_convert_starboard_to_ccboard

    await ctx.respond('starting starboard → ccboard migration; this may take a while...', ephemeral=True)
    status_msg = await ctx.channel.send('Starting starboard → ccboard migration...')
    scheduler.add_job(job_convert_starboard_to_ccboard(ctx.guild.id, status_msg=status_msg), 'Job', 'fix_stars_convert')


@fix_ccboard.command(name='regen', description='Marks every ccboard entry in this guild as dirty so the manager rebuilds all posts on the next tick')
@commands.check(is_bot_owner)
async def fix_ccboard_regen(ctx: ApplicationContext):
    from nova_core import ccboard

    if ccboard._entry_repo is None:
        await ctx.respond('Failed: ccboard entry repo not initialized yet', ephemeral=True)
        return

    affected = await ccboard._entry_repo.mark_all_dirty(ctx.guild.id)
    await ctx.respond(f'Marked {affected:,} ccboard entries dirty; manager will rebuild on the next tick')


@fix_ccboard.command(name='purge', description='Removes a message from the ccboard database given its message link')
@commands.check(is_bot_owner)
@discord.commands.option(name='message_link', required=True, description='Discord message link to purge', input_type=str)
async def fix_ccboard_purge(ctx: ApplicationContext, message_link: str):
    from nova_core import ccboard
    from nova_core.starboard.handlers import parse_jump_url

    parsed = parse_jump_url(message_link)
    if parsed is None:
        await ctx.respond('Failed: invalid message link; expected https://discord.com/channels/GUILD/CHANNEL/MESSAGE', ephemeral=True)
        return
    _g, _c, target_id = parsed

    if ccboard._entry_repo is None or ccboard._reaction_repo is None:
        await ctx.respond('Failed: ccboard repos not initialized yet', ephemeral=True)
        return

    # accept either the original message link or the ccboard post link
    entry = await ccboard._entry_repo.get(target_id)
    if entry is None:
        entry = await ccboard._entry_repo.get_by_starboard_message(target_id)
    if entry is None:
        entry = await ccboard._entry_repo.get_by_display_message(target_id)
    if entry is None:
        await ctx.respond(f'Failed: no ccboard entry found for message {target_id}', ephemeral=True)
        return

    deleted_post = False
    if entry.starboard_message_id:
        try:
            cfg = config.guild(ctx.guild.id)
            cc_channel = bot.get_channel(cfg.ccboard.channel_id)
            if cc_channel:
                cc_msg = cc_channel.get_partial_message(entry.starboard_message_id)
                await cc_msg.delete()
                deleted_post = True
        except discord.NotFound:
            pass
        except Exception as err:
            logger.warning(f'fix ccboard purge: could not delete ccboard post {entry.starboard_message_id}: {err}')

    now = int(__import__('time').time())
    await ccboard._reaction_repo.soft_delete_all_for_message(entry.message_id, now=now)
    await ccboard._entry_repo.delete(entry.message_id)

    parts = [f'Purged ccboard entry for message {entry.message_id}']
    if deleted_post:
        parts.append('and deleted the ccboard post')
    elif entry.starboard_message_id:
        parts.append('(ccboard post could not be deleted; may already be gone)')
    await ctx.respond(', '.join(parts))


@fix_ccboard.command(name='recover', description='Auditor discovery pass — scans recently-active channels for missed reactions')
@commands.check(is_bot_owner)
async def fix_ccboard_recover(ctx: ApplicationContext):
    from nova_core.ccboard.auditor import auditor_task

    result = await auditor_task.discover_guild(ctx.guild.id, dry_run=True)
    await ctx.respond(f'auditor.discover_guild: {result.summary}', ephemeral=True)


@fix_ccboard.command(name='cleanup', description='Scan ccboard channel for orphan posts (no DB entry); confirm=True to delete')
@commands.check(is_bot_owner)
@discord.commands.option(name='confirm', required=False, default=False, description='Apply deletions; default is dry-run (list only)', input_type=bool)
async def fix_ccboard_cleanup(ctx: ApplicationContext, confirm: bool = False):
    from nova_core.ccboard.auditor import auditor_task

    result = await auditor_task.cleanup_orphans(ctx.guild.id, dry_run=not confirm)
    verdict = 'APPLIED' if result.mutated else ('dry-run' if result.dry_run else 'no change')
    await ctx.respond(f'auditor.cleanup_orphans [{verdict}]: {result.summary}', ephemeral=True)


@fix_ccboard.command(name='recount', description='reconcile and recount ccboard reactions; guild-wide if no link, per-entry if link given')
@commands.check(is_bot_owner)
@discord.commands.option(name='message_link', required=False, default=None, description='Discord message link to reconcile; omit for guild-wide reconcile', input_type=str)
@discord.commands.option(name='confirm', required=False, default=False, description='When true, applies the diff; default is dry-run', input_type=bool)
async def fix_ccboard_recount(ctx: ApplicationContext, message_link: str | None = None, confirm: bool = False):
    from nova_core.ccboard.auditor import auditor_task
    from nova_core.starboard.handlers import parse_jump_url

    if message_link is None:
        result = await auditor_task.reconcile_guild(ctx.guild.id, dry_run=not confirm)
        await ctx.respond(f'auditor.reconcile_guild: {result.summary}', ephemeral=True)
        return

    parsed = parse_jump_url(message_link.strip())
    if parsed is None:
        await ctx.respond('Failed: invalid message link; paste the full discord message link', ephemeral=True)
        return
    link_guild_id, _channel_id, target_message_id = parsed
    if link_guild_id != ctx.guild.id:
        await ctx.respond('Failed: that message link is from a different server', ephemeral=True)
        return

    await ctx.defer(ephemeral=True)
    result = await auditor_task.reconcile_entry(ctx.guild.id, target_message_id, dry_run=not confirm)
    verdict = 'APPLIED' if result.mutated else ('dry-run' if result.dry_run else 'no change')
    await ctx.respond(f'auditor.reconcile_entry [{verdict}]: {result.summary}', ephemeral=True)


@fix_group.command(name='emoji', description='Upload and verify all custom emojis (eggs + progress bars) on secondary server')
@commands.check(is_bot_owner)
async def fix_emoji(ctx: ApplicationContext):
    await ctx.defer()

    from nova_core.eggs.emojis import ensure_egg_emojis, ensure_progress_emojis

    secondary = config.get_guild_by_role('secondary')
    guild = bot.get_guild(secondary.id) if secondary is not None else None
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
