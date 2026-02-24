"""
AttuBot - Wiki Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import re

import discord
from discord import ApplicationContext, Bot, SlashCommandGroup
from discord.ext import commands

from attubot import config
from attubot.logging import get_logger
from attubot.util import is_authorized_guild, theme_color
from attubot.wiki import get_wiki
from attubot.wiki.models import PageSummary, SiteInfo

# embed description is capped at 4096 chars; leave room for ellipsis
_EMBED_DESC_LIMIT = 4000


def build_wiki_embed(summary: PageSummary, site_info: SiteInfo) -> discord.Embed:
    """build a discord embed representing a wiki page summary"""
    key = summary.title.replace(' ', '_')
    url = site_info.page_url(key)

    extract = summary.extract or '_No description available._'
    if len(extract) > _EMBED_DESC_LIMIT:
        extract = extract[:_EMBED_DESC_LIMIT] + '...'

    embed = discord.Embed(
        title=summary.title,
        description=extract,
        color=theme_color(),
    )

    if summary.thumbnail:
        embed.set_thumbnail(url=summary.thumbnail.source)

    embed.add_field(name='Open', value=f'[Wiki page]({url})', inline=False)
    embed.set_footer(text=site_info.site_name)

    return embed


logger = get_logger(__name__)

# --- Wiki Commands ---

wiki_group = SlashCommandGroup('wiki', description='Utilities for managing and querying the wiki')


@wiki_group.command(name='random', description='Get a random page from the wiki')
async def wiki_random(ctx: ApplicationContext):
    await ctx.defer()
    wiki = get_wiki()
    summary, site_info = await asyncio.gather(wiki.pages.get_random_summary(), wiki.search.site_info())
    embed = build_wiki_embed(summary, site_info)
    await ctx.respond(embed=embed)


@wiki_group.command(name='lookup', description='Search the wiki for relevent pages; defaults to top result')
@discord.commands.option(name='query', required=True, description='Search Query', input_type=str)
@discord.commands.option(name='limit', required=False, description='Max Number of Results', input_type=int, default=1, min_value=1, max_value=10)
async def wiki_lookup(ctx: ApplicationContext, query: str, limit: int):
    wiki = get_wiki()
    pages = await wiki.search.search(query, limit)

    # handle no results
    if len(pages) == 0:
        await ctx.respond(f'**Oops, no results for __{query}__!** <:rockball_player:1308977543034048552>')
        return

    site_info = await wiki.search.site_info()

    logger.debug(*pages)

    # build response
    if len(pages) == 1:
        page = pages[0]
        link = f'[{page.title}]({site_info.page_url(page.key)})'
        await ctx.respond(f'**Result for __{query}__:** {link}')

    else:
        msg = [f'**Results for __{query}__:**']

        for page in pages:
            link = f'[{page.title}](<{site_info.page_url(page.key)}>)'
            msg.append(f'1. {link}')

        await ctx.respond('\n'.join(msg))

# --- Wiki Admin Commands ---

@wiki_group.command(name='block', description='Blocks a specified user from the wiki (Admin only)')
@discord.commands.option(name='user', required=True, description='Wiki Username (case sensitive probably)', input_type=str)
@discord.commands.option(name='reason', required=True, description='Reason for blocking', input_type=str)
@commands.has_permissions(administrator=True)
@commands.check(is_authorized_guild)
async def wiki_block(ctx: ApplicationContext, user: str, reason: str):
    # strip User: prefix if a profile link was pasted
    extract = re.search(r'User:(.*)$', user)
    if extract is not None:
        user = extract[1]

    await ctx.respond(f'Blocking user [{user}]: {reason}')

    wiki = get_wiki()
    await wiki.authenticate(config.wiki.user, config.wiki.key)
    success = await wiki.admin.block(user, f'{reason} (on behalf of {ctx.user.global_name})')

    if not success:
        await ctx.edit(content=f'Failed to block user [{user}] after 3 attempts')
        await logger.send_to_webhook(Exception(f'wiki.admin.block() failed for user "{user}" after 3 retries'))

# --- Extension Def ---

def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(wiki_group)
