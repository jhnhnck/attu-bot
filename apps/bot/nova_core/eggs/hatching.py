# SPDX-License-Identifier: Apache-2.0
"""nova_core.eggs.hatching | egg game core logic."""

import asyncio
import random
import time
import uuid

import discord
import structlog

from nova_core.client.core import bot, config
from nova_core.eggs.documents import EggDocument, EggUserDocument
from nova_core.eggs.repositories import EggRepository, EggUserRepository


logger = structlog.stdlib.get_logger(__name__)

# module-level repo singletons; wired by nova_core.eggs.init_repos()
_egg_repo: EggRepository | None = None
_egg_user_repo: EggUserRepository | None = None

# per-user in-memory hatch cooldown tracking (monotonic time)
_hatch_last_used: dict[int, float] = {}

# debounce presence updates triggered by hatch animations (monotonic time)
_last_presence_update: float = 0.0
_PRESENCE_DEBOUNCE_SECONDS: float = 15.0


def _egg_emoji_str(rarity: str) -> str:
    """Return the formatted custom emoji string for a rarity, or the key as fallback."""
    emoji_id = config.theme.egg_emojis.get(rarity)
    if emoji_id:
        return f'<:{rarity}_egg:{emoji_id}>'
    return f':{rarity}_egg:'


async def get_or_create_user_thread(guild_id: int, user_id: int, username: str, user_doc: EggUserDocument | None = None) -> discord.Thread | None:
    """Retrieve the egg thread for a user, creating it if it doesn't exist yet.

    Returns None if the eggs channel is not configured (channels.eggs == 0 or channel not in cache).
    """
    if user_doc is None:
        user_doc = await _egg_user_repo.get(guild_id, user_id)

    if user_doc and user_doc.thread_id:
        thread = bot.get_channel(user_doc.thread_id)
        if thread is not None:
            return thread  # type: ignore[return-value]
        guild = bot.get_guild(guild_id)
        if guild:
            try:
                thread = await guild.fetch_channel(user_doc.thread_id)
                if thread:
                    return thread  # type: ignore[return-value]
            except discord.NotFound:
                pass  # thread was deleted; fall through to recreate

    # create a new thread
    guild_cfg = config.guild(guild_id)
    eggs_channel = bot.get_channel(guild_cfg.channels.eggs)
    if eggs_channel is None:
        logger.warning(f'eggs channel not configured or not in cache for guild {guild_id}')
        return None

    thread = await eggs_channel.create_thread(  # type: ignore[union-attr]
        name=f"{username}'s eggs",
        type=discord.ChannelType.public_thread,
    )
    logger.info(f'created egg thread {thread.id} for user {user_id}')

    if user_doc is None:
        user_doc = EggUserDocument(guild_id=guild_id, user_id=user_id, thread_id=thread.id)
    else:
        user_doc.thread_id = thread.id

    await _egg_user_repo.upsert(user_doc)
    return thread


async def collect_egg(guild_id: int, user_id: int, username: str) -> tuple[str, float | None]:
    """Collect an egg for a user.

    Returns (jump_url, None) on success.
    Returns ('cooldown', ready_at) when the user is still on cooldown (ready_at is a unix timestamp).
    Returns ('no_channel', None) when the eggs channel is not configured.
    """
    cooldown = config.hatch.tuning.collect_cooldown_seconds
    now = int(time.time())

    user_doc = await _egg_user_repo.get(guild_id, user_id)
    if user_doc and user_doc.last_collected_at > 0:
        elapsed = now - user_doc.last_collected_at
        if elapsed < cooldown:
            ready_at = user_doc.last_collected_at + cooldown
            return ('cooldown', ready_at)

    rarity = random.choices(config.hatch.rarities, weights=config.hatch.drop_weights, k=1)[0]
    result = random.choice(config.hatch.pools[rarity])

    # pass user_doc to avoid a second db fetch
    thread = await get_or_create_user_thread(guild_id, user_id, username, user_doc=user_doc)
    if thread is None:
        return ('no_channel', None)
    msg = await thread.send(_egg_emoji_str(rarity))

    egg_id = str(uuid.uuid4())
    egg = EggDocument(
        egg_id=egg_id,
        guild_id=guild_id,
        user_id=user_id,
        rarity=rarity,
        collected_at=now,
        hatches_at=now + config.hatch.hatch_durations[rarity],
        result=result,
        message_id=msg.id,
    )
    if user_doc is None:
        user_doc = EggUserDocument(guild_id=guild_id, user_id=user_id, thread_id=thread.id, last_collected_at=now)
    else:
        user_doc.last_collected_at = now

    # independent operations; run concurrently
    await asyncio.gather(
        _egg_repo.insert(egg),
        _egg_user_repo.upsert(user_doc),
    )

    return (msg.jump_url, None)


