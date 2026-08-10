# SPDX-License-Identifier: Apache-2.0
"""nova_core.eggs.documents | mongodb document models for the eggs feature."""

from pydantic import BaseModel, ConfigDict, field_validator


class EggDocument(BaseModel):
    """MongoDB document for a collected egg"""

    model_config = ConfigDict(extra='ignore')

    egg_id: str  # uuid4, unique
    guild_id: int
    user_id: int
    rarity: str  # 'common' | 'uncommon' | 'rare' | 'legendary' | 'mythical'
    collected_at: int  # unix timestamp
    hatches_at: int  # collected_at + rarity hatch duration
    hatched: bool = False
    result: str | None = None  # unicode emoji char after hatching
    message_id: int | None = None  # id of the message in user's thread

    @field_validator('collected_at', 'hatches_at', mode='before')
    @classmethod
    def coerce_to_int(cls, v: object) -> int:
        return int(v)  # pyright: ignore[reportArgumentType]


class EggUserDocument(BaseModel):
    """MongoDB document tracking per-user egg state"""

    model_config = ConfigDict(extra='ignore')

    guild_id: int
    user_id: int
    thread_id: int = 0  # user's egg collection thread
    last_collected_at: int = 0  # unix timestamp; reboot-safe cooldown

    @field_validator('last_collected_at', mode='before')
    @classmethod
    def coerce_to_int(cls, v: object) -> int:
        return int(v)  # pyright: ignore[reportArgumentType]
