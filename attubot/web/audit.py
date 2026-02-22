"""
AttuBot - Audit Logging
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase
from quart import request

from attubot.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ConfigChange:
    """Represents a single field change"""
    field: str
    old_value: Any
    new_value: Any


@dataclass
class AuditLogEntry:
    """Represents an audit log entry"""
    timestamp: int
    ip_address: str
    config_type: str  # "guild" | "theme" | "system"
    action: str  # "create" | "update" | "delete"
    changes: list[ConfigChange]
    guild_id: int | None = None
    user_id: int | None = None  # For future authentication
    success: bool = True
    error_message: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for MongoDB storage"""
        return {
            'timestamp': self.timestamp,
            'ip_address': self.ip_address,
            'config_type': self.config_type,
            'action': self.action,
            'guild_id': self.guild_id,
            'user_id': self.user_id,
            'success': self.success,
            'error_message': self.error_message,
            'changes': [
                {
                    'field': change.field,
                    'old_value': change.old_value,
                    'new_value': change.new_value,
                }
                for change in self.changes
            ],
        }


class AuditLogger:
    """Handles audit logging for configuration changes"""

    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.collection = db.config_audit_log

    async def log_change(
        self,
        config_type: str,
        action: str,
        changes: list[ConfigChange],
        ip_address: str,
        guild_id: int | None = None,
        user_id: int | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """
        Log a configuration change to the audit log.

        Args:
            config_type: Type of config ("guild", "theme", "system")
            action: Action performed ("create", "update", "delete")
            changes: List of ConfigChange objects
            ip_address: IP address of the requester
            guild_id: Guild ID for guild configs
            user_id: User ID (for future authentication)
            success: Whether the change was successful
            error_message: Error message if failed
        """
        try:
            entry = AuditLogEntry(
                timestamp=int(datetime.now().timestamp()),
                ip_address=ip_address,
                config_type=config_type,
                action=action,
                changes=changes,
                guild_id=guild_id,
                user_id=user_id,
                success=success,
                error_message=error_message,
            )

            await self.collection.insert_one(entry.to_dict())

            logger.info(
                f'Audit log: {config_type} {action} by {ip_address}'
                + (f' for guild {guild_id}' if guild_id else '')
                + f' - {len(changes)} changes',
            )

        except Exception as e:
            # Don't let audit logging failures break the application
            logger.error(f'Failed to write audit log: {e}')

    async def get_logs(
        self,
        config_type: str | None = None,
        guild_id: int | None = None,
        user_id: int | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> list[dict]:
        """
        Retrieve audit logs with optional filtering.

        Args:
            config_type: Filter by config type
            guild_id: Filter by guild ID
            user_id: Filter by user ID
            limit: Maximum number of logs to return
            skip: Number of logs to skip (pagination)

        Returns:
            List of audit log entries
        """
        query = {}

        if config_type:
            query['config_type'] = config_type

        if guild_id is not None:
            query['guild_id'] = guild_id

        if user_id is not None:
            query['user_id'] = user_id

        cursor = self.collection.find(query).sort('timestamp', -1).skip(skip).limit(limit)
        logs = await cursor.to_list(length=limit)

        return logs

    async def get_guild_history(self, guild_id: int, limit: int = 50) -> list[dict]:
        """Get change history for a specific guild"""
        return await self.get_logs(config_type='guild', guild_id=guild_id, limit=limit)

    async def get_recent_changes(self, limit: int = 50) -> list[dict]:
        """Get most recent changes across all configs"""
        return await self.get_logs(limit=limit)


def get_client_ip() -> str:
    """Return the real client IP, honouring reverse-proxy headers.

    Safe to call unconditionally: the web port is bound to 127.0.0.1:5000,
    so only a local reverse proxy can reach Quart and external clients cannot
    forge X-Forwarded-For directly.
    """
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # Leftmost entry is the original client
        return forwarded_for.split(',')[0].strip()
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()
    return request.remote_addr or 'unknown'


def compare_configs(old: dict, new: dict, prefix: str = '') -> list[ConfigChange]:
    """
    Compare two configuration dictionaries and return list of changes.

    Args:
        old: Old configuration dictionary
        new: New configuration dictionary
        prefix: Prefix for nested keys (used in recursion)

    Returns:
        List of ConfigChange objects
    """
    changes = []

    # Check all keys in new config
    all_keys = set(old.keys()) | set(new.keys())

    for key in all_keys:
        full_key = f'{prefix}.{key}' if prefix else key

        old_val = old.get(key)
        new_val = new.get(key)

        # Skip if values are the same
        if old_val == new_val:
            continue

        # Handle nested dictionaries
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            changes.extend(compare_configs(old_val, new_val, full_key))
        # Handle lists (compare as sets for order-independence, but track actual change)
        elif isinstance(old_val, list) and isinstance(new_val, list):
            if set(old_val) != set(new_val):
                changes.append(ConfigChange(
                    field=full_key,
                    old_value=old_val,
                    new_value=new_val,
                ))
        # Handle value changes
        else:
            changes.append(ConfigChange(
                field=full_key,
                old_value=old_val,
                new_value=new_val,
            ))

    return changes
