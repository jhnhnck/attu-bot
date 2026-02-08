#!/usr/bin/env python3
"""
AttuBot - SQLite to MongoDB Migration Script
Author(s): @jhnhnck <john@jhnhnck.com>

This script migrates data from the old SQLite/Tortoise ORM database
to the new MongoDB/pymongo database.

Usage:
    python scripts/migrate_to_mongodb.py [--sqlite-path PATH] [--dry-run]

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import argparse
import asyncio

# Setup logging
import logging
import sqlite3
from os import getenv
from pathlib import Path

from pymongo import AsyncMongoClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


class Migration:
    def __init__(self, sqlite_path: str, mongodb_url: str, mongodb_db: str, dry_run: bool = False):
        self.sqlite_path = Path(sqlite_path)
        self.mongodb_url = mongodb_url
        self.mongodb_db_name = mongodb_db
        self.dry_run = dry_run

        self.sqlite_conn = None
        self.mongo_client = None
        self.mongo_db = None

        # Migration stats
        self.stats = {
            'guilds': 0,
            'markers': 0,
            'theme': 0,
            'system': 0,
            'errors': 0,
        }

    async def connect(self):
        """Connect to both databases"""
        logger.info(f'Connecting to SQLite database: {self.sqlite_path}')
        if not self.sqlite_path.exists():
            raise FileNotFoundError(f'SQLite database not found: {self.sqlite_path}')

        self.sqlite_conn = sqlite3.connect(self.sqlite_path)
        self.sqlite_conn.row_factory = sqlite3.Row

        logger.info(f'Connecting to MongoDB: {self.mongodb_url}')
        self.mongo_client = AsyncMongoClient(self.mongodb_url)
        self.mongo_db = self.mongo_client[self.mongodb_db_name]

        # Test connection
        await self.mongo_db.command('ping')
        logger.info('Connected to both databases successfully')

    async def close(self):
        """Close database connections"""
        if self.sqlite_conn:
            self.sqlite_conn.close()

        if self.mongo_client:
            await self.mongo_client.close()

    def get_tokens_for_guild(self, guild_id: int) -> dict:
        """Get all NovaToken entries for a specific guild"""
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            'SELECT key, value FROM novatoken WHERE key LIKE ?',
            (f'{guild_id}.%',),
        )

        tokens = {}
        for row in cursor.fetchall():
            key = row['key'].replace(f'{guild_id}.', '', 1)  # Remove guild prefix
            tokens[key] = row['value']

        return tokens

    def get_global_tokens(self) -> dict:
        """Get all global NovaToken entries"""
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            "SELECT key, value FROM novatoken WHERE key NOT LIKE '%._' AND key NOT LIKE '%.%'",
        )

        tokens = {}
        for row in cursor.fetchall():
            tokens[row['key']] = row['value']

        return tokens

    def parse_tokens_to_guild_config(self, guild_id: int, tokens: dict) -> dict:
        """Parse NovaToken entries into guild config structure"""

        def get_int(key: str, default: int = 0) -> int:
            return int(tokens.get(key, default))

        def get_bool(key: str, default: bool = False) -> bool:
            val = tokens.get(key)
            if val is None:
                return default
            return val.lower() in ('true', '1', 'yes')

        def get_list(key: str) -> list:
            val = tokens.get(key, '')
            if not val:
                return []
            # Handle JSON array or comma-separated
            if val.startswith('['):
                import json
                return json.loads(val)
            return [int(x.strip()) for x in val.split(',') if x.strip()]

        # Parse rollover_time to minutes
        rollover_time_str = tokens.get('epoch.rollover_time', '17:00')
        if ':' in rollover_time_str:
            h, m = rollover_time_str.split(':')
            rollover_minutes = int(h) * 60 + int(m)
        else:
            rollover_minutes = 1020  # Default 17:00

        return {
            'guild_id': guild_id,
            'channels': {
                'activity': get_int('channels.activity'),
                'year_vc': get_int('channels.year_vc'),
                'announcements': get_int('channels.announcements'),
                'year_links': get_int('channels.year_links'),
                'meta_chat': get_int('channels.meta_chat'),
                'lore_channels': get_list('channels.lore_channels'),
            },
            'epoch': {
                'time': get_int('epoch.time'),
                'year': get_int('epoch.year', 1),
                'length': get_int('epoch.length', 14),
                'paused': get_bool('epoch.paused', True),
                'rollover_minutes': rollover_minutes,
            },
            'roles': {
                'announcements': get_int('roles.announcements'),
            },
            'users': {
                'markers': get_list('users.markers'),
            },
        }

    async def migrate_guild_configs(self):
        """Migrate guild configurations from NovaToken to MongoDB"""
        logger.info('Migrating guild configurations...')

        # Get list of all guild IDs from tokens
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            "SELECT DISTINCT CAST(SUBSTR(key, 1, INSTR(key, '.') - 1) AS INTEGER) as guild_id "
            "FROM novatoken WHERE key LIKE '%.%' AND SUBSTR(key, 1, INSTR(key, '.') - 1) GLOB '[0-9]*'",
        )

        guild_ids = [row['guild_id'] for row in cursor.fetchall()]
        logger.info(f'Found {len(guild_ids)} guilds to migrate')

        for guild_id in guild_ids:
            try:
                tokens = self.get_tokens_for_guild(guild_id)
                if not tokens:
                    logger.warning(f'No tokens found for guild {guild_id}, skipping')
                    continue

                config = self.parse_tokens_to_guild_config(guild_id, tokens)

                if self.dry_run:
                    logger.info(f'[DRY RUN] Would migrate guild {guild_id}: {config}')
                else:
                    await self.mongo_db['guild_configs'].update_one(
                        {'guild_id': guild_id},
                        {'$set': config},
                        upsert=True,
                    )
                    logger.info(f'Migrated guild {guild_id}')

                self.stats['guilds'] += 1

            except Exception as e:
                logger.error(f'Error migrating guild {guild_id}: {e}')
                self.stats['errors'] += 1

    async def migrate_theme(self):
        """Migrate theme configuration from NovaToken to MongoDB"""
        logger.info('Migrating theme configuration...')

        try:
            tokens = self.get_global_tokens()

            theme = {
                'config_type': 'theme',
                'rotation': float(tokens.get('theme.rotation', 0.0)),
                'max_rate': float(tokens.get('theme.max_rate', 0.5)),
                'bot_color': tokens.get('theme.bot_color', '#ff0000'),
                'guild_color': tokens.get('theme.guild_color', '#ffffff'),
            }

            if self.dry_run:
                logger.info(f'[DRY RUN] Would migrate theme: {theme}')
            else:
                await self.mongo_db['global_config'].update_one(
                    {'config_type': 'theme'},
                    {'$set': theme},
                    upsert=True,
                )
                logger.info('Migrated theme configuration')

            self.stats['theme'] = 1

        except Exception as e:
            logger.error(f'Error migrating theme: {e}')
            self.stats['errors'] += 1

    async def migrate_system_config(self, config_version: str = '3.0.0'):
        """Migrate system configuration from NovaToken to MongoDB"""
        logger.info('Migrating system configuration...')

        try:
            tokens = self.get_global_tokens()

            # Parse error_log
            error_log_str = tokens.get('error_log', '0,0')
            error_log = [int(x.strip()) for x in error_log_str.split(',')]
            if len(error_log) != 2:
                error_log = [0, 0]

            system = {
                'config_type': 'system',
                'version': config_version,
                'error_log': error_log,
                'error_hook': tokens.get('error_hook', ''),
                'primary_guild': int(tokens.get('primary_guild', 0)),
            }

            if self.dry_run:
                logger.info(f'[DRY RUN] Would migrate system config: {system}')
            else:
                await self.mongo_db['global_config'].update_one(
                    {'config_type': 'system'},
                    {'$set': system},
                    upsert=True,
                )
                logger.info('Migrated system configuration')

            self.stats['system'] = 1

        except Exception as e:
            logger.error(f'Error migrating system config: {e}')
            self.stats['errors'] += 1

    async def migrate_year_markers(self):
        """Migrate year markers from Tortoise ORM table to MongoDB"""
        logger.info('Migrating year markers...')

        try:
            cursor = self.sqlite_conn.cursor()
            cursor.execute('SELECT channel, message, year, exact, wiki_page FROM yearmarker')

            markers = []
            for row in cursor.fetchall():
                marker = {
                    'channel': row['channel'],
                    'message': row['message'],
                    'year': row['year'],
                    'exact': bool(row['exact']),
                    'wiki_page': bool(row['wiki_page']),
                }
                markers.append(marker)

            logger.info(f'Found {len(markers)} year markers to migrate')

            if markers:
                if self.dry_run:
                    logger.info(f'[DRY RUN] Would migrate {len(markers)} markers')
                    for marker in markers[:5]:  # Show first 5 as example
                        logger.info(f'  Example marker: {marker}')
                else:
                    # Clear existing markers first
                    await self.mongo_db['year_markers'].delete_many({})

                    # Insert all markers
                    await self.mongo_db['year_markers'].insert_many(markers)
                    logger.info(f'Migrated {len(markers)} year markers')

                self.stats['markers'] = len(markers)

        except Exception as e:
            logger.error(f'Error migrating year markers: {e}')
            self.stats['errors'] += 1

    async def create_indexes(self):
        """Create MongoDB indexes"""
        if self.dry_run:
            logger.info('[DRY RUN] Would create indexes')
            return

        logger.info('Creating MongoDB indexes...')

        # Guild configs index
        await self.mongo_db['guild_configs'].create_index('guild_id', unique=True)

        # Global config index
        await self.mongo_db['global_config'].create_index('config_type', unique=True)

        # Year markers indexes
        await self.mongo_db['year_markers'].create_index(
            [('channel', 1), ('year', 1)],
            unique=True,
        )
        await self.mongo_db['year_markers'].create_index('channel')

        logger.info('Created indexes successfully')

    async def run(self):
        """Run the full migration"""
        try:
            await self.connect()

            logger.info('='*60)
            logger.info(f"Starting migration {'(DRY RUN)' if self.dry_run else ''}")
            logger.info('='*60)

            await self.migrate_guild_configs()
            await self.migrate_theme()
            await self.migrate_system_config()
            await self.migrate_year_markers()
            await self.create_indexes()

            logger.info('='*60)
            logger.info('Migration complete!')
            logger.info(f"  Guilds migrated: {self.stats['guilds']}")
            logger.info(f"  Markers migrated: {self.stats['markers']}")
            logger.info(f"  Theme migrated: {self.stats['theme']}")
            logger.info(f"  System config migrated: {self.stats['system']}")
            logger.info(f"  Errors: {self.stats['errors']}")
            logger.info('='*60)

            if self.dry_run:
                logger.info('This was a dry run - no changes were made to MongoDB')

        finally:
            await self.close()


async def main():
    parser = argparse.ArgumentParser(description='Migrate AttuBot from SQLite to MongoDB')
    parser.add_argument(
        '--sqlite-path',
        default='./data/attu-bot.db',
        help='Path to SQLite database file (default: ./data/attu-bot.db)',
    )
    parser.add_argument(
        '--mongodb-url',
        default=None,
        help='MongoDB connection URL (default: from MONGODB_URL env var or mongodb://localhost:27017)',
    )
    parser.add_argument(
        '--mongodb-db',
        default=None,
        help='MongoDB database name (default: from MONGODB_DATABASE env var or doombot)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without making changes to MongoDB',
    )

    args = parser.parse_args()

    # Get MongoDB settings from env or args
    mongodb_url = args.mongodb_url or getenv('MONGODB_URL', 'mongodb://localhost:27017')
    mongodb_db = args.mongodb_db or getenv('MONGODB_DATABASE', 'doombot')

    migration = Migration(
        sqlite_path=args.sqlite_path,
        mongodb_url=mongodb_url,
        mongodb_db=mongodb_db,
        dry_run=args.dry_run,
    )

    await migration.run()


if __name__ == '__main__':
    asyncio.run(main())
