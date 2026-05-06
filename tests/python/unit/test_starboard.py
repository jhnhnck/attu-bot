"""
AttuBot - Starboard Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from doom_bot.client.starboard import (
    _check_and_announce_sweep,
    _count_streak,
    _fmt_count,
    _hydrate_stored_embed,
    _is_image,
    _looks_like_image_url,
    _parse_color,
    _should_merge_stored_embed,
    _sweep_message,
    _weighted_count,
    build_content,
    build_embeds,
    dominant_color,
    parse_jump_url,
    parse_starboard_content,
)
from doom_bot.database.models import MessageAuthor, MessageContent, MessageDocument, MessageRefs, StarredMessageDocument


# ---- constants ----

# real guild/channel/message IDs from the dump - used only for pure function tests
real_guild = 1001828025756819456
real_channel = 1001829427409334292
real_message = 1293683225524179035

# synthetic IDs used for integration tests (must match make_guild() default)
test_guild = 1234567890
test_channel = 5555555555
test_starboard_channel = 9999999999
test_message = 111000111000111000
test_starboard_msg = 222000222000222000
test_author = 573360359566737409
user_a = 100000001
user_b = 100000002
user_c = 100000003

emoji_star = '⭐'
emoji_color = '#EEDD20'
emoji_map = {emoji_star: emoji_color}

# convenience for pure function tests
guild = real_guild
channel = real_channel
message = real_message
jump_url = f'https://discord.com/channels/{guild}/{channel}/{message}'


# ---- pure function unit tests ----


def test_parse_color_standard():
    assert _parse_color('#EEDD20') == 0xEEDD20


def test_parse_color_without_hash():
    assert _parse_color('EEDD20') == 0xEEDD20


def test_build_content_single_emoji():
    reactions = {emoji_star: [user_a, user_b, user_c]}
    result = build_content(reactions, jump_url, emoji_map)
    assert result == f'{emoji_star} **3** | {jump_url}'


def test_build_content_multiple_emojis_sorted_by_count():
    emoji2 = '🌟'
    reactions = {emoji_star: [user_a, user_b], emoji2: [user_a, user_b, user_c]}
    emoji_map = {emoji_star: '#EEDD20', emoji2: '#FF0000'}
    result = build_content(reactions, jump_url, emoji_map)
    # emoji2 has 3 reactions vs star's 2, so emoji2 should come first
    assert result.startswith(f'{emoji2} **3** | {emoji_star} **2**')
    assert result.endswith(jump_url)


def test_build_content_skips_unconfigured_emojis():
    reactions = {emoji_star: [user_a], '❤️': [user_b]}  # ❤️ not configured
    result = build_content(reactions, jump_url, emoji_map)
    assert '❤️' not in result
    assert emoji_star in result


def test_build_content_skips_empty_reaction_lists():
    reactions = {emoji_star: [], '🌟': [user_a]}
    emoji_map = {emoji_star: '#EEDD20', '🌟': '#FF0000'}
    result = build_content(reactions, jump_url, emoji_map)
    assert emoji_star not in result
    assert '🌟' in result


def test_dominant_color_single_emoji():
    reactions = {emoji_star: [user_a, user_b]}
    assert dominant_color(reactions, emoji_map) == 0xEEDD20


def test_dominant_color_returns_highest_count_emoji():
    emoji2 = '🌟'
    reactions = {emoji_star: [user_a], emoji2: [user_a, user_b]}
    emoji_map = {emoji_star: '#EEDD20', emoji2: '#FF0000'}
    assert dominant_color(reactions, emoji_map) == 0xFF0000


def test_dominant_color_fallback_when_no_configured_emoji():
    reactions = {'❤️': [user_a]}  # not in emoji_map
    fallback = 0xABCDEF
    assert dominant_color(reactions, emoji_map, fallback=fallback) == fallback


def test_dominant_color_fallback_when_all_lists_empty():
    reactions = {emoji_star: []}
    assert dominant_color(reactions, emoji_map, fallback=0x123456) == 0x123456


def test_parse_jump_url_valid():
    result = parse_jump_url(jump_url)
    assert result == (guild, channel, message)


def test_parse_jump_url_invalid():
    assert parse_jump_url('https://example.com/not-a-jump-url') is None
    assert parse_jump_url('') is None


def test_parse_starboard_content_single_emoji():
    content = f'{emoji_star} **4** | {jump_url}'
    counts, url = parse_starboard_content(content)
    assert counts == {emoji_star: 4}
    assert url == jump_url


def test_parse_starboard_content_multiple_emojis():
    emoji2 = '🌟'
    content = f'{emoji_star} **4** | {emoji2} **1** | {jump_url}'
    counts, url = parse_starboard_content(content)
    assert counts == {emoji_star: 4, emoji2: 1}
    assert url == jump_url


def test_parse_starboard_content_no_url():
    _, url = parse_starboard_content(f'{emoji_star} **3** | no url here')
    assert url is None


def test_parse_starboard_content_real_example():
    content = '\u2b50 **4** | https://discord.com/channels/1001828025756819456/1001829427409334292/1293683225524179035'
    counts, url = parse_starboard_content(content)
    assert '⭐' in counts
    assert counts['⭐'] == 4
    assert url == 'https://discord.com/channels/1001828025756819456/1001829427409334292/1293683225524179035'


def test_is_image_true():
    assert _is_image({'url': 'https://cdn.example.com/img.png', 'content_type': 'image/png'})
    assert _is_image({'url': 'https://cdn.example.com/img.gif', 'content_type': 'image/gif'})


def test_is_image_false_no_url():
    assert not _is_image({'content_type': 'image/png'})


def test_is_image_false_non_image():
    assert not _is_image({'url': 'https://cdn.example.com/file.pdf', 'content_type': 'application/pdf'})


def test_is_image_false_empty_content_type():
    assert not _is_image({'url': 'https://cdn.example.com/file', 'content_type': ''})


def test_is_image_true_without_content_type_ext():
    assert _is_image({'url': 'https://cdn.example.com/file.png', 'content_type': ''})


def test_looks_like_image_url_false_without_ext():
    assert not _looks_like_image_url('https://cdn.example.com/file?size=1')


def test_should_merge_stored_embed_description_only():
    stored = {'description': 'preview', 'image_url': 'https://cdn.example.com/1.png'}
    assert _should_merge_stored_embed(stored)


def test_should_not_merge_when_title_present():
    stored = {'description': 'preview', 'title': 'Title'}
    assert not _should_merge_stored_embed(stored)


def test_hydrate_stored_embed_populates_all_fields():
    stored = {
        'title': 'Title',
        'description': 'desc',
        'url': 'https://example.com',
        'color': 0xFF00FF,
        'image_url': 'https://example.com/img.png',
        'fields': [{'name': 'Field', 'value': 'Value', 'inline': True}],
        'footer_text': 'Footer',
        'footer_icon_url': 'https://example.com/icon.png',
        'author_name': 'Author',
        'author_url': 'https://example.com/author',
        'author_icon_url': 'https://example.com/avatar.png',
        'timestamp': datetime.now(tz=UTC).isoformat(),
    }
    embed = _hydrate_stored_embed(stored)
    assert embed.title == 'Title'
    assert embed.description == 'desc'
    assert embed.url == 'https://example.com'
    assert embed.color.value == 0xFF00FF
    assert embed.image.url == 'https://example.com/img.png'
    assert embed.fields[0].name == 'Field'
    assert embed.footer.text == 'Footer'
    assert embed.author.name == 'Author'


@pytest.mark.asyncio
async def test_build_embeds_merges_link_preview_with_empty_content(monkeypatch):
    msg_doc = _make_msg_doc(content='', embeds=[{'description': 'preview text'}])
    mock_user = MagicMock()
    mock_avatar = MagicMock()
    mock_avatar.__str__.return_value = 'avatar_url'
    mock_user.display_avatar = mock_avatar
    monkeypatch.setattr('doom_bot.bot', MagicMock(get_user=MagicMock(return_value=mock_user)))

    embeds = await build_embeds(msg_doc, test_guild, 0xEEDD20)
    assert embeds[0].description == 'preview text'


@pytest.mark.asyncio
async def test_build_embeds_forwarded_sets_footer(monkeypatch):
    msg_doc = _make_msg_doc(content='this was forwarded', forwarded=True)
    mock_user = MagicMock()
    mock_avatar = MagicMock()
    mock_avatar.__str__.return_value = 'avatar_url'
    mock_user.display_avatar = mock_avatar
    monkeypatch.setattr('doom_bot.bot', MagicMock(get_user=MagicMock(return_value=mock_user)))

    embeds = await build_embeds(msg_doc, test_guild, 0xEEDD20)
    assert embeds[0].footer.text == 'forwarded message'


@pytest.mark.asyncio
async def test_build_embeds_not_forwarded_no_footer(monkeypatch):
    msg_doc = _make_msg_doc(content='regular message', forwarded=False)
    mock_user = MagicMock()
    mock_avatar = MagicMock()
    mock_avatar.__str__.return_value = 'avatar_url'
    mock_user.display_avatar = mock_avatar
    monkeypatch.setattr('doom_bot.bot', MagicMock(get_user=MagicMock(return_value=mock_user)))

    embeds = await build_embeds(msg_doc, test_guild, 0xEEDD20)
    assert embeds[0].footer is None


# ---- make_message_doc helper ----


def _make_msg_doc(**kwargs) -> MessageDocument:
    return MessageDocument(
        message_id=kwargs.pop('message_id', test_message),
        guild_id=kwargs.pop('guild_id', test_guild),
        channel_id=kwargs.pop('channel_id', test_channel),
        parent_channel_id=kwargs.pop('parent_channel_id', None),
        author=MessageAuthor(
            id=kwargs.pop('author_id', test_author),
            name=kwargs.pop('author_name', 'TestUser'),
            bot=kwargs.pop('author_bot', False),
        ),
        content=MessageContent(
            text=kwargs.pop('content', 'hello world'),
            attachments=kwargs.pop('attachments', []),
            embeds=kwargs.pop('embeds', []),
            sticker_ids=kwargs.pop('sticker_ids', []),
            forwarded=kwargs.pop('forwarded', False),
        ),
        refs=MessageRefs(
            reply_to=kwargs.pop('reference_id', None),
            starboard_post=kwargs.pop('starboard_reference_id', None),
        ),
        created_at=kwargs.pop('created_at', 1704067200),
        **kwargs,
    )


def _make_star_doc(**kwargs) -> StarredMessageDocument:
    defaults = {
        'message_id': test_message,
        'channel_id': test_channel,
        'guild_id': test_guild,
        'author_id': test_author,
    }
    defaults.update(kwargs)
    return StarredMessageDocument(**defaults)  # pyright: ignore[reportArgumentType]


# ---- handle_star_add integration tests ----


@pytest.fixture
def mock_sb_repo():
    repo = AsyncMock()
    with patch('doom_bot.client.starboard._starboard_repo', repo):
        yield repo


@pytest.fixture
def mock_sb_and_msg_repos(mock_sb_repo):
    msg_repo = AsyncMock()
    with patch('doom_bot.client.messages._message_repo', msg_repo):
        yield mock_sb_repo, msg_repo


@pytest.fixture
def make_starboard_guild(make_guild):
    """Create a guild with a configured starboard."""

    def _make(**kwargs):
        cfg = make_guild()
        from doom_bot.config import GuildStarboard

        cfg.starboard = GuildStarboard(channel_id=test_starboard_channel, emojis={emoji_star: emoji_color})
        return cfg

    return _make


async def test_handle_star_add_self_star_ignored(make_starboard_guild, mock_sb_and_msg_repos):
    from doom_bot.client.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    # author stars their own message
    msg_doc = _make_msg_doc(author_id=user_a)
    msg_repo.get = AsyncMock(return_value=msg_doc)

    await handle_star_add(test_guild, test_channel, test_message, user_id=user_a, emoji_str=emoji_star)

    sb_repo.add_reaction.assert_not_called()


async def test_handle_star_add_unconfigured_emoji_ignored(make_starboard_guild, mock_sb_and_msg_repos):
    from doom_bot.client.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    await handle_star_add(test_guild, test_channel, test_message, user_id=user_a, emoji_str='❤️')

    sb_repo.add_reaction.assert_not_called()
    msg_repo.get.assert_not_called()


async def test_handle_star_add_creates_document_and_adds_reaction(make_starboard_guild, mock_sb_and_msg_repos):
    from doom_bot.client.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    msg_doc = _make_msg_doc(author_id=test_author)
    msg_repo.get = AsyncMock(return_value=msg_doc)
    sb_repo.get = AsyncMock(return_value=None)  # no existing document

    updated = _make_star_doc(reactions={emoji_star: [user_a]}, total_reactions=1)
    sb_repo.add_reaction = AsyncMock(return_value=updated)

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
        await handle_star_add(test_guild, test_channel, test_message, user_id=user_a, emoji_str=emoji_star)

    sb_repo.upsert.assert_called_once()
    sb_repo.add_reaction.assert_called_once_with(test_message, emoji_star, user_a)
    mock_sync.assert_called_once()


async def test_handle_star_add_reaction_on_starboard_post_resolves_original(make_starboard_guild, mock_sb_and_msg_repos):
    from doom_bot.client.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    # existing doc links starboard post -> original message
    existing_doc = _make_star_doc(starboard_message_id=test_starboard_msg, message_id=test_message)
    sb_repo.get_by_starboard_message = AsyncMock(return_value=existing_doc)

    msg_doc = _make_msg_doc(author_id=test_author)
    msg_repo.get = AsyncMock(return_value=msg_doc)
    sb_repo.get = AsyncMock(return_value=existing_doc)

    updated = _make_star_doc(reactions={emoji_star: [user_a]}, total_reactions=1)
    sb_repo.add_reaction = AsyncMock(return_value=updated)

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock):
        # reaction is on the STARBOARD channel/message, not the original
        await handle_star_add(test_guild, test_starboard_channel, test_starboard_msg, user_id=user_a, emoji_str=emoji_star)

    sb_repo.get_by_starboard_message.assert_called_once_with(test_starboard_msg)
    sb_repo.add_reaction.assert_called_once_with(test_message, emoji_star, user_a)


async def test_handle_star_add_message_not_in_db_ignored(make_starboard_guild, mock_sb_and_msg_repos):
    from doom_bot.client.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    msg_repo.get = AsyncMock(return_value=None)

    await handle_star_add(test_guild, test_channel, test_message, user_id=user_a, emoji_str=emoji_star)

    sb_repo.add_reaction.assert_not_called()


async def test_handle_star_remove_updates_document(make_starboard_guild, mock_sb_and_msg_repos):
    from doom_bot.client.starboard import handle_star_remove

    sb_repo, _ = mock_sb_and_msg_repos
    make_starboard_guild()

    updated = _make_star_doc(reactions={emoji_star: []}, total_reactions=0)
    sb_repo.remove_reaction = AsyncMock(return_value=updated)

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
        await handle_star_remove(test_guild, test_channel, test_message, user_id=user_a, emoji_str=emoji_star)

    sb_repo.remove_reaction.assert_called_once_with(test_message, emoji_star, user_a)
    mock_sync.assert_called_once()


async def test_handle_star_remove_bot_initiated_ignored(make_starboard_guild, mock_sb_and_msg_repos):
    """bot-initiated removals (self-star, duplicate cleanup) must not decrement the original message's reactions"""
    from doom_bot.client.starboard import _pending_bot_removals, handle_star_remove

    sb_repo, _msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    # simulate the bot registering a pending removal (as _remove_reaction_from_discord does)
    _pending_bot_removals.add((test_starboard_channel, test_starboard_msg, user_a, emoji_star))

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
        await handle_star_remove(test_guild, test_starboard_channel, test_starboard_msg, user_id=user_a, emoji_str=emoji_star)

    # the pending key should be consumed and no DB mutation should happen
    assert (test_starboard_channel, test_starboard_msg, user_a, emoji_star) not in _pending_bot_removals
    sb_repo.remove_reaction.assert_not_called()
    mock_sync.assert_not_called()


