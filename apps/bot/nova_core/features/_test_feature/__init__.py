# SPDX-License-Identifier: Apache-2.0
"""nova_core.features._test_feature | manifest system validation feature."""

import discord
import structlog
from discord import ApplicationContext, Bot

from nova_core.manifest import FeatureManifest
from nova_core.tasks.base import BaseTask


logger = structlog.stdlib.get_logger(__name__)

_task_ran = False


class _StartupTask(BaseTask):
    """startup validation task - runs once on bot ready"""

    name = '_test_feature.startup'
    interval = None
    run_once = True
    run_immediately = True

    async def run(self) -> None:
        global _task_ran  # noqa: PLW0603 - module-level flag for test introspection
        logger.info('_test_feature: startup task ran')
        _task_ran = True


async def on_message(message) -> None:
    return


@discord.slash_command(name='manifest-ping', description='manifest system test ping')
async def _manifest_ping(ctx: ApplicationContext):
    await ctx.respond('manifest ping ok')


def setup(bot: Bot) -> None:
    bot.add_application_command(_manifest_ping)


manifest = FeatureManifest(
    name='_test_feature',
    tasks=[_StartupTask()],
    event_handlers={'on_message': on_message},
    setup=setup,
    document_classes=[],
    repository_classes=[],
    migrations=[],
)
