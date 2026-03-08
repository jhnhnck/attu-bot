"""
AttuBot - Link Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re
import time
from typing import cast

import discord
from discord import ApplicationCommand, ApplicationContext, Bot, SlashCommandGroup
from discord.ext import commands

from attubot import bot, config
from attubot.database.models import FamilyDocument
from attubot.families import get_family, get_viewer_url, is_family_file, list_families, save_family
from attubot.logging import get_logger
from attubot.util import has_announcements_role


logger = get_logger(__name__)

# parses https://discord.com/channels/{guild}/{channel}/{message}
_MESSAGE_LINK_RE = re.compile(r'https://discord\.com/channels/(\d+)/(\d+)/(\d+)')

# --- Link Commands ---

link_group = SlashCommandGroup('link', description='Link utilities')
family_group = link_group.create_subgroup('family', description='FamilyEcho family tree commands')


@family_group.command(name='list', description='List all registered family trees')
async def family_list(ctx: ApplicationContext):
    config.guild(ctx.guild.id)  # ensures guild is authorized

    families = await list_families(ctx.guild.id)
    if not families:
        await ctx.respond('no families registered yet - use `/link family set` or `/link family upload` to add one')
        return

    lines = [f.display_name for f in sorted(families, key=lambda f: f.name)]
    await ctx.respond('**registered families:**\n' + '\n'.join(f'- {n}' for n in lines))


@family_group.command(name='view', description='Get a temporary FamilyEcho viewer link for a registered family')
@discord.commands.option(name='name', required=True, description='Family name')
async def family_view(ctx: ApplicationContext, name: str):
    config.guild(ctx.guild.id)  # ensures guild is authorized

    family = await get_family(ctx.guild.id, name)
    if family is None:
        await ctx.respond(f'no family named "{name}" is registered - use /link family set to add one', ephemeral=True)
        return

    await ctx.defer()

    try:
        url = await get_viewer_url(family.file_content)
    except Exception as err:
        logger.error(f'family_view: FamilyEcho API call failed for "{name}": {err}')
        await ctx.respond('failed to generate viewer link - the FamilyEcho API may be unavailable', ephemeral=True)
        return

    await ctx.respond(f'**{family.display_name}** - [open family tree]({url})\n-# link is valid for approximately 24 hours')


@family_group.command(name='set', description='Register a FamilyEcho family tree from an existing message link')
@discord.commands.option(name='name', required=True, description='Family name')
@discord.commands.option(name='message_link', required=True, description='Discord link to the message containing the FamilyScript file')
@commands.check(has_announcements_role)
async def family_set(ctx: ApplicationContext, name: str, message_link: str):
    config.guild(ctx.guild.id)  # ensures guild is authorized

    # parse the message link
    match = _MESSAGE_LINK_RE.search(message_link)
    if not match:
        await ctx.respond('that does not look like a valid Discord message link', ephemeral=True)
        return

    channel_id = int(match.group(2))
    message_id = int(match.group(3))

    # fetch the message and find the .txt attachment
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        msg = await channel.fetch_message(message_id)  # type: ignore[union-attr]
    except Exception as err:
        logger.warn(f'family_set: could not fetch message {message_id} from channel {channel_id}: {err}')
        await ctx.respond('could not fetch that message - check the link and that I have access to that channel', ephemeral=True)
        return

    family_attachments = [a for a in msg.attachments if a.filename.lower().endswith(('.txt', '.ged'))]
    if not family_attachments:
        await ctx.respond('no .txt or .ged file found on that message', ephemeral=True)
        return

    # download and validate
    try:
        raw = await family_attachments[0].read()
        content = raw.decode('utf-8')
    except Exception as err:
        logger.warn(f'family_set: failed to read attachment: {err}')
        await ctx.respond('failed to read the file from that message', ephemeral=True)
        return

    if not is_family_file(content):
        await ctx.respond('the file on that message does not look like a FamilyScript or GEDCOM file from familyecho.com', ephemeral=True)
        return

    normalized = name.strip().lower()
    doc = FamilyDocument(
        guild_id=ctx.guild.id,
        name=normalized,
        display_name=name.strip(),
        message_id=message_id,
        channel_id=channel_id,
        file_content=content,
        set_by=ctx.user.id,
        set_at=int(time.time()),
    )

    try:
        await save_family(doc)
    except Exception as err:
        logger.error(f'family_set: failed to save family "{normalized}": {err}')
        await ctx.respond('failed to save the family record', ephemeral=True)
        return

    await ctx.respond(f'registered family **{name.strip()}** - use `/link family view name:{name.strip()}` to get a viewer link')


@family_group.command(name='upload', description='Register a FamilyEcho family tree by uploading the file directly')
@discord.commands.option(name='name', required=True, description='Family name')
@discord.commands.option(name='file', required=True, description='FamilyScript .txt or GEDCOM .ged file downloaded from familyecho.com', input_type=discord.Attachment)
@commands.check(has_announcements_role)
async def family_upload(ctx: ApplicationContext, name: str, file: discord.Attachment):
    config.guild(ctx.guild.id)  # ensures guild is authorized

    # download the attachment
    try:
        raw = await file.read()
        content = raw.decode('utf-8')
    except Exception as err:
        logger.warn(f'family_upload: failed to read attachment: {err}')
        await ctx.respond('failed to read the attached file', ephemeral=True)
        return

    # validate it's a FamilyScript or GEDCOM file
    if not is_family_file(content):
        await ctx.respond('the attached file does not look like a FamilyScript or GEDCOM file from familyecho.com', ephemeral=True)
        return

    normalized = name.strip().lower()
    doc = FamilyDocument(
        guild_id=ctx.guild.id,
        name=normalized,
        display_name=name.strip(),
        file_content=content,
        set_by=ctx.user.id,
        set_at=int(time.time()),
    )

    try:
        await save_family(doc)
    except Exception as err:
        logger.error(f'family_upload: failed to save family "{normalized}": {err}')
        await ctx.respond('failed to save the family record', ephemeral=True)
        return

    await ctx.respond(f'registered family **{name.strip()}** - use `/link family view name:{name.strip()}` to get a viewer link')


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(cast(ApplicationCommand, link_group))
