# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.cc_stars | ccboard star browsing and leaderboards."""

# the group is named `cc` (not `cc_stars`) so that the subgroup is `stars`,
# mirroring the legacy `/stars` shape under a distinct top-level name

from typing import cast

import discord
import structlog
from discord import ApplicationCommand, ApplicationContext, Bot, SlashCommandGroup

from nova_core.client.core import config
from nova_core.client.embeds import ui_emoji
from nova_core.client.util import theme_color
from nova_core.commands.stars import _PAGE_SIZE, _get_entry_repo


logger = structlog.stdlib.get_logger(__name__)


# message-style says never ship internal state; the stub wording is a deliberate
# exception until the real commands land
cc_group = SlashCommandGroup('cc', description='ccboard browsing and leaderboards (phase 2 stub)')
cc_stars_group = cc_group.create_subgroup('stars', 'ccboard browsing and leaderboards (phase 2 stub)')


@cc_stars_group.command(name='test', description='Walking-skeleton stub; replaced by real /cc stars commands in phase 2.6+')
async def cc_stars_test(ctx: ApplicationContext):
    await ctx.respond('cc_stars: phase 2.0 walking-skeleton stub; real commands land in phases 2.6-2.8', ephemeral=True)


async def _cc_top_messages_embed(ctx: ApplicationContext, entries: list, guild_id: int, title: str) -> None:
    """build and send a numbered top-messages embed from BoardEntryDocument list."""
    if not entries:
        await ctx.respond(f'no data yet for {title.lower()} {ui_emoji("rockball_player")}', ephemeral=True)
        return

    lines = []
    for i, entry in enumerate(entries[:_PAGE_SIZE], start=1):
        jump_url = f'https://discord.com/channels/{guild_id}/{entry.channel_id}/{entry.message_id}'
        lines.append(f'**{i}.** {jump_url} - **{entry.positive_points}** stars')

    embed = discord.Embed(title=title, description='\n'.join(lines), color=theme_color())
    await ctx.respond(embed=embed)


@cc_stars_group.command(name='top-messages', description='top messages by stars')
async def cc_top_messages(ctx: ApplicationContext):
    guild_id = ctx.guild.id
    try:
        guild_config = config.guild(guild_id)
    except Exception:
        await ctx.respond("I couldn't load this server's config", ephemeral=True)
        return

    if not guild_config.ccboard.enabled:
        await ctx.respond('this feature is coming soon', ephemeral=True)
        return

    try:
        entry_repo = _get_entry_repo()
    except RuntimeError:
        await ctx.respond("the ccboard isn't ready yet", ephemeral=True)
        return

    entries = await entry_repo.leaderboard_top_messages(guild_id, limit=_PAGE_SIZE)
    await _cc_top_messages_embed(ctx, entries, guild_id, 'Top Messages')


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(cast('ApplicationCommand', cc_group))