async def run_hatch_animation(message: discord.Message | discord.PartialMessage, result: str, rarity: str) -> None:
    """Run the three-stage hatch animation on a thread message."""
    wait_time = random.randint(config.hatch.tuning.animation_wait_min, config.hatch.tuning.animation_wait_max)
    await asyncio.sleep(wait_time)
    await message.edit(content='💢')
    await asyncio.sleep(1)
    await message.edit(content=result)

    # debounced presence update
    global _last_presence_update  # noqa: PLW0603 - module-level debounce timer shared with periodic presence task
    now = time.monotonic()
    if now - _last_presence_update >= _PRESENCE_DEBOUNCE_SECONDS:
        _last_presence_update = now
        from nova_core.tasks.presence import presence_update_task
        from nova_core.tasks.scheduler import scheduler  # local import avoids circular dep

        scheduler.add_job(presence_update_task.run(), 'PresenceUpdate', 'immediate')


async def hatch_egg(guild_id: int, user_id: int) -> tuple[str, float | None]:
    """Hatch the oldest ready egg for a user.

    Returns (jump_url, None) when a hatch was triggered.
    Returns ('cooldown', ready_at) when the user is on hatch cooldown.
    Returns ('', next_hatches_at) when no egg is ready yet.
    Returns ('no_eggs', None) when the user has no eggs at all.
    """
    cooldown = config.hatch.tuning.hatch_cooldown_seconds
    if cooldown > 0:
        now_mono = time.monotonic()
        last = _hatch_last_used.get(user_id, 0.0)
        if now_mono - last < cooldown:
            ready_at = time.time() + (cooldown - (now_mono - last))
            return ('cooldown', ready_at)

    egg = await _egg_repo.get_oldest_ready(guild_id, user_id)
    if egg is None:
        next_egg = await _egg_repo.get_next_unhatched(guild_id, user_id)
        if next_egg is None:
            return ('no_eggs', None)
        return ('', next_egg.hatches_at)

    user_doc = await _egg_user_repo.get(guild_id, user_id)
    if user_doc is None or not user_doc.thread_id:
        raise RuntimeError('no egg thread found for user')

    thread = bot.get_channel(user_doc.thread_id)
    if thread is None:
        guild = bot.get_guild(guild_id)
        if guild is None:
            raise RuntimeError(f'guild {guild_id} not in cache')
        thread = await guild.fetch_channel(user_doc.thread_id)

    if egg.message_id is None:
        raise RuntimeError(f'egg {egg.egg_id} has no message_id stored')
    msg = thread.get_partial_message(egg.message_id)  # type: ignore[union-attr]
    jump_url = msg.jump_url

    if egg.result is None:
        raise RuntimeError(f'egg {egg.egg_id} has no result set')

    # mark hatched before animation so a restart won't double-hatch
    await _egg_repo.mark_hatched(egg.egg_id, egg.result)

    # run animation in background; caller responds to discord first
    from nova_core.tasks import scheduler

    scheduler.add_job(run_hatch_animation(msg, egg.result, egg.rarity), 'HatchAnimation', egg.egg_id)

    _hatch_last_used[user_id] = time.monotonic()
    return (jump_url, None)


async def transfer_egg(guild_id: int, egg_id: str, from_user_id: int, to_user_id: int, to_username: str) -> str:
    """Transfer an egg from one user to another. Returns the jump_url of the new message.

    Deletes the original thread message and reposts the egg in the recipient's thread.
    Raises ValueError if the egg is not found or not owned by from_user_id.
    """
    egg = await _egg_repo.get(egg_id)
    if egg is None or egg.user_id != from_user_id or egg.guild_id != guild_id:
        raise ValueError('egg not found')

    from_user_doc = await _egg_user_repo.get(guild_id, from_user_id)
    if from_user_doc and from_user_doc.thread_id and egg.message_id:
        thread = bot.get_channel(from_user_doc.thread_id)
        if thread is None:
            guild = bot.get_guild(guild_id)
            if guild:
                try:
                    thread = await guild.fetch_channel(from_user_doc.thread_id)
                except discord.NotFound:
                    thread = None
        if thread is not None:
            try:
                old_msg = thread.get_partial_message(egg.message_id)  # type: ignore[union-attr]
                await old_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass  # already gone or no permission; proceed with transfer

    to_thread = await get_or_create_user_thread(guild_id, to_user_id, to_username)
    if to_thread is None:
        raise ValueError('eggs channel not configured')
    content = egg.result if egg.hatched else _egg_emoji_str(egg.rarity)
    new_msg = await to_thread.send(content)

    await _egg_repo.transfer(egg_id, to_user_id, new_msg.id)
    logger.info(f'transferred egg {egg_id} from {from_user_id} to {to_user_id}')
    return new_msg.jump_url
