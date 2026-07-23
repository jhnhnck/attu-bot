# SPDX-License-Identifier: Apache-2.0
"""nova_core.client.events | bot event handlers."""

import asyncio
import contextlib
import signal
import sys
import time

import anyio
import structlog
from discord import ApplicationContext, Member, Message, RawBulkMessageDeleteEvent, RawMessageDeleteEvent, RawMessageUpdateEvent, RawReactionActionEvent, RawReactionClearEmojiEvent, RawReactionClearEvent
from discord.errors import CheckFailure
from discord.ext.commands import MissingPermissions

import attu_logging
from nova_core.client.core import bot, config
from nova_core.client.embeds import ui_emoji
from nova_core.client.util import event_log_context, shift_hue
from nova_core.config import UnauthorizedGuild


logger = structlog.stdlib.get_logger(__name__)

slow_command_threshold_ms = 500
_cmd_start_times: dict[int, float] = {}

_READY_SENTINEL = '/tmp/bot-ready'  # noqa: S108 - intentional healthcheck sentinel path in docker container


# --- Shutdown ---


async def _shutdown(exit_code: int = 1):
    from nova_core.client.core import db
    from nova_core.tasks.scheduler import scheduler

    await scheduler.stop_all()

    if db.client:
        await db.client.close()

    with contextlib.suppress(FileNotFoundError):
        await anyio.Path(_READY_SENTINEL).unlink()

    asyncio.get_running_loop().stop()
    sys.exit(exit_code)


async def _graceful_shutdown():
    """handle SIGTERM from docker; stop tasks, close connections, then close bot cleanly"""
    from nova_core.client.core import db
    from nova_core.tasks.scheduler import scheduler

    logger.info('SIGTERM received; shutting down gracefully')
    asyncio.get_running_loop().remove_signal_handler(signal.SIGTERM)

    await scheduler.stop_all()

    if db.client:
        await db.client.close()

    with contextlib.suppress(FileNotFoundError):
        await anyio.Path(_READY_SENTINEL).unlink()

    await bot.close()


# --- Ready Path ---


async def _restore_wiki_views():
    """restore persistent wiki lookup views from db on startup"""
    try:
        from nova_core.commands.wiki import WikiLookupView, _get_view_repo, build_wiki_embed
        from nova_core.wiki import get_wiki
        from nova_core.wiki.models import PageSummary, SearchResult

        repo = _get_view_repo()
        deleted = await repo.delete_expired()
        if deleted:
            logger.info(f'purged {deleted} expired wiki view documents')

        active = await repo.all_active()
        if active:
            wiki = get_wiki()
            site_info = await wiki.search.site_info()
            for doc in active:
                pages = [SearchResult(title=t, key=k) for t, k in zip(doc.page_titles, doc.page_keys)]
                page = pages[doc.current_index]
                summary = await wiki.pages.get_summary(page.title) or PageSummary(title=page.title, extract='')
                embed, url = build_wiki_embed(summary, site_info)
                view = WikiLookupView(doc.message_id, doc.invoker_user_id, pages, site_info, embed, url, doc.current_index)
                bot.add_view(view, message_id=doc.message_id)
            logger.info(f'restored {len(active)} persistent wiki views')
    except RuntimeError:
        pass  # repo not initialized (should not happen here)
    except Exception as err:
        logger.warning(f'wiki view restore failed: {err}')


async def _do_ready_init():
    """inner ready path; extracted from on_ready() for testability"""
    try:
        logger.info('connecting to database and initializing repositories')
        from nova_core.database import init_database

        await init_database(config.database.url, config.database.name)

        logger.info('loading configuration from database')
        await config.on_load()
        attu_logging.set_webhook_url(config.error_hook)
    except Exception as err:
        logger.critical('exception caught initializing database; exiting', exc_info=True)
        await attu_logging.webhook.send_to_webhook(err)
        await _shutdown(exit_code=1)
        return

    try:
        await config.on_ready()
    except Exception as err:
        logger.critical('exception caught in on_ready() event; exiting', exc_info=True)
        await attu_logging.webhook.send_to_webhook(err)
        await _shutdown(exit_code=1)
        return

    if config.test_mode:
        logger.critical('reached ready state')
        await _shutdown(exit_code=0)
        return

    await _restore_wiki_views()

    # start task scheduler
    try:
        from nova_core.tasks import register_bot_tasks, scheduler

        register_bot_tasks(scheduler)
        await scheduler.start_all()
    except Exception as err:
        logger.critical('exception caught starting task scheduler; exiting', exc_info=True)
        await attu_logging.webhook.send_to_webhook(err)
        await _shutdown(exit_code=1)
        return

    # register SIGTERM handler for graceful container shutdown
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(_graceful_shutdown()))

    # signal healthcheck: bot is fully ready
    try:
        await anyio.Path(_READY_SENTINEL).write_text('ready\n')
    except Exception as err:
        logger.warning(f'could not write ready sentinel: {err}')

    logger.info('pushing commands to discord')
    await bot.sync_commands()


