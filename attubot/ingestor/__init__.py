"""
AttuBot - Chat/RAG Ingestor Entry Point
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio

from attubot.logging import get_logger


logger = get_logger(__name__)


async def _run():
    from attubot.client.core import config
    from attubot.database import init_database
    from attubot.ingestor.tasks import DiscordIngestTask, WikiIngestTask
    from attubot.tasks.reload_watcher import ReloadWatcherTask
    from attubot.tasks.scheduler import scheduler

    config.ingestor_mode = True
    config.on_init()

    await init_database(config.database.url, config.database.name)
    await config.on_load()

    logger.info('Starting ingestor task scheduler')
    scheduler.register(ReloadWatcherTask())
    scheduler.register(WikiIngestTask())
    scheduler.register(DiscordIngestTask())
    await scheduler.start_all()

    # run forever - tasks handle their own scheduling
    await asyncio.Event().wait()


def start_ingestor():
    """entry point for the ingestor process (python attu-bot.py ingestor)"""
    logger.info('Starting Ingestor!')
    asyncio.run(_run())
