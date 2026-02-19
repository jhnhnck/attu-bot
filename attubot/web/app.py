"""
AttuBot - Main Quart Application
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import os
from pathlib import Path

from quart import Quart

from attubot.config import NovaConfig
from attubot.logging import get_logger

logger = get_logger(__name__)

# Initialize config
config = NovaConfig()

# Initialize audit logger (will be set up after DB connection)
audit_logger = None


def create_app() -> Quart:
    """Application factory for Quart app"""

    # Create Quart app
    app = Quart(
        __name__,
        template_folder=str(Path(__file__).parent / 'templates'),
        static_folder=str(Path(__file__).parent / 'static'),
    )

    @app.before_serving
    async def startup():
        """Initialize configuration before starting the web server"""
        try:
            from attubot.logo import generate_png
            from attubot.web.audit import AuditLogger

            logger.info('Initializing configuration...')
            config.on_init()

            logger.info('Connecting to database...')
            await config.on_load()

            logger.info('Configuration loaded successfully')

            logger.info('Generating favicon...')
            static_dir = Path(__file__).parent / 'static' / 'img'
            favicon_path = static_dir / 'favicon.png'
            static_dir.mkdir(parents=True, exist_ok=True)

            theme = config.theme
            rotation = theme.rotation if theme else 0.0
            bot_color = theme.bot_color if theme else '#ff0000'

            try:
                favicon_png = await generate_png(rotation, bot_color, foreground='#000000', height=256, width=256)
                favicon_path.write_bytes(favicon_png)
                logger.info(f'Favicon generated at {favicon_path}')
            except PermissionError as err:
                logger.error(f'Unable to write favicon at {favicon_path}: {err}')
            except Exception as err:
                logger.error(f'Favicon generation failed: {err}')

            # Initialize Discord bot (REST only)
            logger.info('Initializing Discord API connection...')
            from attubot import bot
            await bot.login(config.bot_token)
            logger.info(f'Logged into Discord as {bot.user}')

            # Initialize audit logger
            logger.info('Initializing audit logger...')
            from attubot import db
            global audit_logger  # noqa: PLW0603
            audit_logger = AuditLogger(db.get_db())
            logger.info('Audit logger initialized')

        except Exception as err:
            logger.fatal(f'Failed to initialize: {err}')
            raise err

    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

    # Security headers
    @app.after_request
    async def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    # Register routes
    from attubot.web.routes import register_routes
    register_routes(app)

    logger.info('Quart application initialized')

    return app
