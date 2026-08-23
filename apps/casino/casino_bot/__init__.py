# SPDX-License-Identifier: Apache-2.0
"""casino_bot | walking skeleton — discord event loop with mongo and feature loader stub."""

from os import getenv
from pathlib import Path

import discord
import structlog
import tomlkit

from attu_models import MongoStorage


logger = structlog.stdlib.get_logger(__name__)

_db = MongoStorage()


def _load_features(bot: discord.Bot, features: list) -> None:
    logger.info(f'feature loader: {len(features)} features configured (stub)')


def start_casino_loop() -> None:
    config_path = Path(getenv('CASINO_CONFIG_FILE', 'apps/casino/casino.toml')).resolve()
    logger.info(f'loading config from "{config_path}"')

    with config_path.open() as f:
        raw_config = tomlkit.load(f)

    mongo_uri: str = raw_config['mongo']['uri']
    mongo_name: str = raw_config['mongo'].get('name', 'casino')
    bot_token: str = raw_config['bot']['token']
    features_enabled: list = list(raw_config.get('features', {}).get('enabled', []))

    intents = discord.Intents.default()
    bot = discord.Bot(intents=intents)

    @bot.event
    async def on_ready() -> None:
        await _db.connect(mongo_uri, mongo_name)
        _load_features(bot, features_enabled)
        logger.info('casino ready')

    logger.info('starting casino bot')
    bot.run(bot_token)
