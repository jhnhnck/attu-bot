"""
AttuBot - Chat web routes (dormant)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

mounts /chat (page) and /api/chat (GET/POST) on a Quart app. invoke from the
bot's web app via `register_chat_routes(app)` once chat is revived. while chat
is disabled, this module is unreferenced.
"""

from pydantic import ValidationError
from quart import Quart, jsonify, render_template, request

from attu_chat.web.forms import ChatConfigForm
from attu_models import ChatChannelConfig, ChatConfigDocument
from attubot.logging import get_logger
from attubot.signals import send_signal
from attubot.web.app import config
from attubot.web.audit import compare_configs, log_audit


logger = get_logger(__name__)


def register_chat_routes(app: Quart) -> None:
    """register chat config page + api routes on the bot's web app."""

    @app.route('/chat')
    async def chat_config_page():
        """Chat runtime configuration editor"""
        return await render_template('chat_config.html', title='chat')

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

            rt = config.chat_runtime
            old_config = rt.model_dump()

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
