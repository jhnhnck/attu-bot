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
from attubot.tasks.jobs import job_backfill_channel, job_construct_year_links, job_fix_author_names
from attubot.util import is_bot_owner

logger = get_logger(__name__)

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


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(cast(ApplicationCommand, fix_group))
