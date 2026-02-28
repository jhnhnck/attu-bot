"""
AttuBot - Web Routes
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from pydantic import ValidationError
from quart import Quart, jsonify, render_template, request

from attubot.config import GuildChannels, GuildEpoch, GuildRoles, GuildStarboard, GuildUsers
from attubot.logging import get_logger
from attubot.signals import send_signal
from attubot.web.app import config
from attubot.web.audit import ConfigChange, compare_configs, get_client_ip
from attubot.web.discord_integration import get_guild_channels, get_guild_info, get_guild_roles, get_users_info, invalidate_guild_cache
from attubot.web.forms import GuildConfigForm, SystemConfigForm, ThemeConfigForm

logger = get_logger(__name__)


def register_routes(app: Quart):  # noqa: PLR0915
    """Register all routes with the Quart app"""

    # ========== Page Routes ==========

    @app.route('/')
    async def index():
        """Dashboard - guild overview"""
        guilds = []
        for guild_id in config.authorized_guilds:
            guild_config = config.guilds.get(guild_id)
            guilds.append({
                'id': guild_id,
                'name': str(guild_config) if guild_config else f'Guild {guild_id}',
                'configured': guild_id in config.valid_guilds,
            })
        return await render_template('index.html', title='Dashboard', guilds=guilds)

    @app.route('/guild/<int:guild_id>')
    async def guild_config_page(guild_id: int):
        """Guild configuration editor"""
        if guild_id not in config.authorized_guilds:
            return await render_template(
                'error.html',
                title='Unauthorized',
                error='This guild is not authorized',
            ), 403

        guild = config.guilds.get(guild_id)
        if not guild:
            return await render_template(
                'error.html',
                title='Not Found',
                error='Guild configuration not found',
            ), 404

        return await render_template(
            'guild_config.html',
            title=f'Guild Configuration - {guild}',
            guild_id=guild_id,
            guild_name=str(guild),
        )

    @app.route('/theme')
    async def theme_config_page():
        """Theme configuration editor"""
        return await render_template('theme_config.html', title='Theme Configuration')

    @app.route('/system')
    async def system_config_page():
        """System configuration editor"""
        return await render_template('system_config.html', title='System Configuration')

    @app.route('/audit')
    async def audit_log_page():
        """Audit log viewer"""
        return await render_template('audit_log.html', title='Audit Log')

    # ========== New Bootstrap Page Routes ==========

    @app.route('/guild/<int:guild_id>/years')
    async def years_page(guild_id: int):
        """Years viewer page"""
        if guild_id not in config.authorized_guilds:
            return await render_template(
                'error.html',
                title='Unauthorized',
                error='This guild is not authorized',
            ), 403

        guild = config.guilds.get(guild_id)
        if not guild:
            return await render_template(
                'error.html',
                title='Not Found',
                error='Guild configuration not found',
            ), 404

        return await render_template(
            'years.html',
            title=f'Years - {guild}',
            guild_id=guild_id,
            guild_name=str(guild),
        )

    @app.route('/guild/<int:guild_id>/markers')
    async def markers_page(guild_id: int):
        """Markers viewer page"""
        if guild_id not in config.authorized_guilds:
            return await render_template(
                'error.html',
                title='Unauthorized',
                error='This guild is not authorized',
            ), 403

        guild = config.guilds.get(guild_id)
        if not guild:
            return await render_template(
                'error.html',
                title='Not Found',
                error='Guild configuration not found',
            ), 404

        return await render_template(
            'markers.html',
            title=f'Markers - {guild}',
            guild_id=guild_id,
            guild_name=str(guild),
        )

    @app.route('/guild/<int:guild_id>/time')
    async def time_status_page(guild_id: int):
        """Time status page"""
        if guild_id not in config.authorized_guilds:
            return await render_template(
                'error.html',
                title='Unauthorized',
                error='This guild is not authorized',
            ), 403

        guild = config.guilds.get(guild_id)
        if not guild:
            return await render_template(
                'error.html',
                title='Not Found',
                error='Guild configuration not found',
            ), 404

        return await render_template(
            'time_status.html',
            title=f'Time Status - {guild}',
            guild_id=guild_id,
            guild_name=str(guild),
        )

    @app.route('/admin/stats')
    async def admin_stats_page():
        """Admin statistics page"""
        return await render_template('admin_stats.html', title='Statistics')

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

        # Fetch Discord users for marker name resolution
        marker_user_ids = [int(user_id) for user_id in guild.users.markers if user_id]
        users_info = await get_users_info(marker_user_ids) if marker_user_ids else []
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

            # Audit logging
            from attubot.web import app as web_app

            if web_app.audit_logger:
                new_config = {
                    'channels': guild.channels.model_dump(),
                    'epoch': guild.epoch.model_dump(),
                    'roles': guild.roles.model_dump(),
                    'users': guild.users.model_dump(),
                    'starboard': guild.starboard.model_dump(),
                }
                changes = compare_configs(old_config, new_config)
                if changes:
                    await web_app.audit_logger.log_change(
                        config_type='guild',
                        action='update',
                        changes=changes,
                        ip_address=get_client_ip(),
                        guild_id=guild_id,
                        success=True,
                    )

            logger.info(f'Guild {guild_id} configuration saved')

            return jsonify({
                'success': True,
                'message': 'Configuration saved successfully',
            })

        except ValidationError as e:
            logger.error(f'Validation error for guild {guild_id}: {e}')

            # Log failed attempt
            from attubot.web import app as web_app

            if web_app.audit_logger:
                await web_app.audit_logger.log_change(
                    config_type='guild',
                    action='update',
                    changes=[],
                    ip_address=get_client_ip(),
                    guild_id=guild_id,
                    success=False,
                    error_message=f'Validation error: {e!s}',
                )

            return jsonify({
                'error': 'Validation failed',
                'details': e.errors(),
            }), 400
        except Exception as e:
            logger.error(f'Error saving guild {guild_id}: {e}')

            # Log failed attempt
            from attubot.web import app as web_app

            if web_app.audit_logger:
                await web_app.audit_logger.log_change(
                    config_type='guild',
                    action='update',
                    changes=[],
                    ip_address=get_client_ip(),
                    guild_id=guild_id,
                    success=False,
                    error_message=str(e),
                )

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
                return jsonify({
                    'success': True,
                    'message': 'Configuration reloaded from database',
                })
            else:
                return jsonify({'error': 'Failed to reload configuration'}), 500
        except Exception as e:
            logger.error(f'Error reloading guild {guild_id}: {e}')
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
            'bot_color': theme.bot_color,
            'guild_color': theme.guild_color,
        })

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
                'bot_color': config.theme.bot_color,
                'guild_color': config.theme.guild_color,
            }

            # Update theme
            config.theme.rotation = validated.rotation
            config.theme.max_rate = validated.max_rate
            config.theme.bot_color = validated.bot_color
            config.theme.guild_color = validated.guild_color

            # Save to database
            await config.theme.save()
            await send_signal('theme')

            # Audit logging
            from attubot.web import app as web_app

            if web_app.audit_logger:
                new_config = {
                    'rotation': config.theme.rotation,
                    'max_rate': config.theme.max_rate,
                    'bot_color': config.theme.bot_color,
                    'guild_color': config.theme.guild_color,
                }
                changes = compare_configs(old_config, new_config)
                if changes:
                    await web_app.audit_logger.log_change(
                        config_type='theme',
                        action='update',
                        changes=changes,
                        ip_address=get_client_ip(),
                        success=True,
                    )

            logger.info('Theme configuration saved')

            return jsonify({
                'success': True,
                'message': 'Theme saved successfully',
            })

        except ValidationError as e:
            logger.error(f'Validation error for theme: {e}')

            # Log failed attempt
            from attubot.web import app as web_app

            if web_app.audit_logger:
                await web_app.audit_logger.log_change(
                    config_type='theme',
                    action='update',
                    changes=[],
                    ip_address=get_client_ip(),
                    success=False,
                    error_message=f'Validation error: {e!s}',
                )

            return jsonify({
                'error': 'Validation failed',
                'details': e.errors(),
            }), 400
        except Exception as e:
            logger.error(f'Error saving theme: {e}')

            # Log failed attempt
            from attubot.web import app as web_app

            if web_app.audit_logger:
                await web_app.audit_logger.log_change(
                    config_type='theme',
                    action='update',
                    changes=[],
                    ip_address=get_client_ip(),
                    success=False,
                    error_message=str(e),
                )

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
                'error_hook': config.error_hook or '',
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

            # Audit logging
            from attubot.web import app as web_app

            if web_app.audit_logger:
                new_config = {
                    'primary_guild': config.primary_guild,
                    'error_log_guild': config.error_log[0] if config.error_log else 0,
                    'error_log_channel': config.error_log[1] if config.error_log else 0,
                    'error_hook': config.error_hook or '',
                }
                changes = compare_configs(old_config, new_config)
                if changes:
                    await web_app.audit_logger.log_change(
                        config_type='system',
                        action='update',
                        changes=changes,
                        ip_address=get_client_ip(),
                        success=True,
                    )

            logger.info('System configuration saved')

            return jsonify({
                'success': True,
                'message': 'System configuration saved successfully',
            })

        except ValidationError as e:
            logger.error(f'Validation error for system config: {e}')

            # Log failed attempt
            from attubot.web import app as web_app

            if web_app.audit_logger:
                await web_app.audit_logger.log_change(
                    config_type='system',
                    action='update',
                    changes=[],
                    ip_address=get_client_ip(),
                    success=False,
                    error_message=f'Validation error: {e!s}',
                )

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
            logger.error(f'Error saving system config: {e}')

            # Log failed attempt
            from attubot.web import app as web_app

            if web_app.audit_logger:
                await web_app.audit_logger.log_change(
                    config_type='system',
                    action='update',
                    changes=[],
                    ip_address=get_client_ip(),
                    success=False,
                    error_message=str(e),
                )

            return jsonify({'error': 'Failed to save system configuration'}), 500

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
            logger.error(f'Error fetching audit logs: {e}')
            return jsonify({'error': 'Failed to fetch audit logs'}), 500

    # ========== API Routes - Years ==========

    @app.route('/api/guilds/<int:guild_id>/years')
    async def api_get_years(guild_id: int):
        """Get all year records for a guild"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.years import Year

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
                    'formatted': y.formatted,
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
            logger.error(f'Error fetching years for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch years'}), 500

    @app.route('/api/guilds/<int:guild_id>/years/<int:year>')
    async def api_get_year(guild_id: int, year: int):
        """Get specific year record"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.years import Year

            year_record = await Year.get(guild_id, year)
            if not year_record:
                return jsonify({'error': f'Year {year} not found'}), 404

            return jsonify({
                'guild': str(year_record.guild),
                'year': year_record.year,
                'start_time': year_record.start_time,
                'end_time': year_record.end_time,
                'duration': year_record.duration,
                'formatted': year_record.formatted,
                'notes': year_record.notes,
            })

        except Exception as e:
            logger.error(f'Error fetching year {year} for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch year'}), 500

    @app.route('/api/guilds/<int:guild_id>/years/latest')
    async def api_get_latest_year(guild_id: int):
        """Get the most recent year record"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.years import Year

            year_record = await Year.get_latest(guild_id)
            if not year_record:
                return jsonify({'error': 'No years found'}), 404

            return jsonify({
                'guild': str(year_record.guild),
                'year': year_record.year,
                'start_time': year_record.start_time,
                'end_time': year_record.end_time,
                'duration': year_record.duration,
                'formatted': year_record.formatted,
                'notes': year_record.notes,
            })

        except Exception as e:
            logger.error(f'Error fetching latest year for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch latest year'}), 500

    @app.route('/api/guilds/<int:guild_id>/years/<int:year>', methods=['POST'])
    async def api_create_year(guild_id: int, year: int):
        """Create/update year record"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.years import Year

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
                    formatted=data.get('formatted', existing.formatted),
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
                    formatted=data.get('formatted', f'Year {year} PC'),
                    notes=data.get('notes', ''),
                )
                await new_year.save()
                message = f'Year {year} created successfully'

            # Audit log
            from attubot.web import app as web_app

            if web_app.audit_logger:
                await web_app.audit_logger.log_change(
                    config_type='year',
                    action='create' if not existing else 'update',
                    changes=[ConfigChange(field='year_data', old_value=str(existing) if existing else None, new_value=str(data))],
                    ip_address=get_client_ip(),
                    guild_id=guild_id,
                    success=True,
                )

            logger.info(f'{message} for guild {guild_id}')
            return jsonify({'success': True, 'message': message})

        except Exception as e:
            logger.error(f'Error creating/updating year {year} for guild {guild_id}: {e}')
            return jsonify({'error': 'Internal server error'}), 500

    @app.route('/api/guilds/<int:guild_id>/years/<int:year>', methods=['DELETE'])
    async def api_delete_year(guild_id: int, year: int):
        """Delete year record"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.years import Year

            existing = await Year.get(guild_id, year)
            if not existing:
                return jsonify({'error': f'Year {year} not found'}), 404

            await existing.delete()

            # Audit log
            from attubot.web import app as web_app

            if web_app.audit_logger:
                await web_app.audit_logger.log_change(
                    config_type='year',
                    action='delete',
                    changes=[ConfigChange(field='year', old_value=year, new_value=None)],
                    ip_address=get_client_ip(),
                    guild_id=guild_id,
                    success=True,
                )

            logger.info(f'Year {year} deleted for guild {guild_id}')
            return jsonify({'success': True, 'message': f'Year {year} deleted successfully'})

        except Exception as e:
            logger.error(f'Error deleting year {year} for guild {guild_id}: {e}')
            return jsonify({'error': 'Internal server error'}), 500

    # ========== API Routes - Markers ==========

    @app.route('/api/guilds/<int:guild_id>/markers')
    async def api_get_markers(guild_id: int):
        """Get all markers for a guild"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.markers import YearMarker

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
            logger.error(f'Error fetching markers for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch markers'}), 500

    @app.route('/api/guilds/<int:guild_id>/markers/<int:year>')
    async def api_get_marker(guild_id: int, year: int):
        """Get specific marker for a year"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.markers import YearMarker

            # Note: markers use channel field as guild reference
            marker = await YearMarker.get(guild_id, year)
            if not marker:
                return jsonify({'error': f'Marker for year {year} not found'}), 404

            return jsonify({
                'channel': str(marker.channel),
                'message': str(marker.message),
                'year': marker.year,
                'exact': marker.exact,
                'wiki_page': marker.wiki_page,
            })

        except Exception as e:
            logger.error(f'Error fetching marker for year {year} in guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch marker'}), 500

    @app.route('/api/guilds/<int:guild_id>/markers/<int:year>/timestamp')
    async def api_get_marker_timestamp(guild_id: int, year: int):
        """Get timestamp from marker snowflake"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.markers import YearMarker

            timestamp = await YearMarker.timestamp(year, guild_id)
            if timestamp is None:
                return jsonify({'error': f'Marker for year {year} not found'}), 404

            return jsonify({
                'year': year,
                'timestamp': timestamp,
            })

        except Exception as e:
            logger.error(f'Error fetching marker timestamp for year {year} in guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch marker timestamp'}), 500

    @app.route('/api/guilds/<int:guild_id>/markers/<int:year>', methods=['POST'])
    async def api_create_marker(guild_id: int, year: int):
        """Create/update marker"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.markers import YearMarker

            data = await request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            # Validate required fields
            if 'message' not in data:
                return jsonify({'error': 'message (Discord message ID) is required'}), 400

            # Channel defaults to guild_id (as per markers.py convention)
            channel = int(data.get('channel', guild_id))
            message = int(data['message'])

            # Get existing marker or create new
            existing = await YearMarker.get(channel, year)

            if existing:
                # Update existing marker
                await existing.update(
                    message=message,
                    exact=data.get('exact', existing.exact),
                    wiki_page=data.get('wiki_page', existing.wiki_page),
                )
                msg = f'Marker for year {year} updated successfully'
            else:
                # Create new marker
                new_marker = YearMarker(
                    channel=channel,
                    message=message,
                    guild=guild_id,
                    year=year,
                    exact=data.get('exact', False),
                    wiki_page=data.get('wiki_page', False),
                )
                await new_marker.save()
                msg = f'Marker for year {year} created successfully'

            # Audit log
            from attubot.web import app as web_app

            if web_app.audit_logger:
                await web_app.audit_logger.log_change(
                    config_type='marker',
                    action='create' if not existing else 'update',
                    changes=[ConfigChange(field='marker_data', old_value=str(existing) if existing else None, new_value=str(data))],
                    ip_address=get_client_ip(),
                    guild_id=guild_id,
                    success=True,
                )

            logger.info(f'{msg} for guild {guild_id}')
            return jsonify({'success': True, 'message': msg})

        except Exception as e:
            logger.error(f'Error creating/updating marker for year {year} in guild {guild_id}: {e}')
            return jsonify({'error': 'Internal server error'}), 500

    @app.route('/api/guilds/<int:guild_id>/markers/<int:year>', methods=['DELETE'])
    async def api_delete_marker(guild_id: int, year: int):
        """Delete marker"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.markers import YearMarker

            # Note: markers use channel field as guild reference
            # Channel defaults to guild_id if not provided (matching POST behavior)
            channel_str = request.args.get('channel')
            channel = int(channel_str) if channel_str else guild_id
            existing = await YearMarker.get(channel, year)
            if not existing:
                return jsonify({'error': f'Marker for year {year} not found'}), 404

            await existing.delete()

            # Audit log
            from attubot.web import app as web_app

            if web_app.audit_logger:
                await web_app.audit_logger.log_change(
                    config_type='marker',
                    action='delete',
                    changes=[ConfigChange(field='marker', old_value=year, new_value=None)],
                    ip_address=get_client_ip(),
                    guild_id=guild_id,
                    success=True,
                )

            logger.info(f'Marker for year {year} deleted for guild {guild_id}')
            return jsonify({'success': True, 'message': f'Marker for year {year} deleted successfully'})

        except Exception as e:
            logger.error(f'Error deleting marker for year {year} in guild {guild_id}: {e}')
            return jsonify({'error': 'Internal server error'}), 500

    # ========== API Routes - Time/Calendar ==========

    @app.route('/api/guilds/<int:guild_id>/time')
    async def api_get_time_status(guild_id: int):
        """Get current time status for a guild"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.calendar import get_next_year, get_year_status

            guild_config = config.guilds.get(guild_id)
            if not guild_config:
                return jsonify({'error': 'Guild not configured'}), 404

            elapsed_days, current_year = get_year_status(guild_id)
            next_rollover = get_next_year(guild_id)

            # Get rollover time as string
            rollover_time = guild_config.epoch.get_rollover_time()
            rollover_str = rollover_time.strftime('%H:%M')

            return jsonify({
                'guild_id': str(guild_id),
                'current_year': current_year,
                'elapsed_days': elapsed_days,
                'current_day': (elapsed_days % guild_config.epoch.length) + 1,
                'next_rollover': int(next_rollover.timestamp()),
                'next_rollover_formatted': next_rollover.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'paused': guild_config.epoch.paused,
                'year_length': guild_config.epoch.length,
                'rollover_time': rollover_str,
                'rollover_minutes': guild_config.epoch.rollover_minutes,
                'epoch_time': guild_config.epoch.time,
                'epoch_year': guild_config.epoch.year,
            })

        except Exception as e:
            logger.error(f'Error fetching time status for guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch time status'}), 500

    @app.route('/api/guilds/<int:guild_id>/time/year-span/<int:year>')
    async def api_get_year_span(guild_id: int, year: int):
        """Get time span (start/end/duration) for a specific year"""
        if guild_id not in config.authorized_guilds:
            return jsonify({'error': 'Unauthorized guild'}), 403

        try:
            from attubot.calendar import get_year_span

            span = await get_year_span(year, guild_id)

            return jsonify({
                'guild_id': str(guild_id),
                'year': year,
                'start_time': span.start_time,
                'end_time': span.end_time,
                'duration': span.duration,
            })

        except Exception as e:
            logger.error(f'Error fetching year span for year {year} in guild {guild_id}: {e}')
            return jsonify({'error': 'Failed to fetch year span'}), 500

    # ========== API Routes - Admin Stats ==========

    @app.route('/api/admin/stats')
    async def api_get_admin_stats():
        """Get system statistics"""
        try:
            from attubot import db
            from attubot.markers import YearMarker
            from attubot.years import Year

            # Collect statistics
            total_guilds = len(config.authorized_guilds)
            configured_guilds = len(config.valid_guilds)

            # Count years, markers, and stars across all guilds
            total_years = 0
            total_markers = 0
            total_starred_messages = 0
            total_stars = 0
            from attubot.starboard import _get_repo as _get_sb_repo

            try:
                sb_repo = _get_sb_repo()
                for guild_id in config.authorized_guilds:
                    total_years += await Year.total(guild_id)
                    total_markers += await YearMarker.total(guild_id)
                    total_starred_messages += await sb_repo.total_for_guild(guild_id)
                    total_stars += await sb_repo.sum_reactions_for_guild(guild_id)
            except RuntimeError:
                # starboard not yet initialized (e.g. web-only mode)
                for guild_id in config.authorized_guilds:
                    total_years += await Year.total(guild_id)
                    total_markers += await YearMarker.total(guild_id)

            # Database connection status
            try:
                db_connected = db.get_db() is not None
            except Exception:
                db_connected = False

            # Config status
            config_loaded = config._get_event('load').is_set()

            # Uptime (if available)
            import time

            uptime_seconds = int(time.time() - config._init_time) if hasattr(config, '_init_time') else 0

            return jsonify({
                'guilds': {
                    'total': total_guilds,
                    'configured': configured_guilds,
                    'authorized': list(str(g) for g in config.authorized_guilds),
                },
                'data': {
                    'total_years': total_years,
                    'total_markers': total_markers,
                    'total_starred_messages': total_starred_messages,
                    'total_stars': total_stars,
                },
                'system': {
                    'db_connected': db_connected,
                    'config_loaded': config_loaded,
                    'uptime_seconds': uptime_seconds,
                    'primary_guild': str(config.primary_guild),
                    'config_version': config.config_version,
                },
            })

        except Exception as e:
            logger.error(f'Error fetching admin stats: {e}')
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

    logger.info('Routes registered')
