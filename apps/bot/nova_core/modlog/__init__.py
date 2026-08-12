# SPDX-License-Identifier: Apache-2.0
"""nova_core.modlog | moderation log feature manifest."""

from nova_core.manifest import FeatureManifest
from nova_core.modlog.handlers import (
    on_guild_channel_create,
    on_guild_channel_delete,
    on_guild_channel_update,
    on_guild_emojis_update,
    on_guild_role_create,
    on_guild_role_delete,
    on_guild_role_update,
    on_member_ban,
    on_member_join,
    on_member_remove,
    on_member_unban,
    on_member_update,
)


manifest = FeatureManifest(
    name='modlog',
    event_handlers={
        'on_member_join': on_member_join,
        'on_member_remove': on_member_remove,
        'on_member_ban': on_member_ban,
        'on_member_unban': on_member_unban,
        'on_guild_channel_create': on_guild_channel_create,
        'on_guild_channel_delete': on_guild_channel_delete,
        'on_guild_channel_update': on_guild_channel_update,
        'on_guild_role_create': on_guild_role_create,
        'on_guild_role_delete': on_guild_role_delete,
        'on_guild_role_update': on_guild_role_update,
        'on_member_update': on_member_update,
        'on_guild_emojis_update': on_guild_emojis_update,
    },
)
