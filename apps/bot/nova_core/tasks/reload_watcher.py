# SPDX-License-Identifier: Apache-2.0
"""nova_core.tasks.reload_watcher | reload watcher task."""

from datetime import timedelta

import structlog

from nova_core.client.core import config, db
from nova_core.client.util import webhook_logging
from nova_core.database.repositories import ReloadSignalRepository
from nova_core.tasks.base import BaseTask


logger = structlog.stdlib.get_logger(__name__)

_repo: ReloadSignalRepository | None = None


def _get_repo() -> ReloadSignalRepository:
    global _repo  # noqa: PLW0603 - lazy singleton initialization requires global

    if _repo is None:
        _repo = ReloadSignalRepository(db.get_db())
    return _repo


class ReloadWatcherTask(BaseTask):
    """Polls MongoDB for reload signals and applies them.

    each consumer process (bot, ingestor) instantiates this task with its own
    `target` so it only consumes signals addressed to it. without per-target
    filtering both processes raced on `find_one_and_delete` and dropped signals.
    """

    interval = timedelta(seconds=5)

    def __init__(self, target: str = 'bot') -> None:
        super().__init__()
        self.target = target
        self.name = f'ReloadWatcher[{target}]'

    async def on_start(self) -> None:
        await config.wait_for_load()

    @webhook_logging(scope=logger)
    async def run(self) -> None:
        """Poll for and process reload signals."""
        repo = _get_repo()

        try:
            signals = await repo.consume_all(self.target)
        except Exception as e:
            logger.error(f'error fetching reload signals: {e}')
            return

        if not signals:
            return

        logger.info(f'processing [{len(signals)}] reload signal(s) for target={self.target}')

        for signal in signals:
            try:
                if signal.signal_type == 'guild':
                    if signal.guild_id is None:
                        logger.warning('received guild reload signal with no guild_id; skipping')
                        continue
                    logger.info(f'reloading guild config for {signal.guild_id} (web-triggered)')
                    await config.load_guild(signal.guild_id)

                elif signal.signal_type == 'theme':
                    logger.info('reloading theme config (web-triggered)')
                    await config.load_theme()
                    from nova_core.tasks.logo_update import logo_update_task  # local import avoids circular dependency with tasks/__init__.py
                    from nova_core.tasks.scheduler import scheduler  # local import avoids circular dependency with tasks/__init__.py

                    scheduler.add_job(logo_update_task.run(), 'LogoUpdate', 'immediate')
                    logger.info('triggered immediate logo update from theme reload')

                elif signal.signal_type == 'system':
                    logger.info('reloading system globals (web-triggered)')
                    await config.load_globals()

                else:
                    logger.warning(f'unknown reload signal type: {signal.signal_type!r}')

            except Exception as e:
                logger.error(f'error processing reload signal {signal.signal_type}: {e}')


# singleton for registration in the bot process
reload_watcher_task = ReloadWatcherTask(target='bot')
