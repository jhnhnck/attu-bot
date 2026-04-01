"""
AttuBot - Main Quart Application
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import secrets
from datetime import datetime, timedelta
from pathlib import Path

from quart import Quart, g

from attubot.client.core import config, db
from attubot.logging import get_logger
from attubot.web.audit import AuditLogger


logger = get_logger(__name__)

# Initialize audit logger (will be set up after DB connection)
audit_logger: AuditLogger | None = None


def _ensure_config() -> None:
    if not config._get_event('init').is_set():
        config.on_init()


def _build_quart_app(assets_dir: Path) -> Quart:
    return Quart(
        __name__,
        template_folder=str(assets_dir / 'templates'),
        static_folder=str(assets_dir / 'static'),
    )


def _configure_app(app: Quart) -> None:
    app.config['SECRET_KEY'] = config.web.secret_key
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max upload
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=14)
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'


def _register_startup(app: Quart, assets_dir: Path) -> None:
    @app.before_serving
    async def startup() -> None:
        """Initialize configuration before starting the web server"""

        try:
            audit_logger_value = await _initialize_startup(assets_dir)
            globals()['audit_logger'] = audit_logger_value
        except Exception as err:
            logger.fatal(f'failed to initialize: {err}')
            raise err

    @app.after_serving
    async def shutdown() -> None:
        """clean up connections on container stop (SIGTERM)"""
        logger.info('web server shutting down')

        if db.client:
            await db.client.close()

        from attubot import bot as discord_bot

        if not discord_bot.is_closed():
            await discord_bot.close()


async def _initialize_startup(assets_dir: Path):
    from attubot.client.logo import generate_png
    from attubot.web.audit import AuditLogger

    logger.info('connecting to database and initializing repositories')
    from attubot.database import init_database

    await init_database(config.database.url, config.database.name)

    logger.info('loading configuration from database')
    config.web_mode = True
    await config.on_load()

    logger.info('configuration loaded')

    logger.info('generating favicon')
    static_dir = assets_dir / 'static' / 'img'
    favicon_path = static_dir / 'favicon.png'
    import anyio

    await anyio.Path(static_dir).mkdir(parents=True, exist_ok=True)

    theme = config.theme
    rotation = theme.rotation if theme else 0.0
    bot_color = theme.bot_color if theme else '#ff0000'
    logo_rings = theme.logo_rings if theme else '#000000'
    logo_planet = theme.logo_planet if theme else '#000000'

    try:
        favicon_png = await generate_png(rotation, bot_color, logo_rings, logo_planet, height=256, width=256)
        await anyio.Path(favicon_path).write_bytes(favicon_png)
        logger.info(f'favicon generated at {favicon_path}')
    except PermissionError as err:
        logger.error(f'unable to write favicon at {favicon_path}: {err}')
    except Exception as err:
        logger.error(f'favicon generation failed: {err}')

    logger.info('initializing discord api connection')
    from attubot import bot

    await bot.login(config.bot_token)
    logger.info(f'logged into discord as {bot.user}')

    logger.info('running post-ready config setup')
    await config.on_ready()

    logger.info('initializing audit logger')
    audit_logger = AuditLogger(db.get_db())
    logger.info('audit logger initialized')
    return audit_logger


def _register_template_hooks(app: Quart) -> None:
    @app.template_filter('timestamp_to_date')
    def timestamp_to_date_filter(ts):
        try:
            return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M')
        except Exception:
            return 'Unknown'

    @app.before_request
    async def set_csp_nonce() -> None:
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.after_request
    async def set_security_headers(response):
        nonce = getattr(g, 'csp_nonce', '')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = (
            f"default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'nonce-{nonce}'; script-src-attr 'unsafe-inline'; style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data:; font-src 'self' https://cdn.jsdelivr.net; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.context_processor
    async def inject_csrf():
        from attubot.web.auth import get_csrf_token

        try:
            nonce = getattr(g, 'csp_nonce', '')
            return {'csrf_token': get_csrf_token(), 'csp_nonce': nonce}
        except Exception:
            return {'csrf_token': '', 'csp_nonce': ''}


def _register_rate_limits_and_routes(app: Quart) -> None:
    from quart_rate_limiter import RateLimit, RateLimiter

    RateLimiter(app, default_limits=[RateLimit(60, timedelta(minutes=1))])

    from attubot.web.auth import register_auth_routes

    register_auth_routes(app)

    from attubot.web.routes import register_routes

    register_routes(app)


def create_app() -> Quart:
    """Application factory for Quart app"""

    _ensure_config()
    assets_dir = Path(config.paths.assets).resolve()
    app = _build_quart_app(assets_dir)

    _register_startup(app, assets_dir)
    _register_template_hooks(app)
    _register_rate_limits_and_routes(app)
    _configure_app(app)

    logger.info('quart application initialized')

    return app


def start_web():
    """Start the web interface — mirrors core.start_bot_loop()"""
    logger.info('starting attubot web interface')
    config.on_init()

    logger.info('starting web server')
    app = create_app()
    app.run(
        host='0.0.0.0',  # noqa: S104 - listening on all interfaces is intentional inside the container
        port=5000,
        debug=False,
        use_reloader=False,
    )
