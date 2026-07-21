# SPDX-License-Identifier: Apache-2.0
"""attu_server.main | fastapi app factory + lifespan + middleware."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from attu_models.connection import MongoStorage
from attu_server import __version__, webauthn_store
from attu_server.api.me import router as me_router
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
        await webauthn_store.ensure_indexes(storage)

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

    # session signing reuses the legacy quart secret_key so existing cookies
    # survive the cutover. csrf is enforced per-request in deps.require_csrf
    # (added in phase 3 with the first write endpoint).
    app.add_middleware(SessionMiddleware, secret_key=cfg.web.secret_key, session_cookie='attu_session', https_only=False)
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    app.include_router(me_router, prefix='/api')

    @app.get('/health')
    async def health() -> dict[str, Any]:
        return {'status': 'ok', 'version': __version__}

    return app


app = create_app()
