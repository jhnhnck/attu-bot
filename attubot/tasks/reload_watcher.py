"""
AttuBot - Reload Watcher Task
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import timedelta

from attubot.client.core import config, db
from attubot.client.util import webhook_logging
from attubot.database.repositories import ReloadSignalRepository
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask


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
            logger.error(f'error fetching reload signals: {e}')
            return

        if not signals:
            return

        logger.info(f'processing [{len(signals)}] reload signal(s) from web')

        for signal in signals:
            try:
                if signal.signal_type == 'guild':
                    if signal.guild_id is None:
                        logger.warn('received guild reload signal with no guild_id; skipping')
                        continue
                    logger.info(f'reloading guild config for {signal.guild_id} (web-triggered)')
                    await config.load_guild(signal.guild_id)

                elif signal.signal_type == 'theme':
                    logger.info('reloading theme config (web-triggered)')
                    await config.load_theme()
                    from attubot.tasks.logo_update import logo_update_task  # local import avoids circular dependency with tasks/__init__.py
                    from attubot.tasks.scheduler import scheduler  # local import avoids circular dependency with tasks/__init__.py

                    scheduler.add_job(logo_update_task.run(), 'LogoUpdate', 'immediate')
                    logger.info('triggered immediate logo update from theme reload')

                elif signal.signal_type == 'system':
                    logger.info('reloading system globals (web-triggered)')
                    await config.load_globals()

                elif signal.signal_type == 'chat':
                    logger.info('reloading chat runtime config (signal received)')
                    await config.load_chat_runtime()

                else:
                    logger.warn(f'unknown reload signal type: {signal.signal_type!r}')

            except Exception as e:
                logger.error(f'error processing reload signal {signal.signal_type}: {e}')


# singleton for registration
reload_watcher_task = ReloadWatcherTask()
