# SPDX-License-Identifier: Apache-2.0
"""nova_core.ccboard.manager | settled-entry sync task for the ccboard."""

import time
from datetime import timedelta

import discord
import structlog

from nova_core.ccboard.builder import build_embeds
from nova_core.ccboard.documents import BoardEntryDocument
from nova_core.ccboard.repositories import EntryRepository
from nova_core.client.core import config
from nova_core.client.util import format_message_link, theme_color
from nova_core.config import GuildCCBoard, UnauthorizedGuild
from nova_core.tasks.base import BaseTask


logger = structlog.stdlib.get_logger(__name__)


# --- constants ---


# debounce window in seconds before a dirty entry is considered settled
_SETTLE_SECONDS = 60

# max entries processed per tick to avoid discord rate-limit spikes
_BATCH_LIMIT = 50

# streak counts that trigger a sweep announcement
_SWEEP_COUNTS = (3, 5, 11)

# how many recent entries to inspect when computing the credited-author streak
_STREAK_WINDOW = 12


# --- helpers ---


def _get_entry_repo() -> EntryRepository:
    """fetch the entry repo singleton wired by database init."""
    from nova_core import ccboard

    if ccboard._entry_repo is None:
        raise RuntimeError('ccboard entry repo not initialized')
    return ccboard._entry_repo


def _credited_author_id(entry: BoardEntryDocument) -> int:
    return entry.effective_author_id or entry.author_id


def _lowest_positive_emoji(cfg: GuildCCBoard) -> str | None:
    """return the configured emoji with the smallest positive point value, or None."""
    positives = [(emoji, pts) for emoji, pts in cfg.emojis.items() if pts > 0]
    if not positives:
        return None
    return min(positives, key=lambda kv: kv[1])[0]


def _sweep_message(streak: int, user_id: int) -> str | None:
    """return the sweep announcement description for the given streak, or None."""
    mention = f'<@{user_id}>'
    if streak == 3:
        return f'**{mention} sweaps!**'
    if streak == 5:
        return f'**{mention} sweaps more!**'
    if streak == 11:
        return f'**{mention} sweaps even more!**'
    return None


# --- task ---


