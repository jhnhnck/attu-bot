"""
AttuBot - Chat Source Registry (chat_sources collection wrapper)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from attu_models import ChatSourceDocument, ChatSourceRepository
from attubot.client.core import db
from attubot.logging import get_logger


logger = get_logger(__name__)

_repo: ChatSourceRepository | None = None


def _get_repo() -> ChatSourceRepository:
    global _repo  # noqa: PLW0603 - lazy singleton initialization requires global
    if _repo is None:
        _repo = ChatSourceRepository(db.get_db())
    return _repo


async def get_source(source_id: str) -> ChatSourceDocument | None:
    """fetch a source record by id; returns None if not found"""
    return await _get_repo().get(source_id)


async def upsert_source(doc: ChatSourceDocument) -> None:
    """save or update a source record"""
    await _get_repo().upsert(doc)


async def flag_incorrect(source_id: str) -> None:
    """mark a source as incorrect; prevents re-ingestion"""
    await _get_repo().flag_incorrect(source_id)
