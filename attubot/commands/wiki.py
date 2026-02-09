"""
AttuBot - Wiki Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re

import discord
from discord import ApplicationContext, Bot, SlashCommandGroup
from discord.ext import commands

from attubot import config
from attubot.logging import get_logger
from attubot.util import is_authorized_guild
from attubot.wiki import AttuWiki

logger = get_logger(__name__)

# --- Wiki Commands ---

wiki_group = SlashCommandGroup('wiki', description='Utilities for managing and querying the wiki')

@wiki_group.command(name='lookup', description='Search the wiki for relevent pages; defaults to top result')
@discord.commands.option(name='query', required=True, description='Search Query', input_type=str)
@discord.commands.option(name='limit', required=False, description='Max Number of Results', input_type=int, default=1, min_value=1, max_value=10)
async def wiki_lookup(ctx: ApplicationContext, query: str, limit: int):
    wiki = AttuWiki()
    pages = await wiki.search(query, limit)

    # Handle no results
    if len(pages) == 0:
        await ctx.respond(f'**Oops, no results for __{query}__!** <:rockball_player:1308977543034048552>')
        return

    # Get wiki page format
    site_info = await wiki.site_info()

    def site_link(title: str, key: str, embed: bool = True) -> str:
        link = f'{ site_info["server"] }{ site_info["articlepath"] }'.replace('$1', key)
        return f'[{title}](<{link}>)' if not embed else f'[{title}]({link})'

    logger.debug(*pages)

    # Build response
    if len(pages) == 1:
        title, key = pages[0]['title'], pages[0]['key']
        await ctx.respond(f'**Result for __{query}__:** {site_link(title, key)}')

    else:
        msg = [f'**Results for __{query}__:**']

        for page in pages:
            title, key = page['title'], page['key']
            msg.append(f'1. { site_link(title, key, embed=False) }')

        await ctx.respond('\n'.join(msg))

# --- Wiki Admin Commands ---

@wiki_group.command(name='block', description='Blocks a specified user from the wiki (Admin only)')
@discord.commands.option(name='user', required=True, description='Wiki Username (case sensitive probably)', input_type=str)
@discord.commands.option(name='reason', required=True, description='Reason for blocking', input_type=str)
@commands.has_permissions(administrator=True)
@commands.check(is_authorized_guild)
async def wiki_block(ctx: ApplicationContext, user: str, reason: str):
    # check if link to the user
    extract = re.search(r'User:(.*)$', user)

    if extract is not None:
        user = extract[1]

    await ctx.respond(f'Blocking user [{user}]: {reason}')

    wiki = AttuWiki()
    await wiki.authenticate(config.wiki.user, config.wiki.key)
    result = await wiki.block(user, f'{reason} (on behalf of {ctx.user.global_name})')

    if result is False:
        await ctx.edit(content=f'Failed to block user [{user}] after {wiki.max_retries} attempts')
        # TODO: we should improve the webhooks some, maybe with a library outside pycord.
        await logger.send_to_webhook(Exception(f'wiki.block() failed for user "{user}" after {wiki.max_retries} retries'))

# --- Extension Def ---

def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(wiki_group)
