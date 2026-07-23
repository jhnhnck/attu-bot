# SPDX-License-Identifier: Apache-2.0
"""nova_core.logging | logging utility."""

import logging
import re
import sys
from os import environ

import structlog


# --- Custom Levels ---

# trace and alert sit outside stdlib's standard levels.
# alert is below INFO so default-level filters drop it; both are also gated by the DEBUG env var.
TRACE = 5
ALERT = 15

logging.addLevelName(TRACE, 'TRACE')
logging.addLevelName(ALERT, 'ALERT')

_DEBUG_MODE = 'DEBUG' in environ

# LOG_LEVEL: optional override for the root logger level. accepts standard level names
# (DEBUG/INFO/WARNING/ERROR/CRITICAL) plus our customs (TRACE/ALERT). DEBUG=1 still takes
# precedence for the wrapper short-circuit on trace/debug/alert calls.
_LOG_LEVEL_ENV = environ.get('LOG_LEVEL', '').upper()

# LOG_FORMAT=json swaps the dev console renderer for a JSON renderer + iso timestamp.
# default stays ConsoleRenderer so `docker compose logs` is unchanged.
_LOG_FORMAT = environ.get('LOG_FORMAT', 'console').lower()


# --- Foreign-Record Processor (pycord rate-limit bucket) ---

_BUCKET_RE = re.compile(r'"([^"]*?):([^"]*?):(\/[^"]*?)"')
_PLACEHOLDER_RE = re.compile(r'/\{[^}]+\}')


def _resolve_pycord_bucket(_logger, _method_name, event_dict):
    """resolve pycord's rate-limit bucket "channel_id:guild_id:/route/{template}" into a real path.

    runs as a foreign_pre_chain processor so only stdlib-origin records (`discord.http`) pay the cost.
    """
    if event_dict.get('logger') != 'discord.http':
        return event_dict
    msg = event_dict.get('event')
    if not isinstance(msg, str):
        return event_dict
    m = _BUCKET_RE.search(msg)
    if m is None:
        return event_dict
    channel_id, guild_id, path = m.group(1), m.group(2), m.group(3)
    if channel_id != 'None':
        path = path.replace('{channel_id}', channel_id)
    if guild_id != 'None':
        path = path.replace('{guild_id}', guild_id)
    path = _PLACEHOLDER_RE.sub('', path)
    event_dict['event'] = msg[: m.start()] + f'"{path}"' + msg[m.end() :]
    return event_dict


# --- Renderer Setup ---


def _final_renderer():
    """choose the final renderer based on LOG_FORMAT.

    json: machine-readable for log shipping (BetterStack, etc.); adds an iso timestamp.
    console (default): colored dev output; preserves the original no-timestamp shape.
    """
    if _LOG_FORMAT == 'json':
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=True, force_colors=True)


def _resolve_root_level() -> int:
    """resolve the root logger level from LOG_LEVEL env, then DEBUG fallback, else INFO.

    accepts standard names plus our customs (TRACE, ALERT). unknown values fall through to INFO.
    """
    if _LOG_LEVEL_ENV:
        # logging.getLevelName returns the int for known names, else the string back
        resolved = logging.getLevelName(_LOG_LEVEL_ENV)
        if isinstance(resolved, int):
            return resolved
    return TRACE if _DEBUG_MODE else logging.INFO


def _build_formatter() -> logging.Formatter:
    """build the shared structlog formatter used by both stdout and stderr stdlib handlers"""
    foreign_pre_chain: list = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _resolve_pycord_bucket,
    ]
    if _LOG_FORMAT == 'json':
        foreign_pre_chain.append(structlog.processors.TimeStamper(fmt='iso'))

    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=foreign_pre_chain,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _final_renderer(),
        ],
    )


class _MaxLevelFilter(logging.Filter):
    """stdlib filter that admits only records strictly below the given level"""

    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self.max_level