async def test_handle_star_remove_user_initiated_on_starboard_post(make_starboard_guild, mock_sb_and_msg_repos):
    """user manually removing their reaction from the starboard post should decrement the original"""
    from doom_bot.client.starboard import handle_star_remove

    sb_repo, _msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    # starboard post links back to original message
    existing_doc = _make_star_doc(starboard_message_id=test_starboard_msg, message_id=test_message)
    sb_repo.get_by_starboard_message = AsyncMock(return_value=existing_doc)

    # no pending key — this is a real user action, not bot-initiated
    updated_doc = _make_star_doc(message_id=test_message)
    sb_repo.remove_reaction = AsyncMock(return_value=updated_doc)

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
        await handle_star_remove(test_guild, test_starboard_channel, test_starboard_msg, user_id=user_b, emoji_str=emoji_star)

    sb_repo.remove_reaction.assert_called_once_with(test_message, emoji_star, user_b)
    mock_sync.assert_called_once()


# ---- one-vote-per-user, auto-remove, and threshold tests ----

emoji_glow = '🌟'
emoji_glow_color = '#FF0000'
response_msg_id = 333000333000333000


async def test_handle_star_add_second_emoji_ignored_when_user_already_voted(make_starboard_guild, mock_sb_and_msg_repos):
    from doom_bot.client.starboard import handle_star_add
    from doom_bot.config import GuildStarboard

    sb_repo, msg_repo = mock_sb_and_msg_repos
    cfg = make_starboard_guild()
    cfg.starboard = GuildStarboard(channel_id=test_starboard_channel, emojis={emoji_star: emoji_color, emoji_glow: emoji_glow_color})

    msg_doc = _make_msg_doc(author_id=test_author)
    msg_repo.get = AsyncMock(return_value=msg_doc)

    existing_doc = _make_star_doc(reactions={emoji_star: [user_a]})
    sb_repo.get = AsyncMock(return_value=existing_doc)

    with patch('doom_bot.client.starboard._remove_reaction_from_discord', new_callable=AsyncMock) as mock_remove, patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
        await handle_star_add(test_guild, test_channel, test_message, user_id=user_a, emoji_str=emoji_glow)

    sb_repo.add_reaction.assert_not_called()
    mock_sync.assert_not_called()
    mock_remove.assert_called_once_with(test_channel, test_message, user_a, emoji_glow)


