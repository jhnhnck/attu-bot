# SPDX-License-Identifier: Apache-2.0
"""attu_server.api.me | GET /api/me - auth + csrf + active guild snapshot."""

import secrets
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel


router = APIRouter()


class MeResponse(BaseModel):
    authenticated: bool
    csrf_token: str
    active_guild: int | None = None
    has_passkeys: bool = False


@router.get('/me', response_model=MeResponse)
async def me(request: Request) -> dict[str, Any]:
    """spa boot probe; later phases extend with user info + passkey count.

    sessions ride on starlette's signed-cookie SessionMiddleware. csrf_token is
    minted on first hit and persists for the session.
    """
    session = request.session
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)

    return {
        'authenticated': bool(session.get('user_id')),
        'csrf_token': session['csrf_token'],
        'active_guild': session.get('active_guild'),
        'has_passkeys': False,  # phase 2 wires the passkey lookup
    }
