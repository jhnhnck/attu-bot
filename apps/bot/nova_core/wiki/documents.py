# SPDX-License-Identifier: Apache-2.0
"""nova_core.wiki.documents | wiki document models."""

from pydantic import BaseModel, ConfigDict


class WikiViewDocument(BaseModel):
    """persistent state for a WikiLookupView instance."""

    model_config = ConfigDict(extra='ignore')

    message_id: int  # discord message id; primary key; used in button custom_ids
    guild_id: int
    channel_id: int
    invoker_user_id: int
    query: str
    current_index: int = 0
    page_titles: list[str]  # for get_summary() calls on navigation
    page_keys: list[str]  # for page_url() calls
    expires_at: int  # unix timestamp ttl