async def test_handle_star_add_self_star_auto_removes(make_starboard_guild, mock_sb_and_msg_repos):
    from doom_bot.client.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    msg_doc = _make_msg_doc(author_id=user_a)  # reactor IS the author
    msg_repo.get = AsyncMock(return_value=msg_doc)
    sb_repo.get = AsyncMock(return_value=None)

    with patch('doom_bot.client.starboard._remove_reaction_from_discord', new_callable=AsyncMock) as mock_remove:
        await handle_star_add(test_guild, test_channel, test_message, user_id=user_a, emoji_str=emoji_star)

    mock_remove.assert_called_once_with(test_channel, test_message, user_a, emoji_star)
    sb_repo.add_reaction.assert_not_called()


async def test_handle_star_add_self_star_on_star_response_uses_orig_ids(make_starboard_guild, mock_sb_and_msg_repos):
    """self-star via a /star response message must remove from the response msg id, not the original"""
    from doom_bot.client.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    response_doc = _make_msg_doc(message_id=response_msg_id, author_id=test_author, starboard_reference_id=test_message)
    original_doc = _make_msg_doc(message_id=test_message, author_id=user_a)

    def _msg_get(mid):
        return response_doc if mid == response_msg_id else original_doc

    msg_repo.get = AsyncMock(side_effect=_msg_get)
    sb_repo.get = AsyncMock(return_value=None)

    with patch('doom_bot.client.starboard._remove_reaction_from_discord', new_callable=AsyncMock) as mock_remove:
        await handle_star_add(test_guild, test_channel, response_msg_id, user_id=user_a, emoji_str=emoji_star)

    # remove must target the response message the user actually reacted on
    mock_remove.assert_called_once_with(test_channel, response_msg_id, user_a, emoji_star)
    sb_repo.add_reaction.assert_not_called()


