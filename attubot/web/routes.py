"""
AttuBot - Web Routes
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from pydantic import ValidationError
from quart import Quart, Response, jsonify, redirect, render_template, request, session

from attubot.client.logo import generate_svg
from attubot.config import GuildChannels, GuildEpoch, GuildRoles, GuildStarboard, GuildUsers
from attubot.database.models import ChatChannelConfig, ChatConfigDocument
from attubot.logging import get_logger
from attubot.signals import send_signal
from attubot.web.app import config
from attubot.web.audit import ConfigChange, compare_configs, log_audit
from attubot.web.discord_integration import get_guild_channels, get_guild_info, get_guild_roles, get_users_info, invalidate_guild_cache
from attubot.web.forms import ChatConfigForm, GuildChannelsForm, GuildConfigForm, GuildEpochForm, GuildRolesForm, GuildStarboardForm, GuildUsersForm, SystemConfigForm, ThemeConfigForm


logger = get_logger(__name__)


def get_active_guild() -> int:
    """return the active guild id from session, falling back to primary_guild."""
    guild_id = session.get('active_guild')
    if guild_id and guild_id in config.authorized_guilds:
        return guild_id
    return config.primary_guild


def _validation_error_fields(exc: ValidationError) -> dict[str, str]:
    """reshape pydantic ValidationError into a field-path -> message dict for frontend field-level display."""
    fields = {}
    for err in exc.errors():
        path = '.'.join(str(loc) for loc in err['loc'])
        fields[path] = err['msg']
    return fields


def register_routes(app: Quart):  # noqa: PLR0915 - route registration defines many routes inline by design
    """Register all routes with the Quart app"""

    # ========== Page Routes ==========

    @app.route('/')
    async def index():
        """Dashboard - combined overview with server-side data"""
        import asyncio
        import time as time_mod

        from attubot.web.helpers import get_admin_stats_data, get_recent_audit_data, get_time_status_data

        guild_id = get_active_guild()

        stats, time_data, audit_logs = await asyncio.gather(
            get_admin_stats_data(),
            get_time_status_data(guild_id),
            get_recent_audit_data(guild_id=guild_id, limit=5),
            return_exceptions=True,
        )

        empty_stats = {'guilds': {}, 'data': {}, 'system': {}}
        if isinstance(stats, Exception):
            logger.error(f'dashboard stats failed: {stats}')
            stats = empty_stats
        if isinstance(time_data, Exception):
            logger.error(f'dashboard time failed: {time_data}')
            time_data = {}
        if isinstance(audit_logs, Exception):
            logger.error(f'dashboard audit failed: {audit_logs}')
            audit_logs = []

        # compute haracalnde date for current time
        haracalnde_now = ''
        try:
            from attubot.client.calendar import haracalnde_date

            haracalnde_now = await haracalnde_date(int(time_mod.time()), guild_id)
        except Exception as e:
            logger.debug(f'haracalnde date failed: {e}')

        return await render_template(
            'index.html',
            title='dashboard',
            stats=stats,
            time_status=time_data,
            audit_logs=audit_logs,
            haracalnde_now=haracalnde_now,
        )

    @app.route('/theme')
    async def theme_config_page():
        """Theme configuration editor"""
        return await render_template('theme_config.html', title='theme')

    @app.route('/system')
    async def system_config_page():
        """System configuration editor"""
        return await render_template('system_config.html', title='system')

    @app.route('/audit')
    async def audit_log_page():
        """Audit log viewer"""
        return await render_template('audit_log.html', title='audit log')

    @app.route('/admin/stats')
    async def admin_stats_page():
        """Admin statistics page"""
        return await render_template('admin_stats.html', title='statistics')

    # ========== New Split Config Page Routes ==========

    async def _render_config_page(template: str, title: str):
        """shared helper for guild config pages - loads SSR data."""
        import json

        from attubot.web.helpers import get_guild_config_data

        guild_id = get_active_guild()
        guild = config.guilds.get(guild_id)

        try:
            ssr = await get_guild_config_data(guild_id)
        except Exception as e:
            logger.error(f'SSR data load failed for {template}: {e}')
            ssr = {}

        return await render_template(
            template,
            title=title,
            guild_id=guild_id,
            guild_name=str(guild),
            ssr_data=json.dumps(ssr, default=str) if ssr else '',
        )

    @app.route('/channels')
    async def channels_page():
        """Channel configuration page"""
        return await _render_config_page('channels.html', 'channels')

    @app.route('/epoch')
    async def epoch_page():
        """Epoch configuration page"""
        return await _render_config_page('epoch.html', 'epoch')

    @app.route('/roles')
    async def roles_page():
        """Roles configuration page"""
        return await _render_config_page('roles.html', 'roles')

    @app.route('/users')
    async def users_page():
        """Users configuration page"""
        return await _render_config_page('users.html', 'users')

    @app.route('/starboard')
    async def starboard_page():
        """Starboard configuration page"""
        return await _render_config_page('starboard.html', 'starboard')

    # ========== Session-based guild data pages ==========

    @app.route('/years')
    async def years_session_page():
        """Years viewer page (session-based guild)"""
        guild_id = get_active_guild()
        guild = config.guilds.get(guild_id)
        return await render_template('years.html', title='years', guild_id=guild_id, guild_name=str(guild))

    @app.route('/markers')
    async def markers_session_page():
        """Markers viewer page (session-based guild)"""
        guild_id = get_active_guild()
        guild = config.guilds.get(guild_id)
        return await render_template('markers.html', title='markers', guild_id=guild_id, guild_name=str(guild))

    @app.route('/time')
    async def time_session_page():
        """Time status page (session-based guild)"""
        guild_id = get_active_guild()
        guild = config.guilds.get(guild_id)
        return await render_template('time_status.html', title='time status', guild_id=guild_id, guild_name=str(guild))

    # ========== Legacy Redirects ==========

    @app.route('/guild/<int:guild_id>')
    async def legacy_guild(guild_id: int):
        """Legacy guild config redirect - sets session and redirects to /channels"""
        if guild_id in config.authorized_guilds:
            session['active_guild'] = guild_id
        return redirect('/channels')

    @app.route('/guild/<int:guild_id>/years')
    async def legacy_years(guild_id: int):
        """Legacy years redirect"""
        if guild_id in config.authorized_guilds:
            session['active_guild'] = guild_id
        return redirect('/years')

    @app.route('/guild/<int:guild_id>/markers')
    async def legacy_markers(guild_id: int):
        """Legacy markers redirect"""
        if guild_id in config.authorized_guilds:
            session['active_guild'] = guild_id
        return redirect('/markers')

    @app.route('/guild/<int:guild_id>/time')
    async def legacy_time(guild_id: int):
        """Legacy time redirect"""
        if guild_id in config.authorized_guilds:
            session['active_guild'] = guild_id
        return redirect('/time')

    # ========== API Routes - Guild Session ==========

    @app.route('/api/set-guild', methods=['POST'])
    async def api_set_guild():
        """Set the active guild in session"""
        data = await request.get_json()
        if not data or 'guild_id' not in data:
            return jsonify({'error': 'guild_id is required'}), 400

        guild_id = int(data['guild_id'])
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        session['active_guild'] = guild_id
        return jsonify({'success': True, 'message': f'Active guild set to {guild_id}'})

    # ========== API Routes - Per-Section PATCH ==========

    @app.route('/api/guilds/<int:guild_id>/channels', methods=['PATCH'])
    async def api_patch_channels(guild_id: int):
        """Update guild channels configuration"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403
        guild = config.guilds.get(guild_id)
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        try:
            form_data = await request.get_json()
            if not form_data:
                return jsonify({'error': 'No data provided'}), 400

            validated = GuildChannelsForm(**form_data)
            old_section = guild.channels.model_dump()
            guild.channels = GuildChannels(**validated.model_dump())
            await guild.save()
            await send_signal('guild', guild_id)

            new_section = guild.channels.model_dump()
            changes = compare_configs(old_section, new_section, prefix='channels')
            if changes:
                await log_audit('guild', 'update', changes, guild_id=guild_id)

            return jsonify({'success': True, 'message': 'Channels saved'})
        except ValidationError as e:
            return jsonify({'error': 'Validation failed', 'fields': _validation_error_fields(e)}), 400
        except Exception as e:
            logger.error(f'error saving channels for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to save channels'}), 500

    @app.route('/api/guilds/<int:guild_id>/epoch', methods=['PATCH'])
    async def api_patch_epoch(guild_id: int):
        """Update guild epoch configuration"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403
        guild = config.guilds.get(guild_id)
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        try:
            form_data = await request.get_json()
            if not form_data:
                return jsonify({'error': 'No data provided'}), 400

            validated = GuildEpochForm(**form_data)
            old_section = guild.epoch.model_dump()
            guild.epoch = GuildEpoch(**validated.model_dump())
            await guild.save()
            await send_signal('guild', guild_id)

            new_section = guild.epoch.model_dump()
            changes = compare_configs(old_section, new_section, prefix='epoch')
            if changes:
                await log_audit('guild', 'update', changes, guild_id=guild_id)

            return jsonify({'success': True, 'message': 'Epoch saved'})
        except ValidationError as e:
            return jsonify({'error': 'Validation failed', 'fields': _validation_error_fields(e)}), 400
        except Exception as e:
            logger.error(f'error saving epoch for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to save epoch'}), 500

    @app.route('/api/guilds/<int:guild_id>/roles', methods=['PATCH'])
    async def api_patch_roles(guild_id: int):
        """Update guild roles configuration"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403
        guild = config.guilds.get(guild_id)
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        try:
            form_data = await request.get_json()
            if not form_data:
                return jsonify({'error': 'No data provided'}), 400

            validated = GuildRolesForm(**form_data)
            old_section = guild.roles.model_dump()
            guild.roles = GuildRoles(**validated.model_dump())
            await guild.save()
            await send_signal('guild', guild_id)

            new_section = guild.roles.model_dump()
            changes = compare_configs(old_section, new_section, prefix='roles')
            if changes:
                await log_audit('guild', 'update', changes, guild_id=guild_id)

            return jsonify({'success': True, 'message': 'Roles saved'})
        except ValidationError as e:
            return jsonify({'error': 'Validation failed', 'fields': _validation_error_fields(e)}), 400
        except Exception as e:
            logger.error(f'error saving roles for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to save roles'}), 500

    @app.route('/api/guilds/<int:guild_id>/users', methods=['PATCH'])
    async def api_patch_users(guild_id: int):
        """Update guild users configuration"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403
        guild = config.guilds.get(guild_id)
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        try:
            form_data = await request.get_json()
            if not form_data:
                return jsonify({'error': 'No data provided'}), 400

            validated = GuildUsersForm(**form_data)
            old_section = guild.users.model_dump()
            guild.users = GuildUsers(**validated.model_dump())
            await guild.save()
            await send_signal('guild', guild_id)

            new_section = guild.users.model_dump()
            changes = compare_configs(old_section, new_section, prefix='users')
            if changes:
                await log_audit('guild', 'update', changes, guild_id=guild_id)

            return jsonify({'success': True, 'message': 'Users saved'})
        except ValidationError as e:
            return jsonify({'error': 'Validation failed', 'fields': _validation_error_fields(e)}), 400
        except Exception as e:
            logger.error(f'error saving users for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to save users'}), 500

    @app.route('/api/guilds/<int:guild_id>/starboard', methods=['PATCH'])
    async def api_patch_starboard(guild_id: int):
        """Update guild starboard configuration"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403
        guild = config.guilds.get(guild_id)
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        try:
            form_data = await request.get_json()
            if not form_data:
                return jsonify({'error': 'No data provided'}), 400

            validated = GuildStarboardForm(**form_data)
            old_section = guild.starboard.model_dump()
            guild.starboard = GuildStarboard(**validated.model_dump())
            await guild.save()
            await send_signal('guild', guild_id)

            new_section = guild.starboard.model_dump()
            changes = compare_configs(old_section, new_section, prefix='starboard')
            if changes:
                await log_audit('guild', 'update', changes, guild_id=guild_id)

            return jsonify({'success': True, 'message': 'Starboard saved'})
        except ValidationError as e:
            return jsonify({'error': 'Validation failed', 'fields': _validation_error_fields(e)}), 400
        except Exception as e:
            logger.error(f'error saving starboard for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to save starboard'}), 500

    # ========== API Routes - Guild Config ==========

    @app.route('/api/guilds')
    async def api_list_guilds():
        """List all authorized guilds"""
        guilds = []
        for guild_id in config.authorized_guilds:
            guild_config = config.guilds.get(guild_id)
            guilds.append({
                'id': str(guild_id),  # Send as string to preserve precision
                'name': str(guild_config) if guild_config else f'Guild {guild_id}',
                'configured': guild_id in config.valid_guilds,
            })
        return jsonify({'guilds': guilds})

    @app.route('/api/guilds/<int:guild_id>')
    async def api_get_guild(guild_id: int):
        """Get guild configuration"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        guild = config.guilds.get(guild_id)
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        # Convert rollover_minutes to HH:MM format for display
        rollover_time = guild.epoch.get_rollover_time()
        rollover_str = rollover_time.strftime('%H:%M')

        # Fetch Discord channels for name resolution
        all_channels = await get_guild_channels(guild_id)
        channel_map = {ch['id']: ch['name'] for ch in (all_channels or [])}

        # Fetch Discord users for marker and valid_bots name resolution
        marker_user_ids = [int(user_id) for user_id in guild.users.markers if user_id]
        valid_bot_ids = [int(b) for b in guild.starboard.valid_bots if b]
        all_user_ids = list(set(marker_user_ids + valid_bot_ids))
        users_info = await get_users_info(all_user_ids) if all_user_ids else []
        user_map = {user['id']: user.get('global_name') or user.get('name', 'Unknown') for user in users_info}

        # Helper function to get channel name from ID
        def get_channel_name(channel_id):
            if not channel_id:
                return None
            return channel_map.get(str(channel_id))

        # Helper function to get user name from ID
        def get_user_name(user_id):
            if not user_id:
                return None
            return user_map.get(str(user_id))

        return jsonify({
            'guild_id': str(guild.id),  # Send as string to preserve precision
            'name': str(guild),
            'channels': {
                'activity': str(guild.channels.activity) if guild.channels.activity else '0',
                'activity_name': get_channel_name(guild.channels.activity),
                'announcements': str(guild.channels.announcements) if guild.channels.announcements else '0',
                'announcements_name': get_channel_name(guild.channels.announcements),
                'year_vc': str(guild.channels.year_vc) if guild.channels.year_vc else '0',
                'year_vc_name': get_channel_name(guild.channels.year_vc),
                'year_links': str(guild.channels.year_links) if guild.channels.year_links else '0',
                'year_links_name': get_channel_name(guild.channels.year_links),
                'meta_chat': str(guild.channels.meta_chat) if guild.channels.meta_chat else '0',
                'meta_chat_name': get_channel_name(guild.channels.meta_chat),
                'general': str(guild.channels.general) if guild.channels.general else '0',
                'general_name': get_channel_name(guild.channels.general),
                'logs': str(guild.channels.logs) if guild.channels.logs else '0',
                'logs_name': get_channel_name(guild.channels.logs),
                'eggs': str(guild.channels.eggs) if guild.channels.eggs else '0',
                'eggs_name': get_channel_name(guild.channels.eggs),
                'lore_channels': [str(ch) for ch in guild.channels.lore_channels],
                'lore_channels_names': [get_channel_name(ch) for ch in guild.channels.lore_channels],
                'canon_channels': [str(ch) for ch in guild.channels.canon_channels],
                'canon_channels_names': [get_channel_name(ch) for ch in guild.channels.canon_channels],
            },
            'epoch': {
                'time': guild.epoch.time,
                'year': guild.epoch.year,
                'length': guild.epoch.length,
                'paused': guild.epoch.paused,
                'rollover_minutes': guild.epoch.rollover_minutes,
                'rollover_time': rollover_str,
            },
            'roles': {
                'announcements': str(guild.roles.announcements) if guild.roles.announcements else '0',
                'bot_color': str(guild.roles.bot_color) if guild.roles.bot_color else '0',
            },
            'users': {
                'markers': [str(user) for user in guild.users.markers],
                'markers_names': [get_user_name(user) for user in guild.users.markers],
            },
            'starboard': {
                'channel_id': str(guild.starboard.channel_id) if guild.starboard.channel_id else '0',
                'channel_id_name': get_channel_name(guild.starboard.channel_id),
                'emojis': guild.starboard.emojis,
                'valid_bots': [str(b) for b in guild.starboard.valid_bots],
                'valid_bots_names': [get_user_name(b) for b in guild.starboard.valid_bots],
            },
        })

    @app.route('/api/guilds/<int:guild_id>', methods=['POST'])
    async def api_save_guild(guild_id: int):
        """Save guild configuration"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        guild = config.guilds.get(guild_id)
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        try:
            # Get form data
            form_data = await request.get_json()
            if not form_data:
                return jsonify({'error': 'No data provided'}), 400

            # Validate with Pydantic
            validated = GuildConfigForm(**form_data)

            # Capture old config for audit logging
            old_config = {
                'channels': guild.channels.model_dump(),
                'epoch': guild.epoch.model_dump(),
                'roles': guild.roles.model_dump(),
                'users': guild.users.model_dump(),
                'starboard': guild.starboard.model_dump(),
            }

            # Update guild configuration
            guild.channels = GuildChannels(**validated.channels.model_dump())
            guild.epoch = GuildEpoch(**validated.epoch.model_dump())
            guild.roles = GuildRoles(**validated.roles.model_dump())
            guild.users = GuildUsers(**validated.users.model_dump())
            guild.starboard = GuildStarboard(**validated.starboard.model_dump())

            # Save to database
            await guild.save()
            await send_signal('guild', guild_id)

            # audit logging
            new_config = {
                'channels': guild.channels.model_dump(),
                'epoch': guild.epoch.model_dump(),
                'roles': guild.roles.model_dump(),
                'users': guild.users.model_dump(),
                'starboard': guild.starboard.model_dump(),
            }
            changes = compare_configs(old_config, new_config)
            if changes:
                await log_audit('guild', 'update', changes, guild_id=guild_id)

            logger.info(f'guild {guild_id} configuration saved')

            return jsonify({
                'success': True,
                'message': 'Configuration saved successfully',
            })

        except ValidationError as e:
            logger.error(f'validation error for guild {guild_id}: {e}')

            await log_audit('guild', 'update', [], guild_id=guild_id, success=False, error_message=f'Validation error: {e!s}')

            return jsonify({
                'error': 'Validation failed',
                'details': [err['msg'] for err in e.errors()],
            }), 400
        except Exception as e:
            logger.error(f'error saving guild {guild_id}: {e}')
            await log_audit('guild', 'update', [], guild_id=guild_id, success=False, error_message=str(e))

            return jsonify({'error': 'Failed to save configuration'}), 500

    @app.route('/api/guilds/<int:guild_id>/validate', methods=['POST'])
    async def api_validate_guild(guild_id: int):
        """Validate guild configuration without saving"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            form_data = await request.get_json()
            if not form_data:
                return jsonify({'error': 'No data provided'}), 400

            # Validate with Pydantic
            validated = GuildConfigForm(**form_data)

            return jsonify({
                'valid': True,
                'message': 'Configuration is valid',
                'data': validated.model_dump(),
            })

        except ValidationError as e:
            return jsonify({
                'valid': False,
                'error': 'Validation failed',
                'details': e.errors(),
            }), 400

    @app.route('/api/guilds/<int:guild_id>/reset', methods=['POST'])
    async def api_reset_guild(guild_id: int):
        """Reload guild configuration from database"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            success = await config.load_guild(guild_id)
            if success:
                await log_audit('guild', 'reload', [], guild_id=guild_id)
                return jsonify({
                    'success': True,
                    'message': 'Configuration reloaded from database',
                })
            else:
                await log_audit('guild', 'reload', [], guild_id=guild_id, success=False, error_message='load_guild returned false')
                return jsonify({'error': 'Failed to reload configuration'}), 500
        except Exception as e:
            logger.error(f'error reloading guild {guild_id}: {e}')
            await log_audit('guild', 'reload', [], guild_id=guild_id, success=False, error_message=str(e))
            return jsonify({'error': 'Failed to reload configuration'}), 500

    @app.route('/api/guilds/<int:guild_id>/channels')
    async def api_get_channels(guild_id: int):
        """Fetch all channels for a guild"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        channels = await get_guild_channels(guild_id)
        return jsonify({'channels': channels or []})

    @app.route('/api/guilds/<int:guild_id>/info')
    async def api_get_guild_info(guild_id: int):
        """Fetch guild info (name, icon) from Discord"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        guild_info = await get_guild_info(guild_id)
        if not guild_info:
            return jsonify({'error': 'Failed to fetch guild info'}), 500

        return jsonify(guild_info)

    @app.route('/api/guilds/<int:guild_id>/roles')
    async def api_get_roles(guild_id: int):
        """Fetch all roles for a guild"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        roles = await get_guild_roles(guild_id)
        return jsonify({'roles': roles})

    @app.route('/api/guilds/<int:guild_id>/refresh', methods=['POST'])
    async def api_refresh_discord_cache(guild_id: int):
        """Invalidate Discord API cache for a guild"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        invalidate_guild_cache(guild_id)
        await log_audit('guild', 'cache_invalidate', [], guild_id=guild_id)
        return jsonify({'success': True, 'message': 'Cache invalidated'})

    # ========== API Routes - Theme Config ==========

    @app.route('/api/theme')
    async def api_get_theme():
        """Get theme configuration"""
        theme = config.theme
        if not theme:
            return jsonify({'error': 'Theme not found'}), 404

        return jsonify({
            'rotation': theme.rotation,
            'max_rate': theme.max_rate,
            'saturation': theme.saturation,
            'lightness': theme.lightness,
            'bot_color': theme.bot_color,
            'guild_color': theme.guild_color,
            'logo_rings': theme.logo_rings,
            'logo_planet': theme.logo_planet,
            'egg_emojis': theme.egg_emojis,
            'progress_emojis': getattr(theme, 'progress_emojis', {}),
            'ui_emojis': {k: str(v) for k, v in theme.ui_emojis.items()},
        })

    @app.route('/api/theme/icon.svg')
    async def api_get_theme_icon():
        """Serve the bot logo as SVG for navbar use"""
        theme = config.theme
        if not theme:
            return jsonify({'error': 'Theme not found'}), 404

        svg = generate_svg(
            rotation=theme.rotation,
            background=theme.bot_color,
            rings=theme.logo_rings,
            planet=theme.logo_planet,
        )
        return Response(svg, mimetype='image/svg+xml')

    @app.route('/api/theme', methods=['POST'])
    async def api_save_theme():
        """Save theme configuration"""
        try:
            form_data = await request.get_json()
            if not form_data:
                return jsonify({'error': 'No data provided'}), 400

            # Validate with Pydantic
            validated = ThemeConfigForm(**form_data)

            # Capture old config for audit logging
            old_config = {
                'rotation': config.theme.rotation,
                'max_rate': config.theme.max_rate,
                'saturation': config.theme.saturation,
                'lightness': config.theme.lightness,
                'bot_color': config.theme.bot_color,
                'guild_color': config.theme.guild_color,
                'logo_rings': config.theme.logo_rings,
                'logo_planet': config.theme.logo_planet,
                'ui_emojis': config.theme.ui_emojis,
            }

            # Update theme
            config.theme.rotation = validated.rotation
            config.theme.max_rate = validated.max_rate
            config.theme.saturation = validated.saturation
            config.theme.lightness = validated.lightness
            config.theme.bot_color = validated.bot_color
            config.theme.guild_color = validated.guild_color
            config.theme.logo_rings = validated.logo_rings
            config.theme.logo_planet = validated.logo_planet
            config.theme.ui_emojis = validated.ui_emojis

            # Save to database
            await config.theme.save()
            await send_signal('theme')

            # audit logging
            new_config = {
                'rotation': config.theme.rotation,
                'max_rate': config.theme.max_rate,
                'saturation': config.theme.saturation,
                'lightness': config.theme.lightness,
                'bot_color': config.theme.bot_color,
                'guild_color': config.theme.guild_color,
                'logo_rings': config.theme.logo_rings,
                'logo_planet': config.theme.logo_planet,
                'ui_emojis': config.theme.ui_emojis,
            }
            changes = compare_configs(old_config, new_config)
            if changes:
                await log_audit('theme', 'update', changes)

            logger.info('theme configuration saved')

            return jsonify({
                'success': True,
                'message': 'Theme saved successfully',
            })

        except ValidationError as e:
            logger.error(f'validation error for theme: {e}')

            await log_audit('theme', 'update', [], success=False, error_message=f'Validation error: {e!s}')

            return jsonify({
                'error': 'Validation failed',
                'details': [err['msg'] for err in e.errors()],
            }), 400
        except Exception as e:
            logger.error(f'error saving theme: {e}')
            await log_audit('theme', 'update', [], success=False, error_message=str(e))

            return jsonify({'error': 'Failed to save theme'}), 500

    # ========== API Routes - System Config ==========

    @app.route('/api/system')
    async def api_get_system():
        """Get system configuration"""
        return jsonify({
            'version': config.config_version,
            'primary_guild': str(config.primary_guild),
            'error_log_guild': str(config.error_log[0]) if config.error_log else '0',
            'error_log_channel': str(config.error_log[1]) if config.error_log else '0',
            'error_hook': config.error_hook or '',
        })

    @app.route('/api/system', methods=['POST'])
    async def api_save_system():
        """Save system configuration"""
        try:
            form_data = await request.get_json()
            if not form_data:
                return jsonify({'error': 'No data provided'}), 400

            # Validate with Pydantic
            validated = SystemConfigForm(**form_data)

            # Capture old config for audit logging
            old_config = {
                'primary_guild': config.primary_guild,
                'error_log_guild': config.error_log[0] if config.error_log else 0,
                'error_log_channel': config.error_log[1] if config.error_log else 0,
                'error_hook': f'...{config.error_hook[-6:]}' if config.error_hook else '',
            }

            # Update system config in database
            await config.config_repo.update_system_field('primary_guild', validated.primary_guild)
            await config.config_repo.update_system_field(
                'error_log',
                [validated.error_log_guild, validated.error_log_channel],
            )
            await config.config_repo.update_system_field('error_hook', validated.error_hook)

            # Reload system config into memory
            await config.load_globals()
            await send_signal('system')

            # audit logging
            new_config = {
                'primary_guild': config.primary_guild,
                'error_log_guild': config.error_log[0] if config.error_log else 0,
                'error_log_channel': config.error_log[1] if config.error_log else 0,
                'error_hook': f'...{config.error_hook[-6:]}' if config.error_hook else '',
            }
            changes = compare_configs(old_config, new_config)
            if changes:
                await log_audit('system', 'update', changes)

            logger.info('system configuration saved')

            return jsonify({
                'success': True,
                'message': 'System configuration saved successfully',
            })

        except ValidationError as e:
            logger.error(f'validation error for system config: {e}')

            await log_audit('system', 'update', [], success=False, error_message=f'Validation error: {e!s}')

            return jsonify({
                'error': 'Validation failed',
                'details': [
                    {
                        'loc': list(err['loc']),
                        'msg': err['msg'],
                        'type': err['type'],
                    }
                    for err in e.errors()
                ],
            }), 400
        except Exception as e:
            logger.error(f'error saving system config: {e}')
            await log_audit('system', 'update', [], success=False, error_message=str(e))

            return jsonify({'error': 'Failed to save system configuration'}), 500

    # ========== Page Route - Chat Config ==========

    @app.route('/chat')
    async def chat_config_page():
        """Chat runtime configuration editor"""
        return await render_template('chat_config.html', title='chat')

    # ========== API Routes - Chat Config ==========

    @app.route('/api/chat')
    async def api_get_chat():
        """Get chat runtime configuration"""
        rt = config.chat_runtime
        return jsonify({
            'discord_lookback_hours': rt.discord_lookback_hours,
            'discord_window_minutes': rt.discord_window_minutes,
            'noise_filter_min_tokens': rt.noise_filter_min_tokens,
            'ignored_user_ids': [str(uid) for uid in rt.ignored_user_ids],
            'ingest_discord': rt.ingest_discord,
            'ingest_wiki': rt.ingest_wiki,
            'ingest_documents': rt.ingest_documents,
            'wiki_namespaces': rt.wiki_namespaces,
            'character_log_channel_id': str(rt.character_log_channel_id) if rt.character_log_channel_id else None,
            'chat_channels': {
                str(cid): {
                    'name': ch.name,
                    'description': ch.description,
                    'channel_type': ch.channel_type,
                    'ingest': ch.ingest,
                }
                for cid, ch in rt.chat_channels.items()
            },
            'user_nations': {str(uid): nation for uid, nation in rt.user_nations.items()},
            'retrieval_top_k_wiki': rt.retrieval_top_k_wiki,
            'retrieval_top_k_discord': rt.retrieval_top_k_discord,
            'retrieval_top_k_documents': rt.retrieval_top_k_documents,
            'retrieval_top_k_images': rt.retrieval_top_k_images,
        })

    @app.route('/api/chat', methods=['POST'])
    async def api_save_chat():
        """Save chat runtime configuration"""
        try:
            form_data = await request.get_json()
            if not form_data:
                return jsonify({'error': 'No data provided'}), 400

            validated = ChatConfigForm.model_validate(form_data)

            # capture old state for audit
            rt = config.chat_runtime
            old_config = rt.model_dump()

            # build updated document
            new_doc = ChatConfigDocument(
                discord_lookback_hours=validated.discord_lookback_hours,
                discord_window_minutes=validated.discord_window_minutes,
                noise_filter_min_tokens=validated.noise_filter_min_tokens,
                ignored_user_ids=validated.ignored_user_ids,
                ingest_discord=validated.ingest_discord,
                ingest_wiki=validated.ingest_wiki,
                ingest_documents=validated.ingest_documents,
                wiki_namespaces=validated.wiki_namespaces,
                character_log_channel_id=validated.character_log_channel_id,
                chat_channels={
                    cid: ChatChannelConfig(
                        name=ch.name,
                        description=ch.description,
                        channel_type=ch.channel_type,
                        ingest=ch.ingest,
                    )
                    for cid, ch in validated.chat_channels.items()
                },
                user_nations=validated.user_nations,
                retrieval_top_k_wiki=validated.retrieval_top_k_wiki,
                retrieval_top_k_discord=validated.retrieval_top_k_discord,
                retrieval_top_k_documents=validated.retrieval_top_k_documents,
                retrieval_top_k_images=validated.retrieval_top_k_images,
            )

            await config.chat_config_repo.save(new_doc)
            await config.load_chat_runtime()
            await send_signal('chat')

            # audit logging
            new_config = config.chat_runtime.model_dump()
            changes = compare_configs(old_config, new_config)
            if changes:
                await log_audit('chat', 'update', changes)

            logger.info('chat configuration saved')

            return jsonify({
                'success': True,
                'message': 'Chat configuration saved successfully',
            })

        except ValidationError as e:
            logger.error(f'validation error for chat config: {e}')

            await log_audit('chat', 'update', [], success=False, error_message=f'Validation error: {e!s}')

            return jsonify({
                'error': 'Validation failed',
                'details': [{'type': err['type'], 'loc': err['loc'], 'msg': err['msg']} for err in e.errors()],
            }), 400
        except Exception as e:
            logger.error(f'error saving chat config: {e}')
            await log_audit('chat', 'update', [], success=False, error_message=str(e))

            return jsonify({'error': 'Failed to save chat configuration'}), 500

    # ========== API Routes - Audit Log ==========

    @app.route('/api/audit')
    async def api_get_audit_logs():
        """Get audit logs with optional filtering"""
        from attubot.web import app as web_app

        if not web_app.audit_logger:
            return jsonify({'error': 'Audit logging not available'}), 503

        # Get query parameters
        config_type = request.args.get('config_type')
        guild_id = request.args.get('guild_id', type=int)
        limit = request.args.get('limit', default=50, type=int)
        skip = request.args.get('skip', default=0, type=int)

        # Limit max results
        limit = min(limit, 200)

        try:
            logs = await web_app.audit_logger.get_logs(
                config_type=config_type,
                guild_id=guild_id,
                limit=limit,
                skip=skip,
            )

            # Format timestamps for display
            from datetime import datetime

            for log in logs:
                if '_id' in log:
                    log['_id'] = str(log['_id'])
                if 'guild_id' in log and log['guild_id'] is not None:
                    log['guild_id'] = str(log['guild_id'])
                log['timestamp_formatted'] = datetime.fromtimestamp(log['timestamp']).strftime('%Y-%m-%d %H:%M:%S')

            return jsonify({
                'logs': logs,
                'count': len(logs),
            })

        except Exception as e:
            logger.error(f'error fetching audit logs: {e}')
            return jsonify({'error': 'Failed to fetch audit logs'}), 500

    # ========== API Routes - Years ==========

    @app.route('/api/guilds/<int:guild_id>/years')
    async def api_get_years(guild_id: int):
        """Get all year records for a guild"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.client.years import Year

            # Pagination (L7)
            limit = min(request.args.get('limit', default=100, type=int), 500)
            skip = request.args.get('skip', default=0, type=int)

            years = await Year.all_for_guild(guild_id)
            years_data = [
                {
                    'guild': str(y.guild),
                    'year': y.year,
                    'start_time': y.start_time,
                    'end_time': y.end_time,
                    'duration': y.duration,
                    'notes': y.notes,
                }
                for y in years
            ]
            total = len(years_data)
            years_data = years_data[skip : skip + limit]

            return jsonify({
                'guild_id': str(guild_id),
                'years': years_data,
                'count': len(years_data),
                'total': total,
                'limit': limit,
                'skip': skip,
            })

        except Exception as e:
            logger.error(f'error fetching years for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch years'}), 500

    @app.route('/api/guilds/<int:guild_id>/years/<int:year>')
    async def api_get_year(guild_id: int, year: int):
        """Get specific year record"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.client.years import Year

            year_record = await Year.get(guild_id, year)
            if not year_record:
                return jsonify({'error': f'Year {year} not found'}), 404

            return jsonify({
                'guild': str(year_record.guild),
                'year': year_record.year,
                'start_time': year_record.start_time,
                'end_time': year_record.end_time,
                'duration': year_record.duration,
                'notes': year_record.notes,
            })

        except Exception as e:
            logger.error(f'error fetching year {year} for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch year'}), 500

    @app.route('/api/guilds/<int:guild_id>/years/latest')
    async def api_get_latest_year(guild_id: int):
        """Get the most recent year record"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.client.years import Year

            year_record = await Year.get_latest(guild_id)
            if not year_record:
                return jsonify({'error': 'No years found'}), 404

            return jsonify({
                'guild': str(year_record.guild),
                'year': year_record.year,
                'start_time': year_record.start_time,
                'end_time': year_record.end_time,
                'duration': year_record.duration,
                'notes': year_record.notes,
            })

        except Exception as e:
            logger.error(f'error fetching latest year for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch latest year'}), 500

    @app.route('/api/guilds/<int:guild_id>/years/<int:year>', methods=['POST'])
    async def api_create_year(guild_id: int, year: int):
        """Create/update year record"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.client.years import Year

            data = await request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            # Validate required fields
            if 'start_time' not in data:
                return jsonify({'error': 'start_time is required'}), 400

            # Get existing year or create new
            existing = await Year.get(guild_id, year)

            if existing:
                # Update existing year
                await existing.update(
                    start_time=data.get('start_time', existing.start_time),
                    end_time=data.get('end_time', existing.end_time),
                    duration=data.get('duration', existing.duration),
                    notes=data.get('notes', existing.notes),
                )
                message = f'Year {year} updated successfully'
            else:
                # Create new year
                new_year = Year(
                    guild=guild_id,
                    year=year,
                    start_time=data['start_time'],
                    end_time=data.get('end_time', 0),
                    duration=data.get('duration', 0),
                    notes=data.get('notes', ''),
                )
                await new_year.save()
                message = f'Year {year} created successfully'

            await log_audit('year', 'create' if not existing else 'update', [ConfigChange(field='year_data', old_value=str(existing) if existing else None, new_value=str(data))], guild_id=guild_id)

            logger.info(f'year {year} {"updated" if existing else "created"} for guild {guild_id}')
            return jsonify({'success': True, 'message': message})

        except Exception as e:
            logger.error(f'error creating/updating year {year} for guild {guild_id}: {e}')
            await log_audit('year', 'create', [], guild_id=guild_id, success=False, error_message=str(e))
            return jsonify({'error': 'Internal server error'}), 500

    @app.route('/api/guilds/<int:guild_id>/years/<int:year>', methods=['DELETE'])
    async def api_delete_year(guild_id: int, year: int):
        """Delete year record"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.client.years import Year

            existing = await Year.get(guild_id, year)
            if not existing:
                return jsonify({'error': f'Year {year} not found'}), 404

            await existing.delete()

            await log_audit('year', 'delete', [ConfigChange(field='year', old_value=year, new_value=None)], guild_id=guild_id)

            logger.info(f'year {year} deleted for guild {guild_id}')
            return jsonify({'success': True, 'message': f'Year {year} deleted successfully'})

        except Exception as e:
            logger.error(f'error deleting year {year} for guild {guild_id}: {e}')
            await log_audit('year', 'delete', [], guild_id=guild_id, success=False, error_message=str(e))
            return jsonify({'error': 'Internal server error'}), 500

    # ========== API Routes - Markers ==========

    @app.route('/api/guilds/<int:guild_id>/markers')
    async def api_get_markers(guild_id: int):
        """Get all markers for a guild"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.client.markers import YearMarker

            # Pagination (L7)
            limit = min(request.args.get('limit', default=100, type=int), 500)
            skip = request.args.get('skip', default=0, type=int)

            markers = await YearMarker.all_for_guild(guild_id)
            markers_data = [
                {
                    'channel': str(m.channel),
                    'message': str(m.message),
                    'year': m.year,
                    'exact': m.exact,
                    'wiki_page': m.wiki_page,
                }
                for m in markers
            ]
            total = len(markers_data)
            markers_data = markers_data[skip : skip + limit]

            return jsonify({
                'guild_id': str(guild_id),
                'markers': markers_data,
                'count': len(markers_data),
                'total': total,
                'limit': limit,
                'skip': skip,
            })

        except Exception as e:
            logger.error(f'error fetching markers for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch markers'}), 500

    @app.route('/api/guilds/<int:guild_id>/markers/<int:year>/<int:channel>')
    async def api_get_marker(guild_id: int, year: int, channel: int):
        """Get specific override marker for a (year, channel) pair"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.client.markers import YearMarker

            marker = await YearMarker.get(channel, year)
            if not marker:
                return jsonify({'error': f'Marker for year {year} channel {channel} not found'}), 404

            return jsonify({
                'guild': str(marker.guild),
                'channel': str(marker.channel),
                'message': str(marker.message),
                'year': marker.year,
                'exact': marker.exact,
                'wiki_page': marker.wiki_page,
            })

        except Exception as e:
            logger.error(f'error fetching marker for year {year} channel {channel} in guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch marker'}), 500

    @app.route('/api/guilds/<int:guild_id>/markers/<int:year>/timestamp')
    async def api_get_marker_timestamp(guild_id: int, year: int):
        """Get timestamp from marker snowflake"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.client.markers import YearMarker

            timestamp = await YearMarker.timestamp(year, guild_id)
            if timestamp is None:
                return jsonify({'error': f'Marker for year {year} not found'}), 404

            return jsonify({
                'year': year,
                'timestamp': timestamp,
            })

        except Exception as e:
            logger.error(f'error fetching marker timestamp for year {year} in guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch marker timestamp'}), 500

    @app.route('/api/guilds/<int:guild_id>/markers/<int:year>/<int:channel>', methods=['POST'])
    async def api_create_marker(guild_id: int, year: int, channel: int):
        """Create/update override marker for a (year, channel) pair"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.client.markers import YearMarker

            data = await request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            if 'message' not in data:
                return jsonify({'error': 'message (Discord message ID) is required'}), 400

            message = int(data['message'])

            existing = await YearMarker.get(channel, year)

            if existing:
                await existing.update(
                    message=message,
                    exact=data.get('exact', existing.exact),
                    wiki_page=data.get('wiki_page', existing.wiki_page),
                )
                msg = f'Marker for year {year} channel {channel} updated successfully'
            else:
                new_marker = YearMarker(
                    channel=channel,
                    message=message,
                    guild=guild_id,
                    year=year,
                    exact=data.get('exact', True),
                    wiki_page=data.get('wiki_page', False),
                )
                await new_marker.save()
                msg = f'Marker for year {year} channel {channel} created successfully'

            await log_audit('marker', 'create' if not existing else 'update', [ConfigChange(field='marker_data', old_value=str(existing) if existing else None, new_value=str(data))], guild_id=guild_id)

            logger.info(f'marker year={year} channel={channel} {"updated" if existing else "created"} for guild {guild_id}')
            return jsonify({'success': True, 'message': msg})

        except Exception as e:
            logger.error(f'error creating/updating marker for year {year} channel {channel} in guild {guild_id}: {e}')
            await log_audit('marker', 'create', [], guild_id=guild_id, success=False, error_message=str(e))
            return jsonify({'error': 'Internal server error'}), 500

    @app.route('/api/guilds/<int:guild_id>/markers/<int:year>/<int:channel>', methods=['DELETE'])
    async def api_delete_marker(guild_id: int, year: int, channel: int):
        """Delete override marker for a (year, channel) pair"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.client.markers import YearMarker

            existing = await YearMarker.get(channel, year)
            if not existing:
                return jsonify({'error': f'Marker for year {year} channel {channel} not found'}), 404

            await existing.delete()

            await log_audit('marker', 'delete', [ConfigChange(field='marker', old_value=f'year={year} channel={channel}', new_value=None)], guild_id=guild_id)

            logger.info(f'marker year={year} channel={channel} deleted for guild {guild_id}')
            return jsonify({'success': True, 'message': f'Marker for year {year} channel {channel} deleted successfully'})

        except Exception as e:
            logger.error(f'error deleting marker for year {year} channel {channel} in guild {guild_id}: {e}')
            await log_audit('marker', 'delete', [], guild_id=guild_id, success=False, error_message=str(e))
            return jsonify({'error': 'Internal server error'}), 500

    # ========== API Routes - Time/Calendar ==========

    @app.route('/api/guilds/<int:guild_id>/time')
    async def api_get_time_status(guild_id: int):
        """Get current time status for a guild"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.web.helpers import get_time_status_data

            data = await get_time_status_data(guild_id)
            if not data:
                return jsonify({'error': 'Guild not configured'}), 404
            return jsonify(data)

        except Exception as e:
            logger.error(f'error fetching time status for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch time status'}), 500

    @app.route('/api/guilds/<int:guild_id>/time/year-span/<int:year>')
    async def api_get_year_span(guild_id: int, year: int):
        """Get time span (start/end/duration) for a specific year"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.client.calendar import get_year_span

            span = await get_year_span(year, guild_id)

            return jsonify({
                'guild_id': str(guild_id),
                'year': year,
                'start_time': span.start_time,
                'end_time': span.end_time,
                'duration': span.duration,
            })

        except Exception as e:
            logger.error(f'error fetching year span for year {year} in guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch year span'}), 500

    # ========== API Routes - Admin Stats ==========

    @app.route('/api/admin/stats')
    async def api_get_admin_stats():
        """Get system statistics"""
        try:
            from attubot.web.helpers import get_admin_stats_data

            return jsonify(await get_admin_stats_data())
        except Exception as e:
            logger.error(f'error fetching admin stats: {e}')
            return jsonify({'error': 'Failed to fetch statistics'}), 500

    # ========== Health Check ==========

    @app.route('/health')
    async def health():
        """Health check endpoint"""
        return jsonify({
            'status': 'ok',
            'service': 'attu-bot-web',
            'config_loaded': config._get_event('load').is_set(),
        })

    logger.info('routes registered')
