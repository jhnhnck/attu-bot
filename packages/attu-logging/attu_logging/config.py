# SPDX-License-Identifier: Apache-2.0
"""attu_logging.config | one-shot stdlib + structlog configuration."""

import logging
import re
import sys
from os import environ

import structlog


# --- foreign-record processor (pycord rate-limit bucket) ---

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


# --- renderer / level helpers ---


def _final_renderer(log_format: str):
    """choose the final renderer based on LOG_FORMAT.

    json: machine-readable for log shipping; adds an iso timestamp via the foreign chain.
    console (default): colored dev output; preserves the original no-timestamp shape.
    """
    if log_format == 'json':
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=True, force_colors=True)


def _resolve_root_level(level_override: str | None) -> int:
    """resolve the root logger level from LOG_LEVEL env (or override), defaulting to INFO."""
    if level_override:
        resolved = logging.getLevelName(level_override.upper())
        if isinstance(resolved, int):
            return resolved
    return logging.INFO


def _build_formatter(log_format: str) -> logging.Formatter:
    """build the shared structlog formatter used by both stdout and stderr stdlib handlers."""
    foreign_pre_chain: list = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _resolve_pycord_bucket,
    ]
    if log_format == 'json':
        foreign_pre_chain.append(structlog.processors.TimeStamper(fmt='iso'))

    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=foreign_pre_chain,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _final_renderer(log_format),
        ],
    )


class _MaxLevelFilter(logging.Filter):
    """stdlib filter that admits only records strictly below the given level."""

    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self.max_level


# --- module-level webhook url store ---

# mutable container avoids `global` while still allowing post-configure mutation.
# read lazily by attu_logging.webhook at call time so startup-vs-on_load timing is handled.
_state: dict[str, str | None] = {'webhook_url': None}


def _get_webhook_url() -> str | None:
    return _state['webhook_url']


# --- public api ---


def set_webhook_url(url: str) -> None:
    """set the discord error webhook url independently of the idempotent configure guard.

    call this from on_load() after config.error_hook is available. configure() runs at
    startup before the url is known, so this function bridges the timing gap.
    """
    _state['webhook_url'] = url


def configure(*, json: bool | None = None, level: str | None = None, webhook_url: str | None = None) -> None:
    """one-shot stdlib + structlog config; idempotent across re-imports and re-calls.

    args:
        json: force json renderer (true) or console renderer (false). defaults to the
              LOG_FORMAT env var (`json` enables; anything else is console).
        level: root logger level override. defaults to the LOG_LEVEL env var, then INFO.
        webhook_url: optional discord error webhook url. if provided, stored for later use by
                     attu_logging.webhook. prefer set_webhook_url() when the url is not
                     available at startup time.
    """
    if webhook_url is not None:
        _state['webhook_url'] = webhook_url

    root = logging.getLogger()

    # idempotent: skip if either marker is already attached. the `_nova_core_owned`
    # check provides backward compatibility for any process that still imports a legacy
    # nova_core logging setup alongside attu_logging.
    if any(getattr(h, '_attu_owned', False) or getattr(h, '_nova_core_owned', False) for h in root.handlers):
        return

    log_format = ('json' if json else 'console') if json is not None else environ.get('LOG_FORMAT', 'console').lower()
    level_override = level if level is not None else environ.get('LOG_LEVEL', '') or None

    formatter = _build_formatter(log_format)

    stdout_h = logging.StreamHandler(sys.stdout)
    stdout_h.setFormatter(formatter)
    stdout_h.addFilter(_MaxLevelFilter(logging.WARNING))
    stdout_h._attu_owned = True  # type: ignore[attr-defined]  # marker for idempotent re-imports
    stdout_h._nova_core_owned = True  # type: ignore[attr-defined]  # cross-package marker for dual-consumer compatibility

    stderr_h = logging.StreamHandler(sys.stderr)
    stderr_h.setFormatter(formatter)
    stderr_h.setLevel(logging.WARNING)
    stderr_h._attu_owned = True  # type: ignore[attr-defined]  # marker for idempotent re-imports
    stderr_h._nova_core_owned = True  # type: ignore[attr-defined]  # cross-package marker for dual-consumer compatibility

    root.addHandler(stdout_h)
    root.addHandler(stderr_h)
    root.setLevel(_resolve_root_level(level_override))

    # quiet noisy third-party loggers; opt back in by setting LOG_LEVEL=DEBUG (or below)
    # which the resolver applies to the root and these inherit unless we pin them here.
    for name in ('pymongo', 'aiohttp.access', 'discord.gateway'):
        logging.getLogger(name).setLevel(logging.WARNING)

    # discord.http: WARNING by default keeps rate-limit warnings visible while
    # suppressing per-request DEBUG noise; DEBUG=1 opts back into the verbose http traces.
    logging.getLogger('discord.http').setLevel(logging.DEBUG if 'DEBUG' in environ else logging.WARNING)

    structlog_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if log_format == 'json':
        structlog_processors.append(structlog.processors.TimeStamper(fmt='iso'))
    structlog_processors.append(structlog.stdlib.ProcessorFormatter.wrap_for_formatter)

    structlog.configure(
        processors=structlog_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