async def test_sync_no_post_when_two_emojis_from_same_user(make_starboard_guild, mock_sb_repo):
    from doom_bot.client.starboard import _sync_starboard_post
    from doom_bot.config import GuildStarboard

    cfg = make_starboard_guild()
    cfg.starboard = GuildStarboard(channel_id=test_starboard_channel, emojis={emoji_star: emoji_color, emoji_glow: emoji_glow_color})

    doc = _make_star_doc(reactions={emoji_star: [user_a], emoji_glow: [user_a]}, weighted_total=2.0)

    channel = AsyncMock()
    msg_doc = _make_msg_doc()

    with patch('doom_bot.client.core.bot') as mock_bot, patch('doom_bot.client.messages._message_repo') as mock_msg_repo, patch('doom_bot.client.starboard.build_embeds', new_callable=AsyncMock, return_value=[]):
        mock_bot.get_channel = MagicMock(return_value=channel)
        mock_msg_repo.get = AsyncMock(return_value=msg_doc)

        await _sync_starboard_post(test_guild, doc, cfg)

    channel.send.assert_not_called()


async def test_sync_creates_post_when_two_users_react_same_emoji(make_starboard_guild, mock_sb_repo):
    from doom_bot.client.starboard import _sync_starboard_post

    cfg = make_starboard_guild()
    doc = _make_star_doc(reactions={emoji_star: [user_a, user_b]}, weighted_total=2.0)

    sb_msg = AsyncMock()
    sb_msg.id = test_starboard_msg
    channel = AsyncMock()
    channel.send = AsyncMock(return_value=sb_msg)
    msg_doc = _make_msg_doc()

    with patch('doom_bot.client.core.bot') as mock_bot, patch('doom_bot.client.messages._message_repo') as mock_msg_repo, patch('doom_bot.client.starboard.build_embeds', new_callable=AsyncMock, return_value=[]), patch('doom_bot.client.starboard._check_and_announce_sweep', new_callable=AsyncMock):
        mock_bot.get_channel = MagicMock(return_value=channel)
        mock_msg_repo.get = AsyncMock(return_value=msg_doc)
        mock_sb_repo.set_starboard_message = AsyncMock()

        await _sync_starboard_post(test_guild, doc, cfg)

    channel.send.assert_called_once()


async def test_sync_deletes_post_when_falls_below_threshold(make_starboard_guild, mock_sb_repo):
    from doom_bot.client.starboard import _sync_starboard_post

    cfg = make_starboard_guild()
    # post exists but only one user reacted - max per-emoji weight is 1.0 < 2
    doc = _make_star_doc(reactions={emoji_star: [user_a]}, starboard_message_id=test_starboard_msg, weighted_total=1.0)

    sb_msg = AsyncMock()
    channel = AsyncMock()
    channel.get_partial_message = MagicMock(return_value=sb_msg)
    msg_doc = _make_msg_doc()

    with patch('doom_bot.client.core.bot') as mock_bot, patch('doom_bot.client.messages._message_repo') as mock_msg_repo, patch('doom_bot.client.starboard.build_embeds', new_callable=AsyncMock, return_value=[]):
        mock_bot.get_channel = MagicMock(return_value=channel)
        mock_msg_repo.get = AsyncMock(return_value=msg_doc)
        mock_sb_repo.set_starboard_message = AsyncMock()

        await _sync_starboard_post(test_guild, doc, cfg)

    sb_msg.delete.assert_called_once()
    mock_sb_repo.set_starboard_message.assert_called_once_with(test_message, None)
    sb_msg.edit.assert_not_called()


async def test_sync_does_not_delete_post_at_threshold(make_starboard_guild, mock_sb_repo):
    from doom_bot.client.starboard import _sync_starboard_post

    cfg = make_starboard_guild()
    # post exists and two users reacted - max per-emoji weight is 2.0 >= 2
    doc = _make_star_doc(reactions={emoji_star: [user_a, user_b]}, starboard_message_id=test_starboard_msg, weighted_total=2.0)

    sb_msg = AsyncMock()
    channel = AsyncMock()
    channel.get_partial_message = MagicMock(return_value=sb_msg)
    msg_doc = _make_msg_doc()

    with patch('doom_bot.client.core.bot') as mock_bot, patch('doom_bot.client.messages._message_repo') as mock_msg_repo, patch('doom_bot.client.starboard.build_embeds', new_callable=AsyncMock, return_value=[]):
        mock_bot.get_channel = MagicMock(return_value=channel)
        mock_msg_repo.get = AsyncMock(return_value=msg_doc)

        await _sync_starboard_post(test_guild, doc, cfg)

    sb_msg.edit.assert_called_once()
    sb_msg.delete.assert_not_called()


def _make_discord_reaction(emoji_str: str, users: list) -> MagicMock:
    """build a mock discord Reaction whose .users() is an async iterator of the given users."""
    reaction = MagicMock()
    reaction.emoji = emoji_str

    async def _iter():
        for u in users:
            yield u

    reaction.users = MagicMock(return_value=_iter())
    return reaction


def _make_discord_user(user_id: int, *, bot: bool = False) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.bot = bot
    return user


async def test_backfill_enforces_one_vote_per_user(make_starboard_guild, mock_sb_repo):
    """user who reacted with two emojis: only first emoji counted, second auto-removed"""
    from doom_bot.client.starboard import backfill_message_reactions
    from doom_bot.config import GuildStarboard

    cfg = make_starboard_guild()
    cfg.starboard = GuildStarboard(channel_id=test_starboard_channel, emojis={emoji_star: emoji_color, emoji_glow: emoji_glow_color})

    message = MagicMock()
    message.id = test_message
    message.author.id = test_author
    message.channel.id = test_channel
    message.reactions = [
        _make_discord_reaction(emoji_star, [_make_discord_user(user_a), _make_discord_user(user_b)]),
        _make_discord_reaction(emoji_glow, [_make_discord_user(user_a)]),
    ]
    message.remove_reaction = AsyncMock()

    mock_sb_repo.get = AsyncMock(return_value=None)
    mock_sb_repo.upsert = AsyncMock()

    with patch('doom_bot.client.messages._message_repo') as mock_msg_repo, patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock):
        mock_msg_repo.get = AsyncMock(return_value=None)
        await backfill_message_reactions(message, test_guild)

    upserted_doc = mock_sb_repo.upsert.call_args[0][0]
    assert user_a in upserted_doc.reactions.get(emoji_star, [])
    assert user_a not in upserted_doc.reactions.get(emoji_glow, [])
    # user_a's duplicate emoji_glow reaction should be auto-removed
    message.remove_reaction.assert_called_once()
    emoji_arg, obj_arg = message.remove_reaction.call_args.args
    assert emoji_arg == emoji_glow
    assert obj_arg.id == user_a


async def test_backfill_removes_self_stars(make_starboard_guild, mock_sb_repo):
    """author reacting to their own message is auto-removed during backfill"""
    from doom_bot.client.starboard import backfill_message_reactions

    make_starboard_guild()

    message = MagicMock()
    message.id = test_message
    message.author.id = test_author
    message.channel.id = test_channel
    message.reactions = [
        _make_discord_reaction(emoji_star, [_make_discord_user(test_author)]),
    ]
    message.remove_reaction = AsyncMock()

    mock_sb_repo.get = AsyncMock(return_value=None)

    with patch('doom_bot.client.messages._message_repo') as mock_msg_repo, patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock):
        mock_msg_repo.get = AsyncMock(return_value=None)
        await backfill_message_reactions(message, test_guild)

    message.remove_reaction.assert_called_once()
    emoji_arg, obj_arg = message.remove_reaction.call_args.args
    assert emoji_arg == emoji_star
    assert obj_arg.id == test_author
    mock_sb_repo.upsert.assert_not_called()


