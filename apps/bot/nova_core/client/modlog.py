# SPDX-License-Identifier: Apache-2.0
"""nova_core.client.modlog | moderation log handlers."""

from collections.abc import Sequence
from datetime import UTC, datetime

import discord
import structlog
from discord import Guild, GuildEmoji, Member, Role, User

from nova_core.client.core import bot, config
from nova_core.client.embeds import make_embed
from nova_core.client.util import event_log_context


logger = structlog.stdlib.get_logger(__name__)


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


async def _send_embed(guild_id: int, embed: discord.Embed) -> None:
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


async def _get_audit_actor(guild: Guild, action: discord.AuditLogAction, target_id: int) -> 'discord.User | discord.Member | None':
    # look up who performed the most recent audit action for this target
    try:
        async for entry in guild.audit_logs(limit=5, action=action):
            target = getattr(entry, 'target', None)
            if getattr(target, 'id', None) != target_id:
                continue
            return getattr(entry, 'user', None)
    except Exception as err:
        logger.debug(f'failed to resolve {action} actor for {guild.id} target={target_id}: {err}')
    return None


async def _get_remove_reason(guild: Guild, target_id: int) -> 'tuple[str | None, discord.User | discord.Member | None]':
    # check whether the member departure was a kick or ban, and by whom
    for action, label in ((discord.AuditLogAction.kick, 'kick'), (discord.AuditLogAction.ban, 'ban')):
        try:
            async for entry in guild.audit_logs(limit=3, action=action):
                if getattr(getattr(entry, 'target', None), 'id', None) != target_id:
                    continue
                return label, getattr(entry, 'user', None)
        except Exception as err:
            logger.debug(f'failed to resolve {label} audit for {guild.id} target={target_id}: {err}')
    return None, None


def _member_avatar(member: Member | User) -> str | None:
    return member.display_avatar.url if member.display_avatar else None


def _build_member_join_embed(member: Member) -> discord.Embed:
    created_at = member.created_at.replace(tzinfo=UTC) if member.created_at.tzinfo is None else member.created_at
    now = datetime.now(tz=UTC)
    age_days = (now - created_at).days
    age_str = f'{age_days // 365}y {age_days % 365}d' if age_days >= 365 else f'{age_days}d'

    embed = make_embed(
        'Member Joined',
        description=f'{member.mention} joined the server',
        footer=f'user id: {member.id}',
        author_name=_member_display_name(member),
        author_icon_url=_member_avatar(member),
    )
    embed.add_field(name='Account Created', value=_format_dt(created_at), inline=False)
    embed.add_field(name='Account Age', value=age_str, inline=True)
    return embed


def _build_member_leave_embed(
    member: Member,
    reason: str | None = None,
    actor: 'discord.User | discord.Member | None' = None,
) -> discord.Embed:
    if reason == 'kick':
        title = 'Member Kicked'
        description = f'{member.mention} was kicked from the server'
    elif reason == 'ban':
        title = 'Member Banned'
        description = f'{member.mention} was banned from the server'
    else:
        title = 'Member Left'
        description = f'{member.mention} left the server'

    embed = make_embed(
        title,
        description=description,
        footer=f'user id: {member.id}',
        author_name=_member_display_name(member),
        author_icon_url=_member_avatar(member),
    )
    embed.add_field(name='Joined', value=_format_dt(member.joined_at), inline=True)
    embed.add_field(name='Roles', value=_role_mentions(list(member.roles)), inline=False)
    if actor is not None:
        embed.add_field(name='By', value=actor.mention, inline=True)
    return embed


@bot.listen()
async def on_member_join(member: Member):
    with event_log_context(event='modlog.on_member_join', guild_id=member.guild.id, user_id=member.id):
        if member.guild.id not in config.valid_guilds:
            return
        embed = _build_member_join_embed(member)
        await _send_embed(member.guild.id, embed)


@bot.listen()
async def on_member_remove(member: Member):
    with event_log_context(event='modlog.on_member_remove', guild_id=member.guild.id, user_id=member.id):
        if member.guild.id not in config.valid_guilds:
            return
        reason, actor = await _get_remove_reason(member.guild, member.id)
        embed = _build_member_leave_embed(member, reason=reason, actor=actor)
        await _send_embed(member.guild.id, embed)


@bot.listen()
async def on_member_ban(guild: Guild, user: User | Member):
    with event_log_context(event='modlog.on_member_ban', guild_id=guild.id, user_id=user.id):
        if guild.id not in config.valid_guilds:
            return
        embed = make_embed(
            'Member Banned',
            description=f'{user.mention} was banned',
            footer=f'user id: {user.id}',
            author_name=_member_display_name(user),
            author_icon_url=_member_avatar(user),
        )
        await _send_embed(guild.id, embed)


@bot.listen()
async def on_member_unban(guild: Guild, user: User):
    with event_log_context(event='modlog.on_member_unban', guild_id=guild.id, user_id=user.id):
        if guild.id not in config.valid_guilds:
            return
        embed = make_embed(
            'Member Unbanned',
            description=f'{user.mention} was unbanned',
            footer=f'user id: {user.id}',
            author_name=_member_display_name(user),
            author_icon_url=_member_avatar(user),
        )
        await _send_embed(guild.id, embed)


