# SPDX-License-Identifier: Apache-2.0
"""nova_core.reminders.documents | MongoDB document model for reminder records."""

from pydantic import BaseModel, ConfigDict


class ReminderDocument(BaseModel):
    """MongoDB document for a scheduled in-universe date reminder"""

    model_config = ConfigDict(extra='ignore')

    reminder_id: str  # uuid4, unique
    guild_id: int
    user_id: int
    channel_id: int  # channel where /remind add was used (delivery + fallback)
    message_id: int = 0  # bot response message id; used to build jump URL back to original /remind add
    attu_year: int  # target haracalnde year (PC era, >= 1)
    attu_month: int | None = None  # 1-12
    attu_day: int | None = None  # 1-30
    note: str = ''
    created_at: int  # unix timestamp
    fired: bool = False
    fired_at: int | None = None