# ---- reaction clear event handler tests ----


async def test_handle_star_clear_wipes_reactions_and_syncs(make_starboard_guild, mock_sb_repo):
    from doom_bot.client.starboard import handle_star_clear

    make_starboard_guild()

    updated = _make_star_doc(reactions={}, total_reactions=0, weighted_total=0.0)
    mock_sb_repo.clear_all_reactions = AsyncMock(return_value=updated)

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
        await handle_star_clear(test_guild, test_channel, test_message)

    mock_sb_repo.clear_all_reactions.assert_called_once_with(test_message)
    mock_sync.assert_called_once()


async def test_handle_star_clear_no_doc_does_nothing(make_starboard_guild, mock_sb_repo):
    from doom_bot.client.starboard import handle_star_clear

    make_starboard_guild()

    mock_sb_repo.clear_all_reactions = AsyncMock(return_value=None)

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
        await handle_star_clear(test_guild, test_channel, test_message)

    mock_sync.assert_not_called()


async def test_handle_star_clear_emoji_removes_one_emoji(make_starboard_guild, mock_sb_repo):
    from doom_bot.client.starboard import handle_star_clear_emoji

    make_starboard_guild()

    updated = _make_star_doc(reactions={}, total_reactions=0, weighted_total=0.0)
    mock_sb_repo.clear_emoji_reactions = AsyncMock(return_value=updated)

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
        await handle_star_clear_emoji(test_guild, test_channel, test_message, emoji_star)

    mock_sb_repo.clear_emoji_reactions.assert_called_once_with(test_message, emoji_star)
    mock_sync.assert_called_once()


async def test_handle_star_clear_emoji_ignores_unconfigured_emoji(make_starboard_guild, mock_sb_repo):
    from doom_bot.client.starboard import handle_star_clear_emoji

    make_starboard_guild()

    mock_sb_repo.clear_emoji_reactions = AsyncMock()

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
        await handle_star_clear_emoji(test_guild, test_channel, test_message, '❤️')

    mock_sb_repo.clear_emoji_reactions.assert_not_called()
    mock_sync.assert_not_called()


async def test_handle_star_clear_redirects_starboard_channel(make_starboard_guild, mock_sb_repo):
    from doom_bot.client.starboard import handle_star_clear

    make_starboard_guild()

    original_doc = _make_star_doc(message_id=test_message)
    mock_sb_repo.get_by_starboard_message = AsyncMock(return_value=original_doc)

    updated = _make_star_doc(reactions={}, total_reactions=0, weighted_total=0.0)
    mock_sb_repo.clear_all_reactions = AsyncMock(return_value=updated)

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock):
        await handle_star_clear(test_guild, test_starboard_channel, test_starboard_msg)

    mock_sb_repo.get_by_starboard_message.assert_called_once_with(test_starboard_msg)
    mock_sb_repo.clear_all_reactions.assert_called_once_with(test_message)


# ---- recount starboard skip-unchanged tests ----


class TestRecountStarboard:
    """tests for the skip-unchanged optimization in job_recount_starboard"""

    def _make_reaction(self, emoji_str: str, user_ids: list[int]):
        """build a mock discord Reaction whose .users() is an async iterator."""
        from unittest.mock import MagicMock

        reaction = MagicMock()
        reaction.emoji = emoji_str

        async def _iter_users():
            for uid in user_ids:
                user = MagicMock()
                user.id = uid
                user.bot = False
                yield user

        reaction.users = MagicMock(return_value=_iter_users())
        return reaction

    async def test_skip_when_reactions_unchanged(self, make_starboard_guild, mock_sb_repo):
        """_sync_starboard_post must NOT be called when live reactions match stored reactions"""
        from unittest.mock import AsyncMock, MagicMock, patch

        from doom_bot.commands.fix import job_recount_starboard

        make_starboard_guild()

        # stored doc already has exactly [user_a, user_b]
        doc = _make_star_doc(
            reactions={emoji_star: [user_a, user_b]},
            total_reactions=2,
            starboard_message_id=0,  # no sb post - skips the second fetch
        )
        mock_sb_repo.all_for_guild = AsyncMock(return_value=[doc])

        orig_msg = MagicMock()
        orig_msg.author = MagicMock(id=test_author)
        orig_msg.reactions = [self._make_reaction(emoji_star, [user_a, user_b])]

        orig_channel = AsyncMock()
        orig_channel.fetch_message = AsyncMock(return_value=orig_msg)

        # bot and _sync_starboard_post are imported inside the function, so patch at source
        with patch('doom_bot.bot') as mock_bot, patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
            mock_bot.get_channel = MagicMock(return_value=orig_channel)
            await job_recount_starboard(test_guild)

        mock_sync.assert_not_called()
        mock_sb_repo.upsert.assert_not_called()

    async def test_syncs_when_reactions_changed(self, make_starboard_guild, mock_sb_repo):
        """_sync_starboard_post MUST be called when live reactions differ from stored"""
        from unittest.mock import AsyncMock, MagicMock, patch

        from doom_bot.commands.fix import job_recount_starboard

        make_starboard_guild()

        # stored doc has 1 reaction, live has 2
        doc = _make_star_doc(
            reactions={emoji_star: [user_a]},
            total_reactions=1,
            starboard_message_id=0,
        )
        mock_sb_repo.all_for_guild = AsyncMock(return_value=[doc])
        mock_sb_repo.upsert = AsyncMock()

        orig_msg = MagicMock()
        orig_msg.author = MagicMock(id=test_author)
        orig_msg.reactions = [self._make_reaction(emoji_star, [user_a, user_b])]

        orig_channel = AsyncMock()
        orig_channel.fetch_message = AsyncMock(return_value=orig_msg)

        with patch('doom_bot.bot') as mock_bot, patch('doom_bot.commands.fix._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
            mock_bot.get_channel = MagicMock(return_value=orig_channel)
            await job_recount_starboard(test_guild)

        mock_sync.assert_called_once()
        mock_sb_repo.upsert.assert_called_once()

    async def test_skip_when_message_not_found(self, make_starboard_guild, mock_sb_repo):
        """discord.NotFound on the original message should not raise - just count as skipped"""
        from unittest.mock import AsyncMock, MagicMock, patch

        import discord

        from doom_bot.commands.fix import job_recount_starboard

        make_starboard_guild()

        doc = _make_star_doc(reactions={emoji_star: [user_a]}, total_reactions=1)
        mock_sb_repo.all_for_guild = AsyncMock(return_value=[doc])

        orig_channel = AsyncMock()
        orig_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))

        with patch('doom_bot.bot') as mock_bot, patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
            mock_bot.get_channel = MagicMock(return_value=orig_channel)
            await job_recount_starboard(test_guild)  # must not raise

        mock_sync.assert_not_called()

    async def test_safe_edit_returns_none_on_http_exception(self):
        """_safe_edit should return None and log a warning rather than raising"""
        from unittest.mock import AsyncMock, MagicMock

        import discord

        from doom_bot.commands.fix import _safe_edit

        msg = AsyncMock()
        msg.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), 'token expired'))

        result = await _safe_edit(msg, 'progress...')
        assert result is None

    async def test_safe_edit_returns_msg_on_success(self):
        """_safe_edit should return the message on a successful edit"""
        from unittest.mock import AsyncMock

        from doom_bot.commands.fix import _safe_edit

        msg = AsyncMock()
        msg.edit = AsyncMock()

        result = await _safe_edit(msg, 'done')
        assert result is msg
        msg.edit.assert_called_once_with(content='done')

    async def test_safe_edit_noop_when_none(self):
        """_safe_edit with status_msg=None is a no-op and returns None"""
        from doom_bot.commands.fix import _safe_edit

        result = await _safe_edit(None, 'anything')
        assert result is None

    async def test_sort_order_independent_comparison(self, make_starboard_guild, mock_sb_repo):
        """skip logic must be order-insensitive - same users in different order should still skip"""
        from unittest.mock import AsyncMock, MagicMock, patch

        from doom_bot.commands.fix import job_recount_starboard

        make_starboard_guild()

        # stored doc has [user_b, user_a] (different order than live)
        doc = _make_star_doc(
            reactions={emoji_star: [user_b, user_a]},
            total_reactions=2,
            starboard_message_id=0,
        )
        mock_sb_repo.all_for_guild = AsyncMock(return_value=[doc])

        # live returns in a different order
        orig_msg = MagicMock()
        orig_msg.author = MagicMock(id=test_author)
        orig_msg.reactions = [self._make_reaction(emoji_star, [user_a, user_b])]

        orig_channel = AsyncMock()
        orig_channel.fetch_message = AsyncMock(return_value=orig_msg)

        with patch('doom_bot.bot') as mock_bot, patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
            mock_bot.get_channel = MagicMock(return_value=orig_channel)
            await job_recount_starboard(test_guild)

        # same users, just different storage order - should be skipped
        mock_sync.assert_not_called()


