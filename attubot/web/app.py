"""
AttuBot - Main Quart Application
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import secrets
from datetime import datetime, timedelta
from pathlib import Path

from quart import Quart, g

from attubot import config
from attubot.logging import get_logger

logger = get_logger(__name__)

# Initialize audit logger (will be set up after DB connection)
audit_logger = None


def create_app() -> Quart:
    """Application factory for Quart app"""

    # Load config file synchronously — needed before building the app so that
    # assets path and secret key are available at construction time.
    # Skipped if already initialized (e.g. in tests where config is set up manually).
    if not config._get_event('init').is_set():
        config.on_init()

    _assets_dir = Path(config.paths.assets).resolve()
    app = Quart(
        __name__,
        template_folder=str(_assets_dir / 'templates'),
        static_folder=str(_assets_dir / 'static'),
    )

    @app.before_serving
    async def startup():
        """Initialize configuration before starting the web server"""
        global audit_logger  # noqa: PLW0603

        try:
            from attubot.logo import generate_png
            from attubot.web.audit import AuditLogger

            logger.info('Connecting to database and initializing repositories...')
            from attubot.database import init_database

            await init_database(config.database.url, config.database.name)

            logger.info('Loading configuration from database...')
            config.web_mode = True
            await config.on_load()

            logger.info('Configuration loaded successfully')

            logger.info('Generating favicon...')
            static_dir = _assets_dir / 'static' / 'img'
            favicon_path = static_dir / 'favicon.png'
            import anyio

            await anyio.Path(static_dir).mkdir(parents=True, exist_ok=True)

            theme = config.theme
            rotation = theme.rotation if theme else 0.0
            bot_color = theme.bot_color if theme else '#ff0000'

            try:
                favicon_png = await generate_png(rotation, bot_color, foreground='#000000', height=256, width=256)
                await anyio.Path(favicon_path).write_bytes(favicon_png)
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

            # Fetch guild names and perform post-ready setup
            logger.info('Running post-ready config setup...')
            await config.on_ready()

            # Initialize audit logger
            logger.info('Initializing audit logger...')
            from attubot import db

            audit_logger = AuditLogger(db.get_db())
            logger.info('Audit logger initialized')

        except Exception as err:
            logger.fatal(f'Failed to initialize: {err}')
            raise err

    app.config['SECRET_KEY'] = config.web.secret_key
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max upload
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)  # Session lasts 30 days

    # Jinja2 filter: format a Unix timestamp as a human-readable date
    @app.template_filter('timestamp_to_date')
    def timestamp_to_date_filter(ts):
        try:
            return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M')
        except Exception:
            return 'Unknown'

    # generate a fresh nonce for every request; stored on g so the CSP header and templates agree
    @app.before_request
    async def set_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    # Security headers
    @app.after_request
    async def set_security_headers(response):
        nonce = getattr(g, 'csp_nonce', '')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # Content-Security-Policy (L2)
        # 'unsafe-inline' is kept for style-src only (inline <style> in base.html navbar theme).
        # script-src uses a per-request nonce for inline <script> blocks; no 'unsafe-inline'.
        # script-src-attr is relaxed to 'unsafe-inline' because dynamically generated rows
        # inject onclick= attributes with runtime values (year ids, field names, credential ids)
        # that cannot be hashed. inline event handlers are lower-risk than injected <script> blocks.
        response.headers['Content-Security-Policy'] = (
            f"default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'nonce-{nonce}'; script-src-attr 'unsafe-inline'; style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data:; font-src 'self' https://cdn.jsdelivr.net; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    # CSRF token and CSP nonce available in all templates (L3)
    @app.context_processor
    async def inject_csrf():
        from attubot.web.auth import get_csrf_token

        try:
            nonce = getattr(g, 'csp_nonce', '')
            return {'csrf_token': get_csrf_token(), 'csp_nonce': nonce}
        except Exception:
            return {'csrf_token': '', 'csp_nonce': ''}

    # Rate limiting (L4) — must be registered before routes
    from quart_rate_limiter import RateLimit, RateLimiter, rate_limit  # noqa: F401 (re-exported for auth.py)

    RateLimiter(app, default_limits=[RateLimit(60, timedelta(minutes=1))])

    # Register auth routes first (installs the before_request guard + per-endpoint rate limits)
    from attubot.web.auth import register_auth_routes

    register_auth_routes(app)

    # Register application routes
    from attubot.web.routes import register_routes

    register_routes(app)

    logger.info('Quart application initialized')

    return app


def start_web():
    """Start the web interface — mirrors core.start_bot_loop()"""
    logger.info('Starting AttuBot Web Interface!')
    config.on_init()

    logger.info('Starting Web Server')
    app = create_app()
    app.run(
        host='0.0.0.0',  # noqa: S104
        port=5000,
        debug=False,
        use_reloader=False,
    )
