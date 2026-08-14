# SPDX-License-Identifier: Apache-2.0
"""nova_core.client.starboard | re-export shim.

the starboard implementation has moved to nova_core.starboard.handlers.
this module re-exports everything from there so existing import sites keep working.
"""

from nova_core.starboard.handlers import (  # noqa: F401  # re-export entire starboard handlers namespace for backward compat
    _IMAGE_EXTENSIONS,
    _JUMP_URL_RE,
    _REACTION_PART_RE,
    _REPLY_COLOR,
    _check_and_announce_sweep,
    _count_streak,
    _fetch_store_and_backfill,
    _fmt_count,
    _get_repo,
    _hydrate_stored_embed,
    _is_image,
    _looks_like_image_url,
    _merge_stored_embed,
    _message_locks,
    _parse_color,
    _pending_bot_removals,
    _remove_reaction_from_discord,
    _should_merge_stored_embed,
    _starboard_repo,
    _strip_query,
    _sweep_message,
    _sync_starboard_post,
    _weighted_count,
    backfill_message_reactions,
    build_content,
    build_embeds,
    dominant_color,
    handle_star_add,
    handle_star_clear,
    handle_star_clear_emoji,
    handle_star_remove,
    parse_jump_url,
    parse_starboard_content,
)