def _configure() -> None:
    """one-shot stdlib + structlog config; idempotent across re-imports"""
    root = logging.getLogger()

    # idempotent: if our handlers are already attached, skip
    if any(getattr(h, '_nova_core_owned', False) for h in root.handlers):
        return

    formatter = _build_formatter()

    stdout_h = logging.StreamHandler(sys.stdout)
    stdout_h.setFormatter(formatter)
    stdout_h.addFilter(_MaxLevelFilter(logging.WARNING))
    stdout_h._nova_core_owned = True  # type: ignore[attr-defined]  # marker for idempotent re-imports

    stderr_h = logging.StreamHandler(sys.stderr)
    stderr_h.setFormatter(formatter)
    stderr_h.setLevel(logging.WARNING)
    stderr_h._nova_core_owned = True  # type: ignore[attr-defined]  # marker for idempotent re-imports

    root.addHandler(stdout_h)
    root.addHandler(stderr_h)
    root.setLevel(_resolve_root_level())

    # quiet noisy third-party loggers; opt back in by setting LOG_LEVEL=DEBUG (or below)
    # which the resolver applies to the root and these inherit unless we pin them here.
    for name in ('pymongo', 'aiohttp.access', 'discord.gateway'):
        logging.getLogger(name).setLevel(logging.WARNING)

    structlog_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if _LOG_FORMAT == 'json':
        structlog_processors.append(structlog.processors.TimeStamper(fmt='iso'))
    structlog_processors.append(structlog.stdlib.ProcessorFormatter.wrap_for_formatter)

    structlog.configure(
        processors=structlog_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


_configure()


# --- Wrapper ---


def _join(args: tuple[object, ...]) -> str:
    """mirror print(*obj, sep=' ') so vararg call sites keep working (e.g. logger.debug(*pages))"""
    if len(args) == 1:
        return str(args[0])
    return ' '.join(str(a) for a in args)


class AttubotLogger:
    """thin facade over structlog.stdlib.BoundLogger; preserves the legacy method names"""

    def __init__(self, name: str) -> None:
        self._name = name or 'nova_core.???'
        self._log = structlog.stdlib.get_logger(self._name)
        # stdlib reference for custom levels - structlog's BoundLogger.log() chokes on
        # levels outside its LEVEL_TO_NAME map. routing through stdlib still goes through
        # ProcessorFormatter's foreign_pre_chain, so rendering is unchanged.
        self._stdlib = logging.getLogger(self._name)

    def info(self, *args: object, **kw: object) -> None:
        self._log.info(_join(args), **kw)

    def warn(self, *args: object, **kw: object) -> None:
        self._log.warning(_join(args), **kw)

    # stdlib alias: callers that learned the name from python's logging module use `.warning`
    warning = warn

    def error(self, *args: object, **kw: object) -> None:
        self._log.error(_join(args), **kw)

    def fatal(self, *args: object, **kw: object) -> None:
        self._log.critical(_join(args), **kw)

    def debug(self, *args: object, **kw: object) -> None:
        if _DEBUG_MODE:
            self._log.debug(_join(args), **kw)

    def trace(self, *args: object, **kw: object) -> None:
        if _DEBUG_MODE:
            self._stdlib.log(TRACE, _join(args), **kw)

    def alert(self, *args: object, **kw: object) -> None:
        if _DEBUG_MODE:
            self._stdlib.log(ALERT, _join(args), **kw)

    async def send_to_webhook(self, error: Exception, location: str = '') -> None:
        from nova_core.webhook import send_to_webhook

        await send_to_webhook(error, location=location, logger_name=self._name)


# --- Pycord Bridge ---


class PycordBridgeHandler(logging.Handler):
    """marker handler kept for compatibility; routing happens via the dual root handlers in _configure().

    pycord's `discord.http` logger gets this attached in client._setup_discord_logging() so the
    bridge symbol stays addressable for tests; records still propagate to the root handlers
    (stdout < WARNING, stderr >= WARNING) via the standard stdlib propagation chain.
    """

    def emit(self, record: logging.LogRecord) -> None:
        pass


# --- Public API ---


# legacy alias kept for type-annotation call sites (e.g. client/util.py: webhook_logging(scope: Logger))
Logger = AttubotLogger


def get_logger(class_name: str) -> AttubotLogger:
    return AttubotLogger(class_name)
