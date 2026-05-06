# SPDX-License-Identifier: Apache-2.0
"""doom_bot.signals | Cross-Process config reload signaling."""

from doom_bot.client.core import db
from doom_bot.database.repositories import ReloadSignalRepository
from doom_bot.logging import get_logger


logger = get_logger(__name__)

_repo: ReloadSignalRepository | None = None

# which consumer processes need to react to each signal type. the bot's runtime
# config drives most behavior; chat-related signals were here when the ingestor
# was a sibling process and will return when chat is revived.
_signal_targets: dict[str, tuple[str, ...]] = {
    'guild': ('bot',),
    'theme': ('bot',),
    'system': ('bot',),
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
