"""
AttuBot - Cross-Process Config Reload Signaling
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from attubot.client.core import db
from attubot.database.repositories import ReloadSignalRepository
from attubot.logging import get_logger


logger = get_logger(__name__)

_repo: ReloadSignalRepository | None = None

# which consumer processes need to react to each signal type. the bot's runtime
# config drives most behavior; the ingestor only needs to know about chat config
# changes so its in-memory chat_runtime stays current.
_signal_targets: dict[str, tuple[str, ...]] = {
    'guild': ('bot',),
    'theme': ('bot',),
    'system': ('bot',),
    'chat': ('bot', 'ingestor'),
}


def _get_repo() -> ReloadSignalRepository:
    """Get or create the reload signal repository"""
    global _repo  # noqa: PLW0603 - lazy singleton initialization requires global
    if _repo is None:
        _repo = ReloadSignalRepository(db.get_db())
    return _repo


async def send_signal(signal_type: str, guild_id: int | None = None):
    """Write a reload signal for every consumer that listens for this signal_type.

    safe to call from the web process - errors are logged but not re-raised.
    """
    targets = _signal_targets.get(signal_type, ('bot',))

    for target in targets:
        try:
            repo = _get_repo()
            await repo.send(signal_type, guild_id, target=target)
            logger.info(f'sent reload signal: type={signal_type} target={target} guild_id={guild_id}')
        except Exception as e:
            logger.error(f'failed to send reload signal (type={signal_type} target={target} guild_id={guild_id}): {e}')