class TestStarboardChannelFallthrough:
    """verify that regular messages in the starboard channel can still be starred"""

    async def test_regular_message_in_starboard_channel_is_processed(self, make_starboard_guild, mock_sb_and_msg_repos):
        """reaction on an unlinked message in the starboard channel should not be silently dropped"""
        from unittest.mock import AsyncMock, patch

        from doom_bot.client.starboard import handle_star_add

        sb_repo, msg_repo = mock_sb_and_msg_repos
        make_starboard_guild()

        # message is in the starboard channel but has no known starboard post lookup
        sb_repo.get_by_starboard_message = AsyncMock(return_value=None)

        msg_doc = _make_msg_doc(author_id=test_author, channel_id=test_starboard_channel)
        msg_repo.get = AsyncMock(return_value=msg_doc)
        sb_repo.get = AsyncMock(return_value=None)

        updated = _make_star_doc(reactions={emoji_star: [user_a]}, total_reactions=1)
        sb_repo.add_reaction = AsyncMock(return_value=updated)

        with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock):
            await handle_star_add(test_guild, test_starboard_channel, test_message, user_id=user_a, emoji_str=emoji_star)

        # should NOT have been dropped - add_reaction must have been called
        sb_repo.add_reaction.assert_called_once_with(test_message, emoji_star, user_a)

    async def test_known_starboard_post_still_redirects_to_original(self, make_starboard_guild, mock_sb_and_msg_repos):
        """reaction on a known starboard post should still redirect to the original message"""
        from unittest.mock import AsyncMock, patch

        from doom_bot.client.starboard import handle_star_add

        sb_repo, msg_repo = mock_sb_and_msg_repos
        make_starboard_guild()

        existing_doc = _make_star_doc(starboard_message_id=test_starboard_msg, message_id=test_message)
        sb_repo.get_by_starboard_message = AsyncMock(return_value=existing_doc)

        msg_doc = _make_msg_doc(author_id=test_author)
        msg_repo.get = AsyncMock(return_value=msg_doc)
        sb_repo.get = AsyncMock(return_value=existing_doc)

        updated = _make_star_doc(reactions={emoji_star: [user_a]}, total_reactions=1)
        sb_repo.add_reaction = AsyncMock(return_value=updated)

        with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock):
            await handle_star_add(test_guild, test_starboard_channel, test_starboard_msg, user_id=user_a, emoji_str=emoji_star)

        # should have been redirected to the original message ID
        sb_repo.add_reaction.assert_called_once_with(test_message, emoji_star, user_a)


class TestStarReferenceRedirect:
    async def test_handle_star_add_uses_reference(self, make_starboard_guild, mock_sb_and_msg_repos):
        from unittest.mock import AsyncMock, patch

        from doom_bot.client.starboard import handle_star_add

        sb_repo, msg_repo = mock_sb_and_msg_repos
        make_starboard_guild()

        response_id = test_starboard_msg + 1
        response_doc = _make_msg_doc(message_id=response_id, channel_id=test_channel, starboard_reference_id=test_message)
        original_doc = _make_msg_doc(author_id=test_author)
        msg_repo.get = AsyncMock(side_effect=[response_doc, original_doc, original_doc])
        sb_repo.get = AsyncMock(return_value=None)

        updated = _make_star_doc(reactions={emoji_star: [user_a]}, total_reactions=1)
        sb_repo.add_reaction = AsyncMock(return_value=updated)

        with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock):
            await handle_star_add(test_guild, test_channel, response_id, user_id=user_a, emoji_str=emoji_star)

        sb_repo.add_reaction.assert_called_once_with(test_message, emoji_star, user_a)

    async def test_handle_star_remove_uses_reference(self, make_starboard_guild, mock_sb_and_msg_repos):
        from unittest.mock import AsyncMock, patch

        from doom_bot.client.starboard import handle_star_remove

        sb_repo, msg_repo = mock_sb_and_msg_repos
        make_starboard_guild()

        response_id = test_starboard_msg + 2
        response_doc = _make_msg_doc(message_id=response_id, starboard_reference_id=test_message)
        msg_repo.get = AsyncMock(return_value=response_doc)
        sb_repo.remove_reaction = AsyncMock(return_value=_make_star_doc(reactions={emoji_star: []}, total_reactions=0))

        with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock):
            await handle_star_remove(test_guild, test_channel, response_id, user_id=user_a, emoji_str=emoji_star)

        sb_repo.remove_reaction.assert_called_once_with(test_message, emoji_star, user_a)


# ---- super reaction (burst) tests ----


def test_weighted_count_normal_only():
    assert _weighted_count(emoji_star, {emoji_star: [user_a, user_b]}, {}) == 2.0


