"""
AttuBot - Moderation Log Handlers
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import discord
from discord import Color, Embed, Guild, GuildEmoji, Member, Role, User

from attubot import bot, config
from attubot.logging import get_logger

logger = get_logger(__name__)


def _theme_color() -> int:
    if config.theme:
        return int(config.theme.bot_color.lstrip('#'), 16)
    return Color.blurple().value


async def _get_logs_channel(guild_id: int) -> discord.TextChannel | None:
    try:
        gc = config.guild(guild_id)
    except Exception:
        return None
    channel_id = gc.channels.logs
    if channel_id == 0:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None
    return guild.get_channel(channel_id)  # type: ignore[return-value]


async def _send_embed(guild_id: int, embed: Embed) -> None:
    channel = await _get_logs_channel(guild_id)
    if channel is None:
        return
    try:
        await channel.send(embed=embed)
    except Exception as err:
        logger.error(f'failed to send modlog embed for guild {guild_id}: {err}')


def _role_mentions(roles: list[Role]) -> str:
    filtered = [role for role in roles if not role.is_default()]
    if not filtered:
        return '*(none)*'
    filtered.sort(key=lambda role: role.position, reverse=True)
    return ', '.join(role.mention for role in filtered)


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return '*(none)*'
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return f'<t:{int(value.timestamp())}:f>'


def _member_display_name(member: Member | User) -> str:
    return member.global_name or member.name


async def _is_bot_audit_action(guild: Guild, action: discord.AuditLogAction, target_id: int) -> bool:
    try:
        async for entry in guild.audit_logs(limit=5, action=action):
            target = getattr(entry, 'target', None)
            entry_target_id = getattr(target, 'id', None)
            if entry_target_id != target_id:
                continue
            user = getattr(entry, 'user', None)
            return bool(user and getattr(user, 'bot', False))
    except Exception as err:
        logger.debug(f'failed to resolve audit log for {guild.id} action={action} target={target_id}: {err}')
    return False


def _build_member_join_embed(member: Member) -> Embed:
    created_at = member.created_at.replace(tzinfo=UTC) if member.created_at.tzinfo is None else member.created_at
    now = datetime.now(tz=UTC)
    age_days = (now - created_at).days
    age_str = f'{age_days // 365}y {age_days % 365}d' if age_days >= 365 else f'{age_days}d'

    embed = Embed(title='Member Joined', color=_theme_color())
    embed.add_field(name='Mention', value=member.mention, inline=True)
    embed.add_field(name='Username', value=member.name, inline=True)
    embed.add_field(name='Account Created', value=_format_dt(created_at), inline=False)
    embed.add_field(name='Account Age', value=age_str, inline=True)

    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)

    embed.set_footer(text=f'user id: {member.id}')
    embed.timestamp = datetime.now(tz=UTC)
    return embed


def _build_member_leave_embed(member: Member) -> Embed:
    embed = Embed(title='Member Left', color=Color.red().value)
    embed.add_field(name='Mention', value=member.mention, inline=True)
    embed.add_field(name='Username', value=member.name, inline=True)
    embed.add_field(name='Joined', value=_format_dt(member.joined_at), inline=True)
    embed.add_field(name='Roles', value=_role_mentions(list(member.roles)), inline=False)
    embed.set_footer(text=f'user id: {member.id}')
    embed.timestamp = datetime.now(tz=UTC)
    return embed


@bot.listen()
async def on_member_join(member: Member):
    if member.guild.id not in config.valid_guilds or member.bot:
        return
    embed = _build_member_join_embed(member)
    await _send_embed(member.guild.id, embed)


@bot.listen()
async def on_member_remove(member: Member):
    if member.guild.id not in config.valid_guilds or member.bot:
        return
    embed = _build_member_leave_embed(member)
    await _send_embed(member.guild.id, embed)


@bot.listen()
async def on_member_ban(guild: Guild, user: User | Member):
    if guild.id not in config.valid_guilds or user.bot:
        return
    embed = Embed(title='Member Banned', color=Color.red().value)
    embed.add_field(name='User', value=f'{user.mention} ({_member_display_name(user)})', inline=False)
    embed.set_footer(text=f'user id: {user.id}')
    embed.timestamp = datetime.now(tz=UTC)
    await _send_embed(guild.id, embed)


@bot.listen()
async def on_member_unban(guild: Guild, user: User):
    if guild.id not in config.valid_guilds or user.bot:
        return
    embed = Embed(title='Member Unbanned', color=_theme_color())
    embed.add_field(name='User', value=f'{user.mention} ({_member_display_name(user)})', inline=False)
    embed.set_footer(text=f'user id: {user.id}')
    embed.timestamp = datetime.now(tz=UTC)
    await _send_embed(guild.id, embed)


@bot.listen()
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    if channel.guild.id not in config.valid_guilds:
        return
    if await _is_bot_audit_action(channel.guild, discord.AuditLogAction.channel_create, channel.id):
        return
    embed = Embed(title='Channel Created', color=_theme_color())
    embed.add_field(name='Channel', value=channel.mention, inline=True)
    embed.add_field(name='Type', value=str(channel.type), inline=True)
    if channel.category:
        embed.add_field(name='Category', value=channel.category.name, inline=True)
    embed.set_footer(text=f'channel id: {channel.id}')
    embed.timestamp = datetime.now(tz=UTC)
    await _send_embed(channel.guild.id, embed)


@bot.listen()
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    if channel.guild.id not in config.valid_guilds:
        return
    if await _is_bot_audit_action(channel.guild, discord.AuditLogAction.channel_delete, channel.id):
        return
    embed = Embed(title='Channel Deleted', color=Color.red().value)
    embed.add_field(name='Channel', value=channel.name, inline=True)
    embed.add_field(name='Type', value=str(channel.type), inline=True)
    if channel.category:
        embed.add_field(name='Category', value=channel.category.name, inline=True)
    embed.set_footer(text=f'channel id: {channel.id}')
    embed.timestamp = datetime.now(tz=UTC)
    await _send_embed(channel.guild.id, embed)


@bot.listen()
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
    if after.guild.id not in config.valid_guilds:
        return
    if await _is_bot_audit_action(after.guild, discord.AuditLogAction.channel_update, after.id):
        return

    changes: list[tuple[str, str, str]] = []
    if before.name != after.name:
        changes.append(('Name', before.name, after.name))
    if getattr(before, 'topic', None) != getattr(after, 'topic', None):
        changes.append(('Topic', getattr(before, 'topic', None) or '*(none)*', getattr(after, 'topic', None) or '*(none)*'))
    if getattr(before, 'category_id', None) != getattr(after, 'category_id', None):
        before_cat = before.category.name if before.category else '*(none)*'
        after_cat = after.category.name if after.category else '*(none)*'
        changes.append(('Category', before_cat, after_cat))
    if getattr(before, 'slowmode_delay', None) != getattr(after, 'slowmode_delay', None):
        changes.append(('Slowmode', str(getattr(before, 'slowmode_delay', 0)), str(getattr(after, 'slowmode_delay', 0))))
    if getattr(before, 'nsfw', None) != getattr(after, 'nsfw', None):
        changes.append(('NSFW', str(getattr(before, 'nsfw', False)), str(getattr(after, 'nsfw', False))))

    if not changes:
        return

    embed = Embed(title='Channel Updated', color=_theme_color())
    embed.add_field(name='Channel', value=after.mention, inline=False)
    for label, old, new in changes:
        embed.add_field(name=label, value=f'{old} -> {new}', inline=False)
    embed.set_footer(text=f'channel id: {after.id}')
    embed.timestamp = datetime.now(tz=UTC)
    await _send_embed(after.guild.id, embed)


@bot.listen()
async def on_guild_role_create(role: Role):
    if role.guild.id not in config.valid_guilds:
        return
    if await _is_bot_audit_action(role.guild, discord.AuditLogAction.role_create, role.id):
        return
    embed = Embed(title='Role Created', color=_theme_color())
    embed.add_field(name='Role', value=role.mention, inline=True)
    embed.add_field(name='Color', value=str(role.color), inline=True)
    embed.set_footer(text=f'role id: {role.id}')
    embed.timestamp = datetime.now(tz=UTC)
    await _send_embed(role.guild.id, embed)


@bot.listen()
async def on_guild_role_delete(role: Role):
    if role.guild.id not in config.valid_guilds:
        return
    if await _is_bot_audit_action(role.guild, discord.AuditLogAction.role_delete, role.id):
        return
    embed = Embed(title='Role Deleted', color=Color.red().value)
    embed.add_field(name='Role', value=role.name, inline=True)
    embed.add_field(name='Color', value=str(role.color), inline=True)
    embed.set_footer(text=f'role id: {role.id}')
    embed.timestamp = datetime.now(tz=UTC)
    await _send_embed(role.guild.id, embed)


@bot.listen()
async def on_guild_role_update(before: Role, after: Role):
    if after.guild.id not in config.valid_guilds:
        return
    if await _is_bot_audit_action(after.guild, discord.AuditLogAction.role_update, after.id):
        return

    changes: list[tuple[str, str, str]] = []
    if before.name != after.name:
        changes.append(('Name', before.name, after.name))
    if before.color != after.color:
        changes.append(('Color', str(before.color), str(after.color)))
    if before.hoist != after.hoist:
        changes.append(('Hoist', str(before.hoist), str(after.hoist)))
    if before.mentionable != after.mentionable:
        changes.append(('Mentionable', str(before.mentionable), str(after.mentionable)))
    if before.permissions.value != after.permissions.value:
        changes.append(('Permissions', str(before.permissions.value), str(after.permissions.value)))

    if not changes:
        return

    embed = Embed(title='Role Updated', color=_theme_color())
    embed.add_field(name='Role', value=after.mention, inline=False)
    for label, old, new in changes:
        embed.add_field(name=label, value=f'{old} -> {new}', inline=False)
    embed.set_footer(text=f'role id: {after.id}')
    embed.timestamp = datetime.now(tz=UTC)
    await _send_embed(after.guild.id, embed)


@bot.listen()
async def on_member_update(before: Member, after: Member):
    if after.guild.id not in config.valid_guilds or after.bot:
        return

    if before.nick != after.nick:
        embed = Embed(title='Nickname Changed', color=_theme_color())
        embed.add_field(name='Member', value=after.mention, inline=True)
        embed.add_field(name='Before', value=before.nick or before.name, inline=True)
        embed.add_field(name='After', value=after.nick or after.name, inline=True)
        embed.set_footer(text=f'user id: {after.id}')
        embed.timestamp = datetime.now(tz=UTC)
        await _send_embed(after.guild.id, embed)

    before_roles = {role.id: role for role in before.roles if not role.is_default()}
    after_roles = {role.id: role for role in after.roles if not role.is_default()}
    added = [after_roles[rid] for rid in after_roles.keys() - before_roles.keys()]
    removed = [before_roles[rid] for rid in before_roles.keys() - after_roles.keys()]

    if added:
        embed = Embed(title='Member Role Added', color=_theme_color())
        embed.add_field(name='Member', value=after.mention, inline=True)
        embed.add_field(name='Roles', value=_role_mentions(added), inline=False)
        embed.set_footer(text=f'user id: {after.id}')
        embed.timestamp = datetime.now(tz=UTC)
        await _send_embed(after.guild.id, embed)

    if removed:
        embed = Embed(title='Member Role Removed', color=Color.red().value)
        embed.add_field(name='Member', value=after.mention, inline=True)
        embed.add_field(name='Roles', value=_role_mentions(removed), inline=False)
        embed.set_footer(text=f'user id: {after.id}')
        embed.timestamp = datetime.now(tz=UTC)
        await _send_embed(after.guild.id, embed)

    before_timeout = getattr(before, 'communication_disabled_until', None)
    after_timeout = getattr(after, 'communication_disabled_until', None)
    if before_timeout != after_timeout:
        embed = Embed(title='Member Timeout Updated', color=Color.orange().value)
        embed.add_field(name='Member', value=after.mention, inline=True)
        embed.add_field(name='Before', value=_format_dt(before_timeout), inline=True)
        embed.add_field(name='After', value=_format_dt(after_timeout), inline=True)
        embed.set_footer(text=f'user id: {after.id}')
        embed.timestamp = datetime.now(tz=UTC)
        await _send_embed(after.guild.id, embed)


def _emoji_map(emojis: Sequence[GuildEmoji]) -> dict[int, GuildEmoji]:
    return {emoji.id: emoji for emoji in emojis}


@bot.listen()
async def on_guild_emojis_update(guild: Guild, before: Sequence[GuildEmoji], after: Sequence[GuildEmoji]):
    if guild.id not in config.valid_guilds:
        return

    before_map = _emoji_map(before)
    after_map = _emoji_map(after)

    created_ids = after_map.keys() - before_map.keys()
    deleted_ids = before_map.keys() - after_map.keys()
    shared_ids = before_map.keys() & after_map.keys()

    for emoji_id in created_ids:
        emoji = after_map[emoji_id]
        if await _is_bot_audit_action(guild, discord.AuditLogAction.emoji_create, emoji_id):
            continue
        embed = Embed(title='Emoji Created', color=_theme_color())
        embed.add_field(name='Emoji', value=f'{emoji} ({emoji.name})', inline=True)
        embed.set_footer(text=f'emoji id: {emoji.id}')
        embed.timestamp = datetime.now(tz=UTC)
        await _send_embed(guild.id, embed)

    for emoji_id in deleted_ids:
        emoji = before_map[emoji_id]
        if await _is_bot_audit_action(guild, discord.AuditLogAction.emoji_delete, emoji_id):
            continue
        embed = Embed(title='Emoji Deleted', color=Color.red().value)
        embed.add_field(name='Emoji', value=f'{emoji.name}', inline=True)
        embed.set_footer(text=f'emoji id: {emoji.id}')
        embed.timestamp = datetime.now(tz=UTC)
        await _send_embed(guild.id, embed)

    for emoji_id in shared_ids:
        before_emoji = before_map[emoji_id]
        after_emoji = after_map[emoji_id]
        if before_emoji.name == after_emoji.name:
            continue
        if await _is_bot_audit_action(guild, discord.AuditLogAction.emoji_update, emoji_id):
            continue
        embed = Embed(title='Emoji Renamed', color=_theme_color())
        embed.add_field(name='Before', value=before_emoji.name, inline=True)
        embed.add_field(name='After', value=after_emoji.name, inline=True)
        embed.add_field(name='Emoji', value=str(after_emoji), inline=True)
        embed.set_footer(text=f'emoji id: {after_emoji.id}')
        embed.timestamp = datetime.now(tz=UTC)
        await _send_embed(guild.id, embed)


logger.info('Registered moderation log handlers')
