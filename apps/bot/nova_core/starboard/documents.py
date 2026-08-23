# SPDX-License-Identifier: Apache-2.0
"""nova_core.starboard.documents | starboard document models."""

from pydantic import BaseModel, ConfigDict


class StarredMessageDocument(BaseModel):
    """MongoDB document tracking stars earned by a message."""

    model_config = ConfigDict(extra='ignore')

    message_id: int
    channel_id: int
    guild_id: int
    author_id: int
    starboard_message_id: int | None = None  # post in the starboard channel, if any
    reactions: dict[str, list[int]] = {}  # emoji_str -> list of user_ids who normal-reacted
    super_reactions: dict[str, list[int]] = {}  # emoji_str -> list of user_ids who super-reacted (1.5x weight)
    total_reactions: int = 0  # raw count of all reactors (normal + super); kept for range queries
    weighted_total: float = 0.0  # weighted sum: normal = 1.0, super = 1.5
    reply_created: bool = False  # true once a reply has been sent to an uneditable predecessor post
    source_deleted: bool = False  # true when the original discord message no longer exists (404)
