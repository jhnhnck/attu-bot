# SPDX-License-Identifier: Apache-2.0
"""nova_core.ccboard.documents | MongoDB document models for the ccboard feature."""

from pydantic import BaseModel, ConfigDict

from attu_models import MessageDocument


class ReactionDocument(BaseModel):
    """MongoDB document for a single ccboard reaction (one per message_id, user_id).

    records are never hard-deleted; `removed` is set only on an explicit remove event.
    re-reacting with the same emoji refreshes the doc in place; a different emoji
    soft-deletes the existing doc and inserts a new one.
    """

    model_config = ConfigDict(extra='ignore')

    message_id: int  # original message (resolved after redirect)
    user_id: int  # reactor
    guild_id: int
    author_id: int  # message author (denormalized for "reactions given" leaderboard)
    emoji_str: str  # which emoji they reacted with
    is_super: bool = False  # burst/super reaction
    point_value: int = 0  # snapshot at reaction time (config emoji value plus super_bonus if applicable)
    reacted_at: int  # unix timestamp
    removed: bool = False  # soft-delete flag
    removed_at: int | None = None  # unix timestamp when soft-deleted
    source_message_id: int  # physical discord message where the reaction lives (pre-redirect)
    source_channel_id: int  # physical discord channel where the reaction lives (pre-redirect)
    last_recounted_at: int | None = None  # unix timestamp; stamped on every point_value re-snapshot (watcher refresh, auditor recount). None means "never recounted; use reacted_at for the staleness predicate"


class BoardEntryDocument(BaseModel):
    """MongoDB document for one tracked message on the ccboard.

    snapshot fields (`snapshot`, `reply_snapshot`) are static from first tracking
    and are intentionally not refreshed when the source message is edited.
    """

    model_config = ConfigDict(extra='ignore')

    message_id: int
    channel_id: int
    guild_id: int
    author_id: int
    effective_author_id: int | None = None  # resolved credit author; None falls back to author_id
    starboard_message_id: int | None = None
    display_message_ids: list[int] = []  # ids of /stars responses showing this entry; capped at 20
    net_points: int = 0  # sum of point_value across all active reactions
    positive_points: int = 0  # sum of positive-value reactions only; threshold uses this
    last_reaction_at: int = 0  # unix timestamp; updated by watcher on each event
    last_synced_at: int = 0  # unix timestamp; updated by manager after each successful sync (diagnostics)
    is_dirty: bool = False  # set by watcher on every event; cleared by manager after sync -- manager pickup uses this
    reply_created: bool = False  # true once a reply has been sent to an uneditable predecessor post
    snapshot: MessageDocument  # full message snapshot at first track
    reply_snapshot: MessageDocument | None = None  # snapshot of refs.reply_to if set