def test_weighted_count_super_only():
    assert _weighted_count(emoji_star, {}, {emoji_star: [user_a, user_b]}) == 3.0


def test_weighted_count_mixed():
    # 2 normal (2.0) + 1 super (1.5) = 3.5
    assert _weighted_count(emoji_star, {emoji_star: [user_a, user_b]}, {emoji_star: [user_c]}) == 3.5


def test_weighted_count_missing_emoji():
    assert _weighted_count(emoji_star, {}, {}) == 0.0


def test_fmt_count_whole_number():
    assert _fmt_count(4.0) == '4'


def test_fmt_count_fractional():
    assert _fmt_count(4.5) == '4.5'


def test_fmt_count_one_and_half():
    assert _fmt_count(1.5) == '1.5'


def test_build_content_super_only():
    """one super reactor should display as 1.5"""
    result = build_content({}, jump_url, emoji_map, super_reactions={emoji_star: [user_a]})
    assert f'{emoji_star} **1.5**' in result
    assert jump_url in result


def test_build_content_normal_and_super_no_double_count():
    """two normal + one super should display as 3.5, not 3"""
    reactions = {emoji_star: [user_a, user_b]}
    super_reactions = {emoji_star: [user_c]}
    result = build_content(reactions, jump_url, emoji_map, super_reactions=super_reactions)
    assert f'{emoji_star} **3.5**' in result


def test_build_content_super_reaction_sorts_correctly():
    """emoji with higher weighted count (via super) should sort before one with more raw reactors"""
    emoji2 = '🌟'
    emoji_map = {emoji_star: '#EEDD20', emoji2: '#FF0000'}
    # star: 1 normal + 1 super = 2.5; emoji2: 2 normal = 2.0 - star should win
    reactions = {emoji_star: [user_a], emoji2: [user_a, user_b]}
    super_reactions = {emoji_star: [user_b]}
    result = build_content(reactions, jump_url, emoji_map, super_reactions=super_reactions)
    assert result.index(emoji_star) < result.index(emoji2)


def test_dominant_color_super_reaction_wins():
    """emoji with lower raw count but higher weighted count should win dominant color"""
    emoji2 = '🌟'
    emoji_map = {emoji_star: '#EEDD20', emoji2: '#FF0000'}
    # star: 0 normal + 2 super = 3.0; emoji2: 2 normal = 2.0
    reactions = {emoji2: [user_a, user_b]}
    super_reactions = {emoji_star: [user_a, user_b]}
    assert dominant_color(reactions, emoji_map, super_reactions=super_reactions) == 0xEEDD20


async def test_handle_star_add_super_calls_add_super_reaction(make_starboard_guild, mock_sb_and_msg_repos):
    """is_burst=True must call add_super_reaction, not add_reaction"""
    from doom_bot.client.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    msg_doc = _make_msg_doc(author_id=test_author)
    msg_repo.get = AsyncMock(return_value=msg_doc)
    sb_repo.get = AsyncMock(return_value=None)

    updated = _make_star_doc(super_reactions={emoji_star: [user_a]}, total_reactions=1, weighted_total=1.5)
    sb_repo.add_super_reaction = AsyncMock(return_value=updated)

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock):
        await handle_star_add(test_guild, test_channel, test_message, user_id=user_a, emoji_str=emoji_star, is_burst=True)

    sb_repo.add_super_reaction.assert_called_once_with(test_message, emoji_star, user_a)
    sb_repo.add_reaction.assert_not_called()


async def test_handle_star_add_normal_does_not_call_super(make_starboard_guild, mock_sb_and_msg_repos):
    """is_burst=False must call add_reaction, not add_super_reaction"""
    from doom_bot.client.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    msg_doc = _make_msg_doc(author_id=test_author)
    msg_repo.get = AsyncMock(return_value=msg_doc)
    sb_repo.get = AsyncMock(return_value=None)

    updated = _make_star_doc(reactions={emoji_star: [user_a]}, total_reactions=1, weighted_total=1.0)
    sb_repo.add_reaction = AsyncMock(return_value=updated)

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock):
        await handle_star_add(test_guild, test_channel, test_message, user_id=user_a, emoji_str=emoji_star, is_burst=False)

    sb_repo.add_reaction.assert_called_once_with(test_message, emoji_star, user_a)
    sb_repo.add_super_reaction.assert_not_called()


async def test_handle_star_remove_super_calls_remove_super_reaction(make_starboard_guild, mock_sb_and_msg_repos):
    """is_burst=True on remove must call remove_super_reaction"""
    from doom_bot.client.starboard import handle_star_remove

    sb_repo, _ = mock_sb_and_msg_repos
    make_starboard_guild()

    updated = _make_star_doc(super_reactions={emoji_star: []}, total_reactions=0, weighted_total=0.0)
    sb_repo.remove_super_reaction = AsyncMock(return_value=updated)

    with patch('doom_bot.client.starboard._sync_starboard_post', new_callable=AsyncMock):
        await handle_star_remove(test_guild, test_channel, test_message, user_id=user_a, emoji_str=emoji_star, is_burst=True)

    sb_repo.remove_super_reaction.assert_called_once_with(test_message, emoji_star, user_a)
    sb_repo.remove_reaction.assert_not_called()


# ---- parse_starboard_content against real dump samples ----


def test_parse_real_dump_samples():
    """verify parser works on actual content strings from assets/starboard_dump.json"""
    samples = [
        '\u2b50 **4** | https://discord.com/channels/1001828025756819456/1001829427409334292/1293683225524179035',
        '\u2b50 **7** | https://discord.com/channels/1001828025756819456/1020881436770832464/1311509842178998333',
        '\u2b50 **5** | https://discord.com/channels/1001828025756819456/1001829427409334292/1294658157930348617',
    ]
    expected_counts = [4, 7, 5]
    expected_msg_ids = [1293683225524179035, 1311509842178998333, 1294658157930348617]

    for content, exp_count, exp_msg_id in zip(samples, expected_counts, expected_msg_ids, strict=True):
        counts, url = parse_starboard_content(content)
        assert '⭐' in counts, f'expected ⭐ in counts for: {content!r}'
        assert counts['⭐'] == exp_count
        parsed = parse_jump_url(url)  # pyright: ignore[reportArgumentType]
        assert parsed is not None
        assert parsed[2] == exp_msg_id


# ---- _count_streak pure function tests ----


def test_count_streak_empty_list():
    assert _count_streak([], test_author) == 0


def test_count_streak_single_match():
    docs = [_make_star_doc(message_id=1001, author_id=test_author, starboard_message_id=2001)]
    assert _count_streak(docs, test_author) == 1


def test_count_streak_single_mismatch():
    docs = [_make_star_doc(message_id=1001, author_id=user_a, starboard_message_id=2001)]
    assert _count_streak(docs, test_author) == 0


def test_count_streak_three_in_a_row():
    docs = [_make_star_doc(message_id=1000 + i, author_id=test_author, starboard_message_id=2000 + i) for i in range(3)]
    assert _count_streak(docs, test_author) == 3