@bot.listen()
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    with event_log_context(event='modlog.on_guild_channel_create', guild_id=channel.guild.id, channel_id=channel.id):
        if channel.guild.id not in config.valid_guilds:
            return
        if await _is_bot_audit_action(channel.guild, discord.AuditLogAction.channel_create, channel.id):
            return
        embed = make_embed('Channel Created', footer=f'channel id: {channel.id}')
        embed.add_field(name='Channel', value=channel.mention, inline=True)
        embed.add_field(name='Type', value=str(channel.type), inline=True)
        if channel.category:
            embed.add_field(name='Category', value=channel.category.name, inline=True)
        await _send_embed(channel.guild.id, embed)


@bot.listen()
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    with event_log_context(event='modlog.on_guild_channel_delete', guild_id=channel.guild.id, channel_id=channel.id):
        if channel.guild.id not in config.valid_guilds:
            return
        if await _is_bot_audit_action(channel.guild, discord.AuditLogAction.channel_delete, channel.id):
            return
        embed = make_embed('Channel Deleted', footer=f'channel id: {channel.id}')
        embed.add_field(name='Channel', value=channel.name, inline=True)
        embed.add_field(name='Type', value=str(channel.type), inline=True)
        if channel.category:
            embed.add_field(name='Category', value=channel.category.name, inline=True)
        await _send_embed(channel.guild.id, embed)


@bot.listen()
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
    with event_log_context(event='modlog.on_guild_channel_update', guild_id=after.guild.id, channel_id=after.id):
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

        channel_actor = await _get_audit_actor(after.guild, discord.AuditLogAction.channel_update, after.id)
        embed = make_embed('Channel Updated', footer=f'channel id: {after.id}')
        embed.add_field(name='Channel', value=after.mention, inline=False)
        for label, old, new in changes:
            embed.add_field(name=label, value=f'{old} -> {new}', inline=False)
        if channel_actor is not None:
            embed.add_field(name='By', value=channel_actor.mention, inline=True)
        await _send_embed(after.guild.id, embed)


@bot.listen()
async def on_guild_role_create(role: Role):
    with event_log_context(event='modlog.on_guild_role_create', guild_id=role.guild.id, role_id=role.id):
        if role.guild.id not in config.valid_guilds:
            return
        if await _is_bot_audit_action(role.guild, discord.AuditLogAction.role_create, role.id):
            return
        embed = make_embed('Role Created', footer=f'role id: {role.id}')
        embed.add_field(name='Role', value=role.mention, inline=True)
        embed.add_field(name='Color', value=str(role.color), inline=True)
        await _send_embed(role.guild.id, embed)


@bot.listen()
async def on_guild_role_delete(role: Role):
    with event_log_context(event='modlog.on_guild_role_delete', guild_id=role.guild.id, role_id=role.id):
        if role.guild.id not in config.valid_guilds:
            return
        if await _is_bot_audit_action(role.guild, discord.AuditLogAction.role_delete, role.id):
            return
        embed = make_embed('Role Deleted', footer=f'role id: {role.id}')
        embed.add_field(name='Role', value=role.name, inline=True)
        embed.add_field(name='Color', value=str(role.color), inline=True)
        await _send_embed(role.guild.id, embed)


@bot.listen()
async def on_guild_role_update(before: Role, after: Role):
    with event_log_context(event='modlog.on_guild_role_update', guild_id=after.guild.id, role_id=after.id):
        if after.guild.id not in config.valid_guilds:
            return
        # skip the bot_color role - its color is updated automatically by logo task
        try:
            gc = config.guild(after.guild.id)
            if gc.roles.bot_color != 0 and after.id == gc.roles.bot_color:
                return
        except Exception as err:
            logger.debug(f'failed to resolve guild config for bot_color role check: {err}')
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

        role_update_actor = await _get_audit_actor(after.guild, discord.AuditLogAction.role_update, after.id)
        embed = make_embed('Role Updated', footer=f'role id: {after.id}')
        embed.add_field(name='Role', value=after.mention, inline=False)
        for label, old, new in changes:
            embed.add_field(name=label, value=f'{old} -> {new}', inline=False)
        if role_update_actor is not None:
            embed.add_field(name='By', value=role_update_actor.mention, inline=True)
        await _send_embed(after.guild.id, embed)


