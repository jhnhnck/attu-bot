# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.wiki | wiki commands."""

import asyncio
import contextlib
import re
import time
from typing import TYPE_CHECKING

import discord
import structlog
from discord import ApplicationContext, Bot, SlashCommandGroup
from discord.ext import commands

import attu_logging
from nova_core.client.core import bot, config
from nova_core.client.embeds import make_embed, ui_emoji
from nova_core.client.util import is_authorized_guild
from nova_core.database.models import WikiViewDocument
from nova_core.wiki import get_wiki
from nova_core.wiki.models import PageSummary, SearchResult, SiteInfo


if TYPE_CHECKING:
    from nova_core.database.repositories import WikiViewRepository


# embed description is capped at 4096 chars; leave room for ellipsis
_EMBED_DESC_LIMIT = 4000

# view timeout in seconds (30 minutes); used for expires_at ttl
_VIEW_TIMEOUT = 1800

# module-level repo singleton; wired in by database/__init__.py
_wiki_view_repo: 'WikiViewRepository | None' = None


def _get_view_repo() -> 'WikiViewRepository':
    if _wiki_view_repo is None:
        raise RuntimeError('wiki view repo not initialized')
    return _wiki_view_repo


def build_wiki_embed(summary: PageSummary, site_info: SiteInfo) -> tuple[discord.Embed, str]:
    """build a discord embed representing a wiki page summary; returns (embed, page_url)"""
    key = summary.title.replace(' ', '_')
    url = site_info.page_url(key)

    extract = summary.extract or '_No description available._'
    if len(extract) > _EMBED_DESC_LIMIT:
        extract = extract[:_EMBED_DESC_LIMIT] + '...'

    embed = make_embed(
        summary.title,
        description=extract,
        footer=site_info.site_name,
        thumbnail=summary.thumbnail.source if summary.thumbnail else None,
        timestamp=False,
    )

    return embed, url


class WikiLinkView(discord.ui.View):
    """simple view with a single link button to open a wiki page"""

    def __init__(self, url: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label='Open Wiki!', style=discord.ButtonStyle.link, url=url, row=0))