def test_count_streak_five_in_a_row():
    docs = [_make_star_doc(message_id=1000 + i, author_id=test_author, starboard_message_id=2000 + i) for i in range(5)]
    assert _count_streak(docs, test_author) == 5


def test_count_streak_eleven_in_a_row():
    docs = [_make_star_doc(message_id=1000 + i, author_id=test_author, starboard_message_id=2000 + i) for i in range(11)]
    assert _count_streak(docs, test_author) == 11


def test_count_streak_broken_by_other_author():
    # 2 by test_author at tail, 1 by user_a before, then test_author earlier - streak is 2
    docs = [
        _make_star_doc(message_id=1001, author_id=test_author, starboard_message_id=2001),
        _make_star_doc(message_id=1002, author_id=user_a, starboard_message_id=2002),
        _make_star_doc(message_id=1003, author_id=test_author, starboard_message_id=2003),
        _make_star_doc(message_id=1004, author_id=test_author, starboard_message_id=2004),
    ]
    assert _count_streak(docs, test_author) == 2


def test_count_streak_other_author_at_tail():
    docs = [
        _make_star_doc(message_id=1001, author_id=test_author, starboard_message_id=2001),
        _make_star_doc(message_id=1002, author_id=test_author, starboard_message_id=2002),
        _make_star_doc(message_id=1003, author_id=user_a, starboard_message_id=2003),
    ]
    assert _count_streak(docs, test_author) == 0


def test_count_streak_unordered_input():
    # same docs as three_in_a_row but reversed - should still return 3
    docs = [_make_star_doc(message_id=1000 + i, author_id=test_author, starboard_message_id=2000 + i) for i in range(3)]
    assert _count_streak(list(reversed(docs)), test_author) == 3


def test_count_streak_author_in_middle_only():
    docs = [
        _make_star_doc(message_id=1001, author_id=user_a, starboard_message_id=2001),
        _make_star_doc(message_id=1002, author_id=test_author, starboard_message_id=2002),
        _make_star_doc(message_id=1003, author_id=user_b, starboard_message_id=2003),
    ]
    assert _count_streak(docs, test_author) == 0


# ---- _sweep_message pure function tests ----


def test_sweep_message_streak_3():
    result = _sweep_message(3, test_author)
    assert result is not None
    assert f'<@{test_author}>' in result
    assert 'sweeps!' in result
    assert ':broom:' in result


def test_sweep_message_streak_5():
    result = _sweep_message(5, test_author)
    assert result is not None
    assert 'sweeps more!' in result
    assert ':silver_medal:' in result


def test_sweep_message_streak_11():
    result = _sweep_message(11, test_author)
    assert result is not None
    assert 'sweeps even more!' in result
    assert ':gold_medal:' in result


def test_sweep_message_streak_0_is_none():
    assert _sweep_message(0, test_author) is None


def test_sweep_message_streak_1_is_none():
    assert _sweep_message(1, test_author) is None


def test_sweep_message_streak_2_is_none():
    assert _sweep_message(2, test_author) is None


def test_sweep_message_streak_4_is_none():
    assert _sweep_message(4, test_author) is None


def test_sweep_message_streak_6_is_none():
    assert _sweep_message(6, test_author) is None


def test_sweep_message_streak_10_is_none():
    assert _sweep_message(10, test_author) is None


def test_sweep_message_streak_12_is_none():
    assert _sweep_message(12, test_author) is None


def test_sweep_message_mention_format():
    result = _sweep_message(3, test_author)
    assert result is not None
    assert result.startswith(f'<@{test_author}>')


# ---- _check_and_announce_sweep integration tests ----


@pytest.fixture
def mock_sb_repo_for_sweep():
    """patch _starboard_repo with a fresh MagicMock for sweep tests"""
    repo = MagicMock()
    repo.all_for_guild = AsyncMock()
    with patch('doom_bot.client.starboard._starboard_repo', repo):
        yield repo


async def test_check_and_announce_sweep_sends_on_streak_3(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=test_author, starboard_message_id=2000 + i) for i in range(3)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(test_guild, test_author, channel)

    channel.send.assert_called_once()
    text = channel.send.call_args.kwargs['content']
    assert f'<@{test_author}>' in text
    assert 'sweeps!' in text
    assert ':broom:' in text


async def test_check_and_announce_sweep_sends_on_streak_5(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=test_author, starboard_message_id=2000 + i) for i in range(5)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(test_guild, test_author, channel)

    channel.send.assert_called_once()
    text = channel.send.call_args.kwargs['content']
    assert 'sweeps more!' in text
    assert ':silver_medal:' in text


async def test_check_and_announce_sweep_sends_on_streak_11(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=test_author, starboard_message_id=2000 + i) for i in range(11)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(test_guild, test_author, channel)

    channel.send.assert_called_once()
    text = channel.send.call_args.kwargs['content']
    assert 'sweeps even more!' in text
    assert ':gold_medal:' in text


async def test_check_and_announce_sweep_no_send_on_streak_2(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=test_author, starboard_message_id=2000 + i) for i in range(2)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(test_guild, test_author, channel)

    channel.send.assert_not_called()


async def test_check_and_announce_sweep_no_send_on_streak_4(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=test_author, starboard_message_id=2000 + i) for i in range(4)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(test_guild, test_author, channel)

    channel.send.assert_not_called()


async def test_check_and_announce_sweep_no_send_when_streak_broken(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    # 2 by test_author at tail, then user_a breaks the streak
    docs = [
        _make_star_doc(message_id=1001, author_id=user_a, starboard_message_id=2001),
        _make_star_doc(message_id=1002, author_id=test_author, starboard_message_id=2002),
        _make_star_doc(message_id=1003, author_id=test_author, starboard_message_id=2003),
    ]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(test_guild, test_author, channel)

    channel.send.assert_not_called()


async def test_check_and_announce_sweep_ignores_unposted_docs(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    # 3 docs by test_author but one lacks starboard_message_id - only 2 are "posted"
    docs = [
        _make_star_doc(message_id=1001, author_id=test_author, starboard_message_id=2001),
        _make_star_doc(message_id=1002, author_id=test_author, starboard_message_id=2002),
        _make_star_doc(message_id=1003, author_id=test_author, starboard_message_id=None),
    ]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(test_guild, test_author, channel)

    # streak of 2 posted docs - no announce
    channel.send.assert_not_called()


async def test_check_and_announce_sweep_swallows_repo_error(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    repo.all_for_guild = AsyncMock(side_effect=RuntimeError('db error'))
    channel = AsyncMock()

    # must not raise
    await _check_and_announce_sweep(test_guild, test_author, channel)

    channel.send.assert_not_called()


async def test_check_and_announce_sweep_swallows_send_error(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=test_author, starboard_message_id=2000 + i) for i in range(3)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()
    channel.send = AsyncMock(side_effect=RuntimeError('discord error'))

    # must not raise
    await _check_and_announce_sweep(test_guild, test_author, channel)
