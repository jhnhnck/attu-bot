"""
AttuBot - Chat Subsystem Initialization Task
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import datetime, timedelta

from attubot.client.core import config
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask


logger = get_logger(__name__)


class ChatInitTask(BaseTask):
    """initialize chat subsystems (embedder, reranker, vector store, llm) at startup"""

    name = 'ChatInit'
    interval = None        # one-shot; next_run() returns far future
    run_immediately = True

    async def on_start(self) -> None:
        await config.wait_for_load()

    async def run(self) -> None:
        import asyncio

        from attubot.commands.chat import _get_system_prompt
        from attubot.ingestor.embedder import _get_embedder
        from attubot.ingestor.llm import _get_llm
        from attubot.ingestor.reranker import _get_reranker
        from attubot.ingestor.vector_store import _get_vector_store

        logger.info('Initializing chat subsystems...')
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _get_embedder)   # blocking model load
        await loop.run_in_executor(None, _get_reranker)   # blocking model load
        _get_vector_store()
        _get_llm()
        _get_system_prompt()
        logger.info('Chat subsystems ready')

    async def next_run(self) -> datetime:
        # effectively never runs again after the immediate run
        return datetime.now().astimezone() + timedelta(days=36500)


chat_init_task = ChatInitTask()