class WikiLookupView(discord.ui.View):
    """paginated view for cycling through wiki search results - persistent across reboots"""

    def __init__(self, message_id: int, invoker_user_id: int, pages: list[SearchResult], site_info: SiteInfo, initial_embed: discord.Embed, initial_url: str, current_index: int = 0):
        super().__init__(timeout=None)
        self._message_id = message_id
        self._invoker_user_id = invoker_user_id
        self._pages = pages
        self._site_info = site_info
        self._index = current_index
        self._current_url = initial_url
        self._current_embed = initial_embed
        self._build_buttons()

    def _build_buttons(self) -> None:
        """clear and rebuild buttons for the current state"""
        self.clear_items()

        # link button is always first
        self.add_item(discord.ui.Button(label='Open Wiki!', style=discord.ButtonStyle.link, url=self._current_url, row=0))

        total = len(self._pages)
        if total > 1:
            prev_btn = discord.ui.Button(
                label='Previous',
                style=discord.ButtonStyle.secondary,
                disabled=self._index == 0,
                custom_id=f'wiki_prev_{self._message_id}',
                row=0,
            )
            prev_btn.callback = self._prev_callback
            self.add_item(prev_btn)

            next_btn = discord.ui.Button(
                label=f'Next ({self._index + 1}/{total})',
                style=discord.ButtonStyle.primary,
                disabled=self._index >= total - 1,
                custom_id=f'wiki_next_{self._message_id}',
                row=0,
            )
            next_btn.callback = self._next_callback
            self.add_item(next_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._invoker_user_id:
            await interaction.response.send_message(f"those aren't yours to press {ui_emoji('rockball')}", ephemeral=True)
            return False
        return True

    async def cleanup(self) -> None:
        """remove from db and disable buttons"""
        with contextlib.suppress(Exception):
            await _get_view_repo().delete(self._message_id)
        self.disable_all_items()

    async def _fetch_and_update(self, interaction: discord.Interaction) -> None:
        """fetch the summary for the current index and update the message"""
        await interaction.response.defer()
        wiki = get_wiki()
        page = self._pages[self._index]
        summary = await wiki.pages.get_summary(page.title)

        if summary is None:
            # fallback: build a minimal summary from the search result
            summary = PageSummary(title=page.title, extract=page.excerpt or '')

        self._current_embed, self._current_url = build_wiki_embed(summary, self._site_info)
        self._build_buttons()

        # persist updated index
        with contextlib.suppress(Exception):
            repo = _get_view_repo()
            doc = await repo.get(self._message_id)
            if doc:
                doc.current_index = self._index
                await repo.upsert(doc)

        await interaction.edit_original_response(embed=self._current_embed, view=self)

    async def _prev_callback(self, interaction: discord.Interaction) -> None:
        self._index -= 1
        await self._fetch_and_update(interaction)

    async def _next_callback(self, interaction: discord.Interaction) -> None:
        self._index += 1
        await self._fetch_and_update(interaction)


logger = structlog.stdlib.get_logger(__name__)

# --- Wiki Commands ---

wiki_group = SlashCommandGroup('wiki', description='Utilities for managing and querying the wiki')


@wiki_group.command(name='random', description='Get a random page from the wiki')
async def wiki_random(ctx: ApplicationContext):
    await ctx.defer()
    wiki = get_wiki()
    summary, site_info = await asyncio.gather(wiki.pages.get_random_summary(), wiki.search.site_info())
    embed, url = build_wiki_embed(summary, site_info)
    await ctx.respond(embed=embed, view=WikiLinkView(url))


_SEARCH_LIMIT = 11


@wiki_group.command(name='lookup', description='Search the wiki for relevent pages')
@discord.commands.option(name='query', required=True, description='Search Query', input_type=str)
async def wiki_lookup(ctx: ApplicationContext, query: str):
    await ctx.defer()
    wiki = get_wiki()

    # fetch title-only result first, then up to 11 body results concurrently
    title_pages, body_pages = await asyncio.gather(
        wiki.search.search_title(query, 1),
        wiki.search.search(query, _SEARCH_LIMIT),
    )

    # combine: title result first, then body results not already included, capped at _SEARCH_LIMIT
    seen = {p.title for p in title_pages}
    pages = list(title_pages)
    for p in body_pages:
        if len(pages) >= _SEARCH_LIMIT:
            break
        if p.title not in seen:
            seen.add(p.title)
            pages.append(p)

    # handle no results
    if len(pages) == 0:
        await ctx.respond(f'**Oops, no results for __{query}__!** {ui_emoji("rockball_player")}')
        return

    site_info = await wiki.search.site_info()
    logger.debug(*pages)

    # fetch the full summary for the first result
    summary = await wiki.pages.get_summary(pages[0].title)
    if summary is None:
        summary = PageSummary(title=pages[0].title, extract=pages[0].excerpt or '')

    embed, url = build_wiki_embed(summary, site_info)

    if len(pages) == 1:
        await ctx.respond(embed=embed, view=WikiLinkView(url))
    else:
        # respond first to get the message id, then attach the persistent view
        await ctx.respond(embed=embed)
        message = await ctx.interaction.original_response()
        message_id = message.id

        view = WikiLookupView(message_id, ctx.user.id, pages, site_info, embed, url)

        if ctx.guild_id is None or ctx.channel_id is None:
            await ctx.respond('Failed: this command must be used in a server', ephemeral=True)
            return

        repo = _get_view_repo()
        await repo.upsert(
            WikiViewDocument(
                message_id=message_id,
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
                invoker_user_id=ctx.user.id,
                query=query,
                current_index=0,
                page_titles=[p.title for p in pages],
                page_keys=[p.key for p in pages],
                expires_at=int(time.time()) + _VIEW_TIMEOUT,
            )
        )

        await message.edit(view=view)
        bot.add_view(view, message_id=message_id)


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
        await ctx.edit(content=f'Failed: could not block user [{user}] after 3 attempts')
        await attu_logging.webhook.send_to_webhook(Exception(f'wiki.admin.block() failed for user "{user}" after 3 retries'))


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(wiki_group)
