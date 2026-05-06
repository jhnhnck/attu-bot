"""
AttuBot - FamilyEcho Family Tracking
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re

import httpx

from attubot.database.models import FamilyDocument
from attubot.database.repositories import FamilyRepository
from attubot.logging import get_logger


logger = get_logger(__name__)

# module-level singleton seeded by database/__init__.py
_family_repo: FamilyRepository | None = None

familyecho_api = 'https://www.familyecho.com/api/'

# matches the first three lines of a FamilyScript (.txt) file; \r? handles windows line endings
_FAMILYSCRIPT_HEADER_RE = re.compile(r'^# .+\r?\n#\r?\n# FamilyScript downloaded by ')

# matches the first two lines of a GEDCOM (.ged) file exported from Family Echo
_GEDCOM_HEADER_RE = re.compile(r'^0 HEAD\r?\n1 SOUR Family Echo')


def _get_repo() -> FamilyRepository:
    if _family_repo is None:
        raise RuntimeError('family repo not initialized')
    return _family_repo


def is_family_file(content: str) -> bool:
    """Return True if content is a FamilyScript or Family Echo GEDCOM file."""
    if _FAMILYSCRIPT_HEADER_RE.match(content) or _GEDCOM_HEADER_RE.match(content):
        return True
    header = content[:200].splitlines()[:5]
    logger.debug(f'family file header mismatch; first lines: {header!r}')
    return False


async def get_viewer_url(file_content: str) -> str:
    """POST the FamilyScript content to FamilyEcho and return the temporary viewer URL.

    The returned URL is valid for approximately 24 hours.
    Raises ValueError if the API returns an error response.
    Raises httpx.HTTPError on network failure.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            familyecho_api,
            data={'format': 'json', 'operation': 'temp_view', 'family': file_content},
        )
        resp.raise_for_status()
        body = resp.json()

    if 'error' in body:
        raise ValueError(f'FamilyEcho API error: {body["error"]}')
    if 'url' not in body:
        raise ValueError(f'unexpected FamilyEcho API response: {body!r}')

    return body['url']


async def get_family(guild_id: int, name: str) -> FamilyDocument | None:
    """Fetch a family by guild and name (case-insensitive)."""
    return await _get_repo().get(guild_id, name.strip().lower())


async def save_family(doc: FamilyDocument) -> None:
    """Persist a family record."""
    await _get_repo().upsert(doc)


async def list_families(guild_id: int) -> list[FamilyDocument]:
    """Return all registered families for a guild."""
    return await _get_repo().list_all(guild_id)
