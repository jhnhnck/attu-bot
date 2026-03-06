"""
AttuBot - Reload Watcher Task
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import timedelta

from attubot.core import config, db
from attubot.database.repositories import ReloadSignalRepository
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask
from attubot.util import webhook_logging


logger = get_logger(__name__)

_repo: ReloadSignalRepository | None = None


def _get_repo() -> ReloadSignalRepository:
    global _repo  # noqa: PLW0603 - lazy singleton initialization requires global

    if _repo is None:
        _repo = ReloadSignalRepository(db.get_db())
    return _repo


class ReloadWatcherTask(BaseTask):
    """Polls MongoDB for reload signals and applies them."""

    name: str = 'ReloadWatcher'
    interval = timedelta(seconds=5)

    async def on_start(self) -> None:
        await config.wait_for_load()

    @webhook_logging(scope=logger)
    async def run(self) -> None:
        """Poll for and process reload signals."""
        repo = _get_repo()

        try:
            signals = await repo.consume_all()
        except Exception as e:
            logger.error(f'Error fetching reload signals: {e}')
            return

        if not signals:
            return

        logger.info(f'Processing {len(signals)} reload signal(s) from web')

        for signal in signals:
            try:
                if signal.signal_type == 'guild':
                    if signal.guild_id is None:
                        logger.warn('Received guild reload signal with no guild_id; skipping')
                        continue
                    logger.info(f'Reloading guild config for {signal.guild_id} (web-triggered)')
                    await config.load_guild(signal.guild_id)

                elif signal.signal_type == 'theme':
                    logger.info('Reloading theme config (web-triggered)')
                    await config.load_theme()

                elif signal.signal_type == 'system':
                    logger.info('Reloading system globals (web-triggered)')
                    await config.load_globals()

                else:
                    logger.warn(f'Unknown reload signal type: {signal.signal_type!r}')

            except Exception as e:
                logger.error(f'Error processing reload signal {signal.signal_type}: {e}')


# singleton for registration
reload_watcher_task = ReloadWatcherTask()