# --- Events ---


@bot.event
async def on_application_command_error(ctx: ApplicationContext, error: Exception):
    logger.error('error sent to on_application_command_error', exc_info=error, command=ctx.command.name)

    if isinstance(error, CheckFailure | UnauthorizedGuild):
        if ctx.guild.id in config.authorized_guilds:
            await ctx.respond("You're not my real dad!")
        else:
            # catch all for if bot gets added to another discord guild
            await ctx.respond('This feature requires DoomBot(tm) Premium')

    elif isinstance(error, MissingPermissions):
        await ctx.respond(f'Nice try! {ui_emoji("rockball")}')

    else:
        if ctx.command.name != 'force_error':
            await ctx.respond(f'An unexpected error occurred! {ui_emoji("rockball_player")}')

        if hasattr(ctx.response, 'jump_url'):
            link = ctx.response.jump_url
        elif hasattr(ctx.channel, 'jump_url'):
            link = ctx.channel.jump_url
        elif hasattr(ctx.guild, 'jump_url'):
            link = ctx.guild.jump_url
        else:
            link = '`fuck idk man`'

        await attu_logging.webhook.send_to_webhook(error, location=f'triggered by `{ctx.user.global_name}` at {link}')


@bot.event
async def on_ready():
    perms = '292595117136'

    if not hasattr(on_ready, 'has_run'):
        on_ready.has_run = False

    if not on_ready.has_run:
        on_ready.has_run = True

        logger.info(f'logged in as {bot.user}')
        logger.info(f'add to a server:\n\thttps://discord.com/oauth2/authorize?client_id={bot.application_id}&scope=bot&permissions={perms}')

        await _do_ready_init()

    else:
        logger.info(f'reconnected as {bot.user}')


@bot.listen()
async def on_message(message: Message):
    with event_log_context(
        event='on_message',
        guild_id=message.guild.id if message.guild is not None else None,
        channel_id=message.channel.id,
        user_id=message.author.id,
    ):
        if message.guild is None:
            logger.debug(f'skipping checks for message from "{message.author.name}" with blank guild')
            return

        if message.guild.id not in config.valid_guilds:
            logger.debug(f'skipping checks for message from "{message.author.name}" in "{message.guild.name}" (invalidated guild)')
            return

        guild_config = config.guild(message.guild.id)

        # store the message unless it's in the logs channel
        if message.channel.id != guild_config.channels.logs:
            from nova_core.client.messages import store_message

            await store_message(message)

        activity_channel = guild_config.channels.activity

        if message.channel.id == activity_channel and message.content.startswith(f'[{config.wiki.user.split("@")[0]}]'):
            if 'blocked' in message.content or 'registered' in message.content:
                await message.add_reaction(ui_emoji('tieteran_wave'))
            else:
                await message.add_reaction('💖')


@bot.listen()
async def on_raw_message_edit(payload: RawMessageUpdateEvent):
    with event_log_context(
        event='on_raw_message_edit',
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
    ):
        if payload.guild_id is None:
            logger.debug('raw_message_edit: dropping; guild_id is None')
            return

        if payload.guild_id not in config.valid_guilds:
            logger.debug(f'raw_message_edit: dropping; guild_id={payload.guild_id} not in valid_guilds')
            return

        # skip edits in the logs channel
        try:
            logs_channel_id = config.guild(payload.guild_id).channels.logs
            if payload.channel_id == logs_channel_id:
                logger.debug('raw_message_edit: dropping; channel is logs channel')
                return
        except Exception as err:
            logger.debug(f'raw_message_edit: dropping; exception resolving logs channel: {err}')
            return

        logger.debug('raw_message_edit: passing to log_edit')
        from nova_core.client.messages import log_edit

        await log_edit(payload)


