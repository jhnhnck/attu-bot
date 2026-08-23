# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.cc_stars | deprecated walking-skeleton stub for /cc stars."""

# the group is named `cc` (not `cc_stars`) so that the subgroup is `stars`,
# mirroring the legacy `/stars` shape under a distinct top-level name

from typing import cast

import structlog
from discord import ApplicationCommand, ApplicationContext, Bot, SlashCommandGroup


logger = structlog.stdlib.get_logger(__name__)


cc_group = SlashCommandGroup('cc', description='ccboard browsing and leaderboards (phase 2 stub)')
cc_stars_group = cc_group.create_subgroup('stars', 'ccboard browsing and leaderboards (phase 2 stub)')


@cc_stars_group.command(name='test', description='Walking-skeleton stub; replaced by real /cc stars commands in phase 2.6+')
async def cc_stars_test(ctx: ApplicationContext):
    await ctx.respond('cc_stars: phase 2.0 walking-skeleton stub; real commands land in phases 2.6-2.8', ephemeral=True)


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(cast(ApplicationCommand, cc_group))
