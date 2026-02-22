"""
AttuBot - Cross-Process Config Reload Signaling
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from typing import TYPE_CHECKING

from attubot.logging import get_logger

if TYPE_CHECKING:
    from attubot.database.repositories import ReloadSignalRepository

logger = get_logger(__name__)

_repo: 'ReloadSignalRepository | None' = None


def _get_repo() -> 'ReloadSignalRepository':
    """Get or create the reload signal repository"""
    global _repo  # noqa: PLW0603
    if _repo is None:
        from attubot import db
        from attubot.database.repositories import ReloadSignalRepository

        _repo = ReloadSignalRepository(db.get_db())
    return _repo


async def send_signal(signal_type: str, guild_id: int | None = None):
    """Write a reload signal to MongoDB so the bot process picks it up

    safe to call from the web process - errors are logged but not re-raised.
    """
    try:
        repo = _get_repo()
        await repo.send(signal_type, guild_id)
        logger.debug(f'Sent reload signal: type={signal_type} guild_id={guild_id}')
    except Exception as e:
        logger.error(f'Failed to send reload signal (type={signal_type} guild_id={guild_id}): {e}')


