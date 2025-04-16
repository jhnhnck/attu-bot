"""
AttuBot - Wiki Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re

import discord
from discord import ApplicationContext, Bot, SlashCommandGroup
from discord.ext import commands

from attubot.config import Config
from attubot.logging import get_logger
from attubot.util import is_authorized_guild
from attubot.wiki import AttuWiki

logger = get_logger(__name__)

# --- Wiki Commands ---

wiki_group = SlashCommandGroup('wiki', description='Utlities for managing and querying the wiki')

@wiki_group.command(name='lookup', description='Search the wiki for relevent pages; defaults to top result')
@discord.commands.option(name='query', required=True, description='Search Query', input_type=str)
@discord.commands.option(name='limit', required=False, description='Max Number of Results', input_type=int, default=1, min_value=1, max_value=10)
async def wiki_lookup(ctx: ApplicationContext, query: str, limit: int):
    wiki = AttuWiki()
    pages = await wiki.search(query, limit)

    # Handle no results
    if len(pages) == 0:
        await ctx.respond('Oops, no results! <:rockball_player:1308977543034048552>')
        return

    # Get wiki page format
    site_info = await wiki.site_info()
    fmt = f'{site_info["server"]}{site_info["articlepath"]}'

    # Build response
    if len(pages) == 1:
        await ctx.respond(fmt.replace('$1', pages[0]['key']))

    else:
        msg = [f'## Top Results for "{query}"']

        for page in pages:
            msg.append(f'1. [{page["title"]}](<{fmt.replace("$1", page["key"])}>)')

        await ctx.respond('\n'.join(msg))

# --- Wiki Admin Commands ---

@wiki_group.command(name='block', description='Blocks a specified user from the wiki (Admin only)')
@discord.commands.option(name='user', required=True, description='Wiki Username (case sensitive probably)', input_type=str)
@discord.commands.option(name='reason', required=True, description='Reason for blocking', input_type=str)
@commands.has_permissions(administrator=True)
@commands.check(is_authorized_guild)
async def wiki_block(ctx: ApplicationContext, user, reason):
    # check if link to the user
    extract = re.search(r'User:(.*)$', user)

    if extract is not None:
        user = extract[1]

    await ctx.respond(f'Blocking user [{user}]: {reason}')

    wiki = AttuWiki()
    await wiki.authenticate(Config.wiki_user, Config.wiki_key)
    await wiki.block(user, f'{reason} (on behalf of {ctx.user.global_name})')

# --- Extension Def ---

def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(wiki_group)