@bot.listen()
async def on_raw_message_delete(payload: RawMessageDeleteEvent):
    with event_log_context(
        event='on_raw_message_delete',
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
    ):
        if payload.guild_id is None or payload.guild_id not in config.valid_guilds:
            return

        # skip deletions in the logs channel
        try:
            logs_channel_id = config.guild(payload.guild_id).channels.logs
            if payload.channel_id == logs_channel_id:
                return
        except Exception as err:
            logger.debug(f'on_raw_message_delete: failed to get guild config for {payload.guild_id}: {err}')
            return

        from nova_core.client.messages import log_delete

        await log_delete(payload)


@bot.listen()
async def on_raw_bulk_message_delete(payload: RawBulkMessageDeleteEvent):
    with event_log_context(
        event='on_raw_bulk_message_delete',
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
    ):
        if payload.guild_id is None or payload.guild_id not in config.valid_guilds:
            return

        # skip bulk deletions in the logs channel
        try:
            logs_channel_id = config.guild(payload.guild_id).channels.logs
            if payload.channel_id == logs_channel_id:
                return
        except Exception as err:
            logger.debug(f'on_raw_bulk_message_delete: failed to get guild config for {payload.guild_id}: {err}')
            return

        from nova_core.client.messages import log_bulk_delete

        await log_bulk_delete(payload)


@bot.listen()
async def on_member_join(member: Member):
    with event_log_context(event='on_member_join', guild_id=member.guild.id, user_id=member.id):
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
                logger.warning(f'general channel {channel_id} not found in guild {member.guild.id}')
                return
            await channel.send(f'welcome to the archipelago {member.mention}')

        await send_welcome()


@bot.before_invoke
async def on_application_command(ctx: ApplicationContext):
    structlog.contextvars.bind_contextvars(
        command=ctx.command.qualified_name,
        user_id=ctx.user.id,
        guild_id=ctx.guild.id if ctx.guild is not None else None,
        channel_id=ctx.channel.id if ctx.channel is not None else None,
    )
    _cmd_start_times[ctx.interaction.id] = time.perf_counter()
    logger.info(f'command executed: user="{ctx.user.global_name}" command="/{ctx.command}" channel="{ctx.channel.name}" data={ctx.interaction.data}')

    # shift theme hue by 1 degree on every command invocation (save deferred to after_invoke)
    if config.theme is not None:
        config.theme.bot_color = shift_hue(config.theme.bot_color)


@bot.after_invoke
async def on_application_command_complete(ctx: ApplicationContext):
    start = _cmd_start_times.pop(ctx.interaction.id, None)
    if start is not None:
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms >= slow_command_threshold_ms:
            logger.warning(f'slow command: /{ctx.command} took {elapsed_ms:.0f}ms')
        else:
            logger.debug(f'command timing: /{ctx.command} took {elapsed_ms:.0f}ms')

    # persist theme hue after timing so the db write doesn't inflate measured command time
    if config.theme is not None:
        try:
            await config.theme.save()
        except Exception as err:
            logger.warning(f'failed to save theme after hue shift: {err}')

    structlog.contextvars.clear_contextvars()


logger.info('registered event handlers')


def _ccboard_enabled(guild_id: int) -> bool:
    """return True when the ccboard feature flag is set for this guild"""
    try:
        return config.guild(guild_id).ccboard.enabled
    except Exception:
        return False


def _starboard_enabled(guild_id: int) -> bool:
    """return True when the legacy starboard is enabled for this guild; fails open so a
    config error never silently suppresses the starboard"""
    try:
        return config.guild(guild_id).starboard.enabled
    except Exception:
        return True


