# SPDX-License-Identifier: Apache-2.0
"""attu_server.main | fastapi app factory + lifespan + middleware."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware

from attu_models.connection import MongoStorage
from attu_server import __version__
from attu_server.api.admin import router as admin_router
from attu_server.bridge_client import BridgeClient
from attu_server.config import ServerConfig, load_config
from attu_server.preflight import check_schema


logger = logging.getLogger('attu_server')


def _build_lifespan(cfg: ServerConfig):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        storage = MongoStorage()
        await storage.connect(cfg.database.url, cfg.database.name)

        # belt-and-braces; compose's healthcheck-gated depends_on is the primary gate
        await check_schema(storage)

        bridge = BridgeClient(cfg.bridge)

        app.state.config = cfg
        app.state.storage = storage
        app.state.bridge = bridge

        logger.info('attu_server startup complete')
        try:
            yield
        finally:
            await bridge.aclose()
            await storage.close()
            logger.info('attu_server shutdown complete')

    return lifespan


def create_app(cfg: ServerConfig | None = None) -> FastAPI:
    cfg = cfg or load_config()
    app = FastAPI(title='attu_server', version=__version__, lifespan=_build_lifespan(cfg))

    app.add_middleware(GZipMiddleware, minimum_size=1024)

    app.include_router(admin_router, prefix='/api')

    @app.get('/health')
    async def health() -> dict[str, Any]:
        return {'status': 'ok', 'version': __version__}

    return app


app = create_app()
