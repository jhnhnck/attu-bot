# SPDX-License-Identifier: Apache-2.0
"""nova_core.trees.documents | FamilyEcho family tree document."""

from pydantic import BaseModel, ConfigDict


class FamilyDocument(BaseModel):
    """MongoDB document for a registered FamilyEcho family tree."""

    model_config = ConfigDict(extra='ignore')

    guild_id: int
    name: str  # normalized key (lowercase, stripped)
    display_name: str  # original-case display name
    message_id: int | None = None  # discord message id from parsed message_link
    channel_id: int | None = None  # channel of the original message
    file_content: str  # full FamilyScript file text
    set_by: int  # user id who registered it
    set_at: int  # unix timestamp
