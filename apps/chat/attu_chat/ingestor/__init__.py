"""
AttuBot - Chat/RAG Ingestor Entry Point
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import signal

from attubot.logging import get_logger


logger = get_logger(__name__)


async def _run():
    from attu_chat.ingestor.tasks import DiscordIngestTask, WikiIngestTask
    from attubot.client.core import config, db
    from attubot.database import init_database
    from attubot.tasks.reload_watcher import ReloadWatcherTask
    from attubot.tasks.scheduler import scheduler

    config.ingestor_mode = True
    config.on_init()

    await init_database(config.database.url, config.database.name)
    await config.on_load()

    logger.info('starting ingestor task scheduler')
    scheduler.register(ReloadWatcherTask(target='ingestor'))
    scheduler.register(WikiIngestTask())
    scheduler.register(DiscordIngestTask())
    await scheduler.start_all()

    # run until SIGTERM or SIGINT (e.g. docker stop)
    loop = asyncio.get_running_loop()
    _stop = asyncio.Event()
    loop.add_signal_handler(signal.SIGTERM, _stop.set)
    loop.add_signal_handler(signal.SIGINT, _stop.set)

    logger.info('ingestor running; waiting for shutdown signal')
    await _stop.wait()

    logger.info('shutting down ingestor')
    await scheduler.stop_all()

    if db.client:
        await db.client.close()


def start_ingestor():
    """entry point for the ingestor process (python attu-chat.py ingestor)"""
    logger.info('starting ingestor')
    asyncio.run(_run())