class ManagerTask(BaseTask):
    """periodically sync settled ccboard entries to discord posts.

    the watcher writes is_dirty=True on every reaction event; this task picks up entries
    whose last_reaction_at is at least 60s old, syncs the discord post (create / edit /
    delete), and clears is_dirty. processing one entry per acquired lock keeps the
    watcher's reaction handler and migration commands serialized on the same key.
    """

    name: str = 'CCBoardManager'
    interval: timedelta | None = timedelta(seconds=10)
    run_immediately: bool = False

    async def on_start(self) -> None:
        await config.wait_for_ready()

    async def run(self) -> None:
        from nova_core import ccboard

        entry_repo = _get_entry_repo()
        now = int(time.time())

        for guild_id in list(config.authorized_guilds):
            try:
                guild_cfg = config.guild(guild_id)
            except UnauthorizedGuild:
                continue
            cc_cfg = guild_cfg.ccboard
            if not cc_cfg.enabled:
                continue

            try:
                settled = await entry_repo.find_settled(guild_id, now=now, debounce_seconds=_SETTLE_SECONDS, limit=_BATCH_LIMIT)
            except Exception as err:
                logger.exception(f'ccboard manager: find_settled failed for guild {guild_id}')
                continue

            for entry in settled:
                lock = ccboard.get_lock(entry.message_id)
                async with lock:
                    try:
                        await self._sync_post(entry, cc_cfg)
                    except Exception as err:
                        # leave is_dirty=True so the next tick retries; log and move on
                        logger.exception(f'ccboard manager: sync failed for message {entry.message_id}')
                        continue
                    try:
                        await entry_repo.mark_synced(entry.message_id, now=now)
                    except Exception as err:
                        logger.exception(f'ccboard manager: mark_synced failed for message {entry.message_id}')

    async def _sync_post(self, entry: BoardEntryDocument, cfg: GuildCCBoard) -> None:  # noqa: PLR0911, PLR0912, PLR0915 - branchy create/update/delete/replace logic with multiple discord error cases
        """create / edit / delete the discord post for one settled entry."""
        from nova_core.client.core import bot

        entry_repo = _get_entry_repo()
        jump_url = format_message_link(entry.guild_id, entry.channel_id, entry.message_id)
        content = f'{entry.net_points} {cfg.points_label} | {jump_url}'

        # below threshold: delete any existing post and clear the reference
        if entry.positive_points < cfg.threshold:
            if entry.starboard_message_id is None:
                return
            channel = bot.get_channel(cfg.channel_id)
            if channel is None:
                try:
                    channel = await bot.fetch_channel(cfg.channel_id)
                except Exception as err:
                    logger.warning(f'ccboard manager: channel {cfg.channel_id} unavailable: {err}')
                    return
            try:
                old = channel.get_partial_message(entry.starboard_message_id)
                await old.delete()
                logger.info(f'ccboard manager: deleted post {entry.starboard_message_id} for message {entry.message_id}; below threshold')
            except discord.NotFound:
                logger.debug(f'ccboard manager: post {entry.starboard_message_id} already gone')
            except Exception as err:
                logger.warning(f'ccboard manager: could not delete post {entry.starboard_message_id}: {err}')
            await entry_repo.set_starboard_message(entry.message_id, None)
            return

        # at/above threshold: ensure the channel is reachable
        channel = bot.get_channel(cfg.channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(cfg.channel_id)
            except Exception as err:
                logger.warning(f'ccboard manager: channel {cfg.channel_id} unavailable: {err}')
                return

        embeds = build_embeds(entry, cfg)

        # no post yet: create one and announce sweeps on success
        if entry.starboard_message_id is None:
            await self._create_post(entry, cfg, channel, content, embeds)
            return

        # post exists: edit in place, falling back to recreate / reply on errors
        try:
            existing = channel.get_partial_message(entry.starboard_message_id)
            await existing.edit(content=content, embeds=embeds)
            logger.debug(f'ccboard manager: updated post {entry.starboard_message_id} for message {entry.message_id}')
            return
        except discord.NotFound:
            # post was deleted externally; clear the reference and fall through to recreate
            logger.warning(f'ccboard manager: post {entry.starboard_message_id} not found, recreating')
            await entry_repo.set_starboard_message(entry.message_id, None)
            entry.starboard_message_id = None
            await self._create_post(entry, cfg, channel, content, embeds)
            return
        except discord.Forbidden:
            # uneditable post (legacy bot's message); reply once to keep a jump path
            if entry.reply_created:
                logger.debug(f'ccboard manager: skipping repeat reply for uneditable post {entry.starboard_message_id}')
                return
            logger.warning(f'ccboard manager: cannot edit post {entry.starboard_message_id}, sending reply')
            try:
                try:
                    old = channel.get_partial_message(entry.starboard_message_id)
                    new_msg = await channel.send(content=content, embeds=embeds, reference=old)
                except discord.NotFound:
                    new_msg = await channel.send(content=content, embeds=embeds)
                await entry_repo.set_starboard_message(entry.message_id, new_msg.id)
                await entry_repo.set_reply_created(entry.message_id)
                emoji = _lowest_positive_emoji(cfg)
                if emoji is not None:
                    try:
                        await new_msg.add_reaction(emoji)
                    except Exception as react_err:
                        logger.warning(f'ccboard manager: failed to add reaction {emoji} to replacement post: {react_err}')
                logger.info(f'ccboard manager: replaced uneditable post {entry.starboard_message_id} with {new_msg.id} for message {entry.message_id}')
            except Exception as err:
                logger.exception(f'ccboard manager: failed to send replacement for post {entry.starboard_message_id}')
        except Exception as err:
            logger.exception(f'ccboard manager: failed to update post {entry.starboard_message_id}')

    async def _create_post(
        self,
        entry: BoardEntryDocument,
        cfg: GuildCCBoard,
        channel,
        content: str,
        embeds: list[discord.Embed],
    ) -> None:
        """send a new ccboard post, persist the id, react, and announce sweeps.

        if the db write fails after the discord send succeeded, delete the orphan post and
        re-raise so the next tick retries cleanly.
        """
        entry_repo = _get_entry_repo()
        new_msg = await channel.send(content=content, embeds=embeds, allowed_mentions=discord.AllowedMentions.none())
        try:
            await entry_repo.set_starboard_message(entry.message_id, new_msg.id)
        except Exception as err:
            # discord post created but db write failed; delete the orphan so the next tick
            # can retry without leaving a duplicate
            logger.exception(f'ccboard manager: failed to record post {new_msg.id} for message {entry.message_id}; deleting orphan')
            try:
                await new_msg.delete()
            except Exception as del_err:
                logger.exception(f'ccboard manager: failed to delete orphan post {new_msg.id}; manual cleanup may be needed')
            raise

        emoji = _lowest_positive_emoji(cfg)
        if emoji is not None:
            try:
                await new_msg.add_reaction(emoji)
            except Exception as err:
                logger.warning(f'ccboard manager: failed to add reaction {emoji} to post {new_msg.id}: {err}')

        logger.info(f'ccboard manager: created post {new_msg.id} for message {entry.message_id} ({entry.positive_points} positive)')
        await self._announce_sweep(entry, cfg, channel)

    async def _announce_sweep(self, entry: BoardEntryDocument, cfg: GuildCCBoard, channel) -> None:
        """check for a sweep milestone and announce it; never blocks post creation."""
        try:
            entry_repo = _get_entry_repo()
            credited = _credited_author_id(entry)
            recent = await entry_repo.recent_authors(entry.guild_id, limit=_STREAK_WINDOW)
            streak = 0
            for author in recent:
                if author != credited:
                    break
                streak += 1
            if streak not in _SWEEP_COUNTS:
                return
            description = _sweep_message(streak, credited)
            if description is None:
                return
            embed = discord.Embed(color=theme_color(), description=description)
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            logger.info(f'ccboard manager: sweep announced for author {credited} streak {streak}')
        except Exception as err:
            logger.exception('ccboard manager: sweep announcement failed')


# singleton instance for registration
manager_task = ManagerTask()


logger.info('registered: ccboard manager')
