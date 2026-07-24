# SPDX-License-Identifier: Apache-2.0
"""attu_server.api.admin.ping | GET /api/admin/ping - liveness probe for auth'd callers."""

from fastapi import APIRouter


router = APIRouter()


@router.get('/ping')
async def ping() -> dict:
    return {'ok': True}
