"""
AttuBot - Ingestor Background Tasks
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import timedelta

from attubot.client.core import config
from attubot.client.util import webhook_logging
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask


logger = get_logger(__name__)


class WikiIngestTask(BaseTask):
    """polls the wiki for recent changes and ingests new/updated pages into qdrant"""

    name: str = 'WikiIngest'
    interval = timedelta(hours=1)
    run_immediately = True

    async def on_start(self) -> None:
        await config.wait_for_load()

    @webhook_logging(scope=logger)
    async def run(self) -> None:
        if not config.chat_runtime.ingest_wiki:
            logger.debug('wiki ingest disabled; skipping')
            return

        from attubot.ingestor.pipelines.wiki import WikiPipeline

        pipeline = WikiPipeline()
        await pipeline.run_recent_changes()
