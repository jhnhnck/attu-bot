# SPDX-License-Identifier: Apache-2.0
"""attu_server.api.admin | admin router; all routes require a valid bearer api key."""

from fastapi import APIRouter, Depends

from attu_server.api.admin.config_routes import router as config_router
from attu_server.api.admin.guilds import router as guilds_router
from attu_server.api.admin.ping import router as ping_router
from attu_server.deps import require_api_key


router = APIRouter(prefix='/admin', dependencies=[Depends(require_api_key)])
router.include_router(ping_router)
router.include_router(guilds_router)
router.include_router(config_router)