@bot.listen()
async def on_member_update(before: Member, after: Member):  # noqa: PLR0912, PLR0915 - single event handler covering nick + role changes with audit log calls
    with event_log_context(event='modlog.on_member_update', guild_id=after.guild.id, user_id=after.id):
        if after.guild.id not in config.valid_guilds or after.bot:
            return

        if before.nick != after.nick:
            # use audit log for authoritative before/after values and actor
            actor: discord.User | discord.Member | None = None
            audit_before_nick: str | None = before.nick
            audit_after_nick: str | None = after.nick
            try:
                async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                    target = getattr(entry, 'target', None)
                    if getattr(target, 'id', None) != after.id:
                        continue
                    changes = getattr(entry, 'changes', None)
                    if changes is not None and hasattr(changes.before, 'nick'):
                        audit_before_nick = changes.before.nick
                        audit_after_nick = changes.after.nick
                        actor = getattr(entry, 'user', None)
                        break
            except Exception as err:
                logger.debug(f'failed to fetch audit log for nick change guild={after.guild.id} user={after.id}: {err}')

            description = f'{after.mention} changed their nickname'
            if actor is not None and actor.id != after.id:
                description = f'{after.mention} had their nickname changed by {actor.mention}'

            embed = make_embed(
                'Nickname Changed',
                description=description,
                footer=f'user id: {after.id}',
                author_name=_member_display_name(after),
                author_icon_url=_member_avatar(after),
            )
            embed.add_field(name='Before', value=audit_before_nick or before.name, inline=True)
            embed.add_field(name='After', value=audit_after_nick or after.name, inline=True)
            await _send_embed(after.guild.id, embed)

        before_roles = {role.id: role for role in before.roles if not role.is_default()}
        after_roles = {role.id: role for role in after.roles if not role.is_default()}
        added = [after_roles[rid] for rid in after_roles.keys() - before_roles.keys()]
        removed = [before_roles[rid] for rid in before_roles.keys() - after_roles.keys()]

        role_actor: discord.User | discord.Member | None = None
        if added or removed:
            role_actor = await _get_audit_actor(after.guild, discord.AuditLogAction.member_role_update, after.id)

        if added:
            embed = make_embed(
                'Member Role Added',
                description=f'{after.mention} was given a role',
                footer=f'user id: {after.id}',
                author_name=_member_display_name(after),
                author_icon_url=_member_avatar(after),
            )
            embed.add_field(name='Roles', value=_role_mentions(added), inline=False)
            if role_actor is not None and role_actor.id != after.id:
                embed.add_field(name='By', value=role_actor.mention, inline=True)
            await _send_embed(after.guild.id, embed)

        if removed:
            embed = make_embed(
                'Member Role Removed',
                description=f'{after.mention} had a role removed',
                footer=f'user id: {after.id}',
                author_name=_member_display_name(after),
                author_icon_url=_member_avatar(after),
            )
            embed.add_field(name='Roles', value=_role_mentions(removed), inline=False)
            if role_actor is not None and role_actor.id != after.id:
                embed.add_field(name='By', value=role_actor.mention, inline=True)
            await _send_embed(after.guild.id, embed)

        before_timeout = getattr(before, 'communication_disabled_until', None)
        after_timeout = getattr(after, 'communication_disabled_until', None)
        if before_timeout != after_timeout:
            timeout_actor = await _get_audit_actor(after.guild, discord.AuditLogAction.member_update, after.id)
            timeout_description = (f'{after.mention} was timed out by {timeout_actor.mention}' if after_timeout else f'{after.mention} had their timeout removed by {timeout_actor.mention}') if timeout_actor is not None else f'{after.mention} had their timeout updated'

            embed = make_embed(
                'Member Timeout Updated',
                description=timeout_description,
                footer=f'user id: {after.id}',
                author_name=_member_display_name(after),
                author_icon_url=_member_avatar(after),
            )
            embed.add_field(name='Before', value=_format_dt(before_timeout), inline=True)
            embed.add_field(name='After', value=_format_dt(after_timeout), inline=True)
            await _send_embed(after.guild.id, embed)


def _emoji_map(emojis: Sequence[GuildEmoji]) -> dict[int, GuildEmoji]:
    return {emoji.id: emoji for emoji in emojis}


@bot.listen()
async def on_guild_emojis_update(guild: Guild, before: Sequence[GuildEmoji], after: Sequence[GuildEmoji]):
    with event_log_context(event='modlog.on_guild_emojis_update', guild_id=guild.id):
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
            embed = make_embed('Emoji Created', footer=f'emoji id: {emoji.id}')
            embed.add_field(name='Emoji', value=f'{emoji} ({emoji.name})', inline=True)
            await _send_embed(guild.id, embed)

        for emoji_id in deleted_ids:
            emoji = before_map[emoji_id]
            if await _is_bot_audit_action(guild, discord.AuditLogAction.emoji_delete, emoji_id):
                continue
            embed = make_embed('Emoji Deleted', footer=f'emoji id: {emoji.id}')
            embed.add_field(name='Emoji', value=f'{emoji.name}', inline=True)
            await _send_embed(guild.id, embed)

        for emoji_id in shared_ids:
            before_emoji = before_map[emoji_id]
            after_emoji = after_map[emoji_id]
            if before_emoji.name == after_emoji.name:
                continue
            if await _is_bot_audit_action(guild, discord.AuditLogAction.emoji_update, emoji_id):
                continue
            embed = make_embed('Emoji Renamed', footer=f'emoji id: {after_emoji.id}')
            embed.add_field(name='Before', value=before_emoji.name, inline=True)
            embed.add_field(name='After', value=after_emoji.name, inline=True)
            embed.add_field(name='Emoji', value=str(after_emoji), inline=True)
            await _send_embed(guild.id, embed)


logger.info('registered moderation log handlers')