@bot.listen()
async def on_raw_reaction_add(payload: RawReactionActionEvent):
    with event_log_context(
        event='on_raw_reaction_add',
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        user_id=payload.user_id,
    ):
        logger.debug(f'reaction_add: guild={payload.guild_id} channel={payload.channel_id} msg={payload.message_id} user={payload.user_id} emoji={str(payload.emoji)!r}')
        if payload.guild_id is None or payload.guild_id not in config.valid_guilds:
            logger.debug(f'reaction_add: dropping; guild_id={payload.guild_id} not in valid_guilds={config.valid_guilds}')
            return

        if _starboard_enabled(payload.guild_id):
            from nova_core.client.starboard import handle_star_add

            await handle_star_add(
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
                user_id=payload.user_id,
                emoji_str=str(payload.emoji),
                is_burst=payload.burst,
            )

        if _ccboard_enabled(payload.guild_id):
            from nova_core.ccboard import watcher as ccboard_watcher

            # payload.member is the reactor for raw_reaction_add; if missing or partial,
            # fall back to a guild member lookup so bot-authored reactions are filtered
            is_bot = False
            member = payload.member
            if member is not None:
                is_bot = bool(getattr(member, 'bot', False))
            else:
                try:
                    fetched = await bot.get_or_fetch_member(bot.get_guild(payload.guild_id), payload.user_id)
                    if fetched is not None:
                        is_bot = bool(getattr(fetched, 'bot', False))
                except Exception:
                    # leave is_bot False so a missing member lookup doesn't silently drop reactions
                    is_bot = False

            await ccboard_watcher.handle_reaction_add(
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
                user_id=payload.user_id,
                emoji_str=str(payload.emoji),
                is_burst=payload.burst,
                is_bot=is_bot,
            )


@bot.listen()
async def on_raw_reaction_remove(payload: RawReactionActionEvent):
    with event_log_context(
        event='on_raw_reaction_remove',
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        user_id=payload.user_id,
    ):
        logger.debug(f'reaction_remove: guild={payload.guild_id} channel={payload.channel_id} msg={payload.message_id} user={payload.user_id} emoji={str(payload.emoji)!r}')
        if payload.guild_id is None or payload.guild_id not in config.valid_guilds:
            logger.debug(f'reaction_remove: dropping; guild_id={payload.guild_id} not in valid_guilds={config.valid_guilds}')
            return

        if _starboard_enabled(payload.guild_id):
            from nova_core.client.starboard import handle_star_remove

            await handle_star_remove(
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
                user_id=payload.user_id,
                emoji_str=str(payload.emoji),
                is_burst=payload.burst,
            )

        if _ccboard_enabled(payload.guild_id):
            from nova_core.ccboard import watcher as ccboard_watcher

            await ccboard_watcher.handle_reaction_remove(
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
                user_id=payload.user_id,
                emoji_str=str(payload.emoji),
            )


@bot.listen()
async def on_raw_reaction_clear(payload: RawReactionClearEvent):
    with event_log_context(
        event='on_raw_reaction_clear',
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
    ):
        logger.debug(f'reaction_clear: guild={payload.guild_id} channel={payload.channel_id} msg={payload.message_id}')
        if payload.guild_id is None or payload.guild_id not in config.valid_guilds:
            logger.debug(f'reaction_clear: dropping; guild_id={payload.guild_id} not in valid_guilds={config.valid_guilds}')
            return

        if _starboard_enabled(payload.guild_id):
            from nova_core.client.starboard import handle_star_clear

            await handle_star_clear(
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
            )

        if _ccboard_enabled(payload.guild_id):
            from nova_core.ccboard import watcher as ccboard_watcher

            await ccboard_watcher.handle_reaction_clear(
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
            )


@bot.listen()
async def on_raw_reaction_clear_emoji(payload: RawReactionClearEmojiEvent):
    with event_log_context(
        event='on_raw_reaction_clear_emoji',
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
    ):
        logger.debug(f'reaction_clear_emoji: guild={payload.guild_id} channel={payload.channel_id} msg={payload.message_id} emoji={str(payload.emoji)!r}')
        if payload.guild_id is None or payload.guild_id not in config.valid_guilds:
            logger.debug(f'reaction_clear_emoji: dropping; guild_id={payload.guild_id} not in valid_guilds={config.valid_guilds}')
            return

        if _starboard_enabled(payload.guild_id):
            from nova_core.client.starboard import handle_star_clear_emoji

            await handle_star_clear_emoji(
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
                emoji_str=str(payload.emoji),
            )

        if _ccboard_enabled(payload.guild_id):
            from nova_core.ccboard import watcher as ccboard_watcher

            await ccboard_watcher.handle_reaction_clear_emoji(
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
                emoji_str=str(payload.emoji),
            )
