"""
AttuBot - Starboard Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from attubot.database.models import MessageAuthor, MessageContent, MessageDocument, MessageRefs, StarredMessageDocument
from attubot.starboard import (
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


# ---- constants ----

# real guild/channel/message IDs from the dump - used only for pure function tests
REAL_GUILD = 1001828025756819456
REAL_CHANNEL = 1001829427409334292
REAL_MESSAGE = 1293683225524179035

# synthetic IDs used for integration tests (must match make_guild() default)
TEST_GUILD = 1234567890
TEST_CHANNEL = 5555555555
TEST_STARBOARD_CHANNEL = 9999999999
TEST_MESSAGE = 111000111000111000
TEST_STARBOARD_MSG = 222000222000222000
TEST_AUTHOR = 573360359566737409
USER_A = 100000001
USER_B = 100000002
USER_C = 100000003

EMOJI_STAR = '⭐'
EMOJI_COLOR = '#EEDD20'
EMOJI_MAP = {EMOJI_STAR: EMOJI_COLOR}

# convenience for pure function tests
GUILD = REAL_GUILD
CHANNEL = REAL_CHANNEL
MESSAGE = REAL_MESSAGE
JUMP_URL = f'https://discord.com/channels/{GUILD}/{CHANNEL}/{MESSAGE}'


# ---- pure function unit tests ----


def test_parse_color_standard():
    assert _parse_color('#EEDD20') == 0xEEDD20


def test_parse_color_without_hash():
    assert _parse_color('EEDD20') == 0xEEDD20


def test_build_content_single_emoji():
    reactions = {EMOJI_STAR: [USER_A, USER_B, USER_C]}
    result = build_content(reactions, JUMP_URL, EMOJI_MAP)
    assert result == f'{EMOJI_STAR} **3** | {JUMP_URL}'


def test_build_content_multiple_emojis_sorted_by_count():
    emoji2 = '🌟'
    reactions = {EMOJI_STAR: [USER_A, USER_B], emoji2: [USER_A, USER_B, USER_C]}
    emoji_map = {EMOJI_STAR: '#EEDD20', emoji2: '#FF0000'}
    result = build_content(reactions, JUMP_URL, emoji_map)
    # emoji2 has 3 reactions vs star's 2, so emoji2 should come first
    assert result.startswith(f'{emoji2} **3** | {EMOJI_STAR} **2**')
    assert result.endswith(JUMP_URL)


def test_build_content_skips_unconfigured_emojis():
    reactions = {EMOJI_STAR: [USER_A], '❤️': [USER_B]}  # ❤️ not configured
    result = build_content(reactions, JUMP_URL, EMOJI_MAP)
    assert '❤️' not in result
    assert EMOJI_STAR in result


def test_build_content_skips_empty_reaction_lists():
    reactions = {EMOJI_STAR: [], '🌟': [USER_A]}
    emoji_map = {EMOJI_STAR: '#EEDD20', '🌟': '#FF0000'}
    result = build_content(reactions, JUMP_URL, emoji_map)
    assert EMOJI_STAR not in result
    assert '🌟' in result


def test_dominant_color_single_emoji():
    reactions = {EMOJI_STAR: [USER_A, USER_B]}
    assert dominant_color(reactions, EMOJI_MAP) == 0xEEDD20


def test_dominant_color_returns_highest_count_emoji():
    emoji2 = '🌟'
    reactions = {EMOJI_STAR: [USER_A], emoji2: [USER_A, USER_B]}
    emoji_map = {EMOJI_STAR: '#EEDD20', emoji2: '#FF0000'}
    assert dominant_color(reactions, emoji_map) == 0xFF0000


def test_dominant_color_fallback_when_no_configured_emoji():
    reactions = {'❤️': [USER_A]}  # not in emoji_map
    fallback = 0xABCDEF
    assert dominant_color(reactions, EMOJI_MAP, fallback=fallback) == fallback


def test_dominant_color_fallback_when_all_lists_empty():
    reactions = {EMOJI_STAR: []}
    assert dominant_color(reactions, EMOJI_MAP, fallback=0x123456) == 0x123456


def test_parse_jump_url_valid():
    result = parse_jump_url(JUMP_URL)
    assert result == (GUILD, CHANNEL, MESSAGE)


def test_parse_jump_url_invalid():
    assert parse_jump_url('https://example.com/not-a-jump-url') is None
    assert parse_jump_url('') is None


def test_parse_starboard_content_single_emoji():
    content = f'{EMOJI_STAR} **4** | {JUMP_URL}'
    counts, url = parse_starboard_content(content)
    assert counts == {EMOJI_STAR: 4}
    assert url == JUMP_URL


def test_parse_starboard_content_multiple_emojis():
    emoji2 = '🌟'
    content = f'{EMOJI_STAR} **4** | {emoji2} **1** | {JUMP_URL}'
    counts, url = parse_starboard_content(content)
    assert counts == {EMOJI_STAR: 4, emoji2: 1}
    assert url == JUMP_URL


def test_parse_starboard_content_no_url():
    _, url = parse_starboard_content(f'{EMOJI_STAR} **3** | no url here')
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
    monkeypatch.setattr('attubot.bot', MagicMock(get_user=MagicMock(return_value=mock_user)))

    embeds = await build_embeds(msg_doc, TEST_GUILD, 0xEEDD20)
    assert embeds[0].description == 'preview text'


@pytest.mark.asyncio
async def test_build_embeds_forwarded_sets_footer(monkeypatch):
    msg_doc = _make_msg_doc(content='this was forwarded', forwarded=True)
    mock_user = MagicMock()
    mock_avatar = MagicMock()
    mock_avatar.__str__.return_value = 'avatar_url'
    mock_user.display_avatar = mock_avatar
    monkeypatch.setattr('attubot.bot', MagicMock(get_user=MagicMock(return_value=mock_user)))

    embeds = await build_embeds(msg_doc, TEST_GUILD, 0xEEDD20)
    assert embeds[0].footer.text == 'forwarded message'


@pytest.mark.asyncio
async def test_build_embeds_not_forwarded_no_footer(monkeypatch):
    msg_doc = _make_msg_doc(content='regular message', forwarded=False)
    mock_user = MagicMock()
    mock_avatar = MagicMock()
    mock_avatar.__str__.return_value = 'avatar_url'
    mock_user.display_avatar = mock_avatar
    monkeypatch.setattr('attubot.bot', MagicMock(get_user=MagicMock(return_value=mock_user)))

    embeds = await build_embeds(msg_doc, TEST_GUILD, 0xEEDD20)
    assert embeds[0].footer is None


# ---- make_message_doc helper ----


def _make_msg_doc(**kwargs) -> MessageDocument:
    return MessageDocument(
        message_id=kwargs.pop('message_id', TEST_MESSAGE),
        guild_id=kwargs.pop('guild_id', TEST_GUILD),
        channel_id=kwargs.pop('channel_id', TEST_CHANNEL),
        parent_channel_id=kwargs.pop('parent_channel_id', None),
        author=MessageAuthor(
            id=kwargs.pop('author_id', TEST_AUTHOR),
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
        'message_id': TEST_MESSAGE,
        'channel_id': TEST_CHANNEL,
        'guild_id': TEST_GUILD,
        'author_id': TEST_AUTHOR,
    }
    defaults.update(kwargs)
    return StarredMessageDocument(**defaults)  # pyright: ignore[reportArgumentType]


# ---- handle_star_add integration tests ----


@pytest.fixture
def mock_sb_repo():
    repo = AsyncMock()
    with patch('attubot.starboard._starboard_repo', repo):
        yield repo


@pytest.fixture
def mock_sb_and_msg_repos(mock_sb_repo):
    msg_repo = AsyncMock()
    with patch('attubot.messages._message_repo', msg_repo):
        yield mock_sb_repo, msg_repo


@pytest.fixture
def make_starboard_guild(make_guild):
    """Create a guild with a configured starboard."""

    def _make(**kwargs):
        cfg = make_guild()
        from attubot.config import GuildStarboard

        cfg.starboard = GuildStarboard(channel_id=TEST_STARBOARD_CHANNEL, emojis={EMOJI_STAR: EMOJI_COLOR})
        return cfg

    return _make


async def test_handle_star_add_self_star_ignored(make_starboard_guild, mock_sb_and_msg_repos):
    from attubot.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    # author stars their own message
    msg_doc = _make_msg_doc(author_id=USER_A)
    msg_repo.get = AsyncMock(return_value=msg_doc)

    await handle_star_add(TEST_GUILD, TEST_CHANNEL, TEST_MESSAGE, user_id=USER_A, emoji_str=EMOJI_STAR)

    sb_repo.add_reaction.assert_not_called()


async def test_handle_star_add_unconfigured_emoji_ignored(make_starboard_guild, mock_sb_and_msg_repos):
    from attubot.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    await handle_star_add(TEST_GUILD, TEST_CHANNEL, TEST_MESSAGE, user_id=USER_A, emoji_str='❤️')

    sb_repo.add_reaction.assert_not_called()
    msg_repo.get.assert_not_called()


async def test_handle_star_add_creates_document_and_adds_reaction(make_starboard_guild, mock_sb_and_msg_repos):
    from attubot.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    msg_doc = _make_msg_doc(author_id=TEST_AUTHOR)
    msg_repo.get = AsyncMock(return_value=msg_doc)
    sb_repo.get = AsyncMock(return_value=None)  # no existing document

    updated = _make_star_doc(reactions={EMOJI_STAR: [USER_A]}, total_reactions=1)
    sb_repo.add_reaction = AsyncMock(return_value=updated)

    with patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
        await handle_star_add(TEST_GUILD, TEST_CHANNEL, TEST_MESSAGE, user_id=USER_A, emoji_str=EMOJI_STAR)

    sb_repo.upsert.assert_called_once()
    sb_repo.add_reaction.assert_called_once_with(TEST_MESSAGE, EMOJI_STAR, USER_A)
    mock_sync.assert_called_once()


async def test_handle_star_add_reaction_on_starboard_post_resolves_original(make_starboard_guild, mock_sb_and_msg_repos):
    from attubot.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    # existing doc links starboard post -> original message
    existing_doc = _make_star_doc(starboard_message_id=TEST_STARBOARD_MSG, message_id=TEST_MESSAGE)
    sb_repo.get_by_starboard_message = AsyncMock(return_value=existing_doc)

    msg_doc = _make_msg_doc(author_id=TEST_AUTHOR)
    msg_repo.get = AsyncMock(return_value=msg_doc)
    sb_repo.get = AsyncMock(return_value=existing_doc)

    updated = _make_star_doc(reactions={EMOJI_STAR: [USER_A]}, total_reactions=1)
    sb_repo.add_reaction = AsyncMock(return_value=updated)

    with patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock):
        # reaction is on the STARBOARD channel/message, not the original
        await handle_star_add(TEST_GUILD, TEST_STARBOARD_CHANNEL, TEST_STARBOARD_MSG, user_id=USER_A, emoji_str=EMOJI_STAR)

    sb_repo.get_by_starboard_message.assert_called_once_with(TEST_STARBOARD_MSG)
    sb_repo.add_reaction.assert_called_once_with(TEST_MESSAGE, EMOJI_STAR, USER_A)


async def test_handle_star_add_message_not_in_db_ignored(make_starboard_guild, mock_sb_and_msg_repos):
    from attubot.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    msg_repo.get = AsyncMock(return_value=None)

    await handle_star_add(TEST_GUILD, TEST_CHANNEL, TEST_MESSAGE, user_id=USER_A, emoji_str=EMOJI_STAR)

    sb_repo.add_reaction.assert_not_called()


async def test_handle_star_remove_updates_document(make_starboard_guild, mock_sb_and_msg_repos):
    from attubot.starboard import handle_star_remove

    sb_repo, _ = mock_sb_and_msg_repos
    make_starboard_guild()

    updated = _make_star_doc(reactions={EMOJI_STAR: []}, total_reactions=0)
    sb_repo.remove_reaction = AsyncMock(return_value=updated)

    with patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
        await handle_star_remove(TEST_GUILD, TEST_CHANNEL, TEST_MESSAGE, user_id=USER_A, emoji_str=EMOJI_STAR)

    sb_repo.remove_reaction.assert_called_once_with(TEST_MESSAGE, EMOJI_STAR, USER_A)
    mock_sync.assert_called_once()


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

        from attubot.commands.fix import job_recount_starboard

        make_starboard_guild()

        # stored doc already has exactly [USER_A, USER_B]
        doc = _make_star_doc(
            reactions={EMOJI_STAR: [USER_A, USER_B]},
            total_reactions=2,
            starboard_message_id=0,  # no sb post - skips the second fetch
        )
        mock_sb_repo.all_for_guild = AsyncMock(return_value=[doc])

        orig_msg = MagicMock()
        orig_msg.author = MagicMock(id=TEST_AUTHOR)
        orig_msg.reactions = [self._make_reaction(EMOJI_STAR, [USER_A, USER_B])]

        orig_channel = AsyncMock()
        orig_channel.fetch_message = AsyncMock(return_value=orig_msg)

        # bot and _sync_starboard_post are imported inside the function, so patch at source
        with patch('attubot.bot') as mock_bot, patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
            mock_bot.get_channel = MagicMock(return_value=orig_channel)
            await job_recount_starboard(TEST_GUILD)

        mock_sync.assert_not_called()
        mock_sb_repo.upsert.assert_not_called()

    async def test_syncs_when_reactions_changed(self, make_starboard_guild, mock_sb_repo):
        """_sync_starboard_post MUST be called when live reactions differ from stored"""
        from unittest.mock import AsyncMock, MagicMock, patch

        from attubot.commands.fix import job_recount_starboard

        make_starboard_guild()

        # stored doc has 1 reaction, live has 2
        doc = _make_star_doc(
            reactions={EMOJI_STAR: [USER_A]},
            total_reactions=1,
            starboard_message_id=0,
        )
        mock_sb_repo.all_for_guild = AsyncMock(return_value=[doc])
        mock_sb_repo.upsert = AsyncMock()

        orig_msg = MagicMock()
        orig_msg.author = MagicMock(id=TEST_AUTHOR)
        orig_msg.reactions = [self._make_reaction(EMOJI_STAR, [USER_A, USER_B])]

        orig_channel = AsyncMock()
        orig_channel.fetch_message = AsyncMock(return_value=orig_msg)

        with patch('attubot.bot') as mock_bot, patch('attubot.commands.fix._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
            mock_bot.get_channel = MagicMock(return_value=orig_channel)
            await job_recount_starboard(TEST_GUILD)

        mock_sync.assert_called_once()
        mock_sb_repo.upsert.assert_called_once()

    async def test_skip_when_message_not_found(self, make_starboard_guild, mock_sb_repo):
        """discord.NotFound on the original message should not raise - just count as skipped"""
        from unittest.mock import AsyncMock, MagicMock, patch

        import discord

        from attubot.commands.fix import job_recount_starboard

        make_starboard_guild()

        doc = _make_star_doc(reactions={EMOJI_STAR: [USER_A]}, total_reactions=1)
        mock_sb_repo.all_for_guild = AsyncMock(return_value=[doc])

        orig_channel = AsyncMock()
        orig_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))

        with patch('attubot.bot') as mock_bot, patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
            mock_bot.get_channel = MagicMock(return_value=orig_channel)
            await job_recount_starboard(TEST_GUILD)  # must not raise

        mock_sync.assert_not_called()

    async def test_safe_edit_returns_none_on_http_exception(self):
        """_safe_edit should return None and log a warning rather than raising"""
        from unittest.mock import AsyncMock, MagicMock

        import discord

        from attubot.commands.fix import _safe_edit

        msg = AsyncMock()
        msg.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), 'token expired'))

        result = await _safe_edit(msg, 'progress...')
        assert result is None

    async def test_safe_edit_returns_msg_on_success(self):
        """_safe_edit should return the message on a successful edit"""
        from unittest.mock import AsyncMock

        from attubot.commands.fix import _safe_edit

        msg = AsyncMock()
        msg.edit = AsyncMock()

        result = await _safe_edit(msg, 'done')
        assert result is msg
        msg.edit.assert_called_once_with(content='done')

    async def test_safe_edit_noop_when_none(self):
        """_safe_edit with status_msg=None is a no-op and returns None"""
        from attubot.commands.fix import _safe_edit

        result = await _safe_edit(None, 'anything')
        assert result is None

    async def test_sort_order_independent_comparison(self, make_starboard_guild, mock_sb_repo):
        """skip logic must be order-insensitive - same users in different order should still skip"""
        from unittest.mock import AsyncMock, MagicMock, patch

        from attubot.commands.fix import job_recount_starboard

        make_starboard_guild()

        # stored doc has [USER_B, USER_A] (different order than live)
        doc = _make_star_doc(
            reactions={EMOJI_STAR: [USER_B, USER_A]},
            total_reactions=2,
            starboard_message_id=0,
        )
        mock_sb_repo.all_for_guild = AsyncMock(return_value=[doc])

        # live returns in a different order
        orig_msg = MagicMock()
        orig_msg.author = MagicMock(id=TEST_AUTHOR)
        orig_msg.reactions = [self._make_reaction(EMOJI_STAR, [USER_A, USER_B])]

        orig_channel = AsyncMock()
        orig_channel.fetch_message = AsyncMock(return_value=orig_msg)

        with patch('attubot.bot') as mock_bot, patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
            mock_bot.get_channel = MagicMock(return_value=orig_channel)
            await job_recount_starboard(TEST_GUILD)

        # same users, just different storage order - should be skipped
        mock_sync.assert_not_called()


class TestStarboardChannelFallthrough:
    """verify that regular messages in the starboard channel can still be starred"""

    async def test_regular_message_in_starboard_channel_is_processed(self, make_starboard_guild, mock_sb_and_msg_repos):
        """reaction on an unlinked message in the starboard channel should not be silently dropped"""
        from unittest.mock import AsyncMock, patch

        from attubot.starboard import handle_star_add

        sb_repo, msg_repo = mock_sb_and_msg_repos
        make_starboard_guild()

        # message is in the starboard channel but has no known starboard post lookup
        sb_repo.get_by_starboard_message = AsyncMock(return_value=None)

        msg_doc = _make_msg_doc(author_id=TEST_AUTHOR, channel_id=TEST_STARBOARD_CHANNEL)
        msg_repo.get = AsyncMock(return_value=msg_doc)
        sb_repo.get = AsyncMock(return_value=None)

        updated = _make_star_doc(reactions={EMOJI_STAR: [USER_A]}, total_reactions=1)
        sb_repo.add_reaction = AsyncMock(return_value=updated)

        with patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock):
            await handle_star_add(TEST_GUILD, TEST_STARBOARD_CHANNEL, TEST_MESSAGE, user_id=USER_A, emoji_str=EMOJI_STAR)

        # should NOT have been dropped - add_reaction must have been called
        sb_repo.add_reaction.assert_called_once_with(TEST_MESSAGE, EMOJI_STAR, USER_A)

    async def test_known_starboard_post_still_redirects_to_original(self, make_starboard_guild, mock_sb_and_msg_repos):
        """reaction on a known starboard post should still redirect to the original message"""
        from unittest.mock import AsyncMock, patch

        from attubot.starboard import handle_star_add

        sb_repo, msg_repo = mock_sb_and_msg_repos
        make_starboard_guild()

        existing_doc = _make_star_doc(starboard_message_id=TEST_STARBOARD_MSG, message_id=TEST_MESSAGE)
        sb_repo.get_by_starboard_message = AsyncMock(return_value=existing_doc)

        msg_doc = _make_msg_doc(author_id=TEST_AUTHOR)
        msg_repo.get = AsyncMock(return_value=msg_doc)
        sb_repo.get = AsyncMock(return_value=existing_doc)

        updated = _make_star_doc(reactions={EMOJI_STAR: [USER_A]}, total_reactions=1)
        sb_repo.add_reaction = AsyncMock(return_value=updated)

        with patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock):
            await handle_star_add(TEST_GUILD, TEST_STARBOARD_CHANNEL, TEST_STARBOARD_MSG, user_id=USER_A, emoji_str=EMOJI_STAR)

        # should have been redirected to the original message ID
        sb_repo.add_reaction.assert_called_once_with(TEST_MESSAGE, EMOJI_STAR, USER_A)


class TestStarReferenceRedirect:
    async def test_handle_star_add_uses_reference(self, make_starboard_guild, mock_sb_and_msg_repos):
        from unittest.mock import AsyncMock, patch

        from attubot.starboard import handle_star_add

        sb_repo, msg_repo = mock_sb_and_msg_repos
        make_starboard_guild()

        response_id = TEST_STARBOARD_MSG + 1
        response_doc = _make_msg_doc(message_id=response_id, channel_id=TEST_CHANNEL, starboard_reference_id=TEST_MESSAGE)
        original_doc = _make_msg_doc(author_id=TEST_AUTHOR)
        msg_repo.get = AsyncMock(side_effect=[response_doc, original_doc, original_doc])
        sb_repo.get = AsyncMock(return_value=None)

        updated = _make_star_doc(reactions={EMOJI_STAR: [USER_A]}, total_reactions=1)
        sb_repo.add_reaction = AsyncMock(return_value=updated)

        with patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock):
            await handle_star_add(TEST_GUILD, TEST_CHANNEL, response_id, user_id=USER_A, emoji_str=EMOJI_STAR)

        sb_repo.add_reaction.assert_called_once_with(TEST_MESSAGE, EMOJI_STAR, USER_A)

    async def test_handle_star_remove_uses_reference(self, make_starboard_guild, mock_sb_and_msg_repos):
        from unittest.mock import AsyncMock, patch

        from attubot.starboard import handle_star_remove

        sb_repo, msg_repo = mock_sb_and_msg_repos
        make_starboard_guild()

        response_id = TEST_STARBOARD_MSG + 2
        response_doc = _make_msg_doc(message_id=response_id, starboard_reference_id=TEST_MESSAGE)
        msg_repo.get = AsyncMock(return_value=response_doc)
        sb_repo.remove_reaction = AsyncMock(return_value=_make_star_doc(reactions={EMOJI_STAR: []}, total_reactions=0))

        with patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock):
            await handle_star_remove(TEST_GUILD, TEST_CHANNEL, response_id, user_id=USER_A, emoji_str=EMOJI_STAR)

        sb_repo.remove_reaction.assert_called_once_with(TEST_MESSAGE, EMOJI_STAR, USER_A)


# ---- super reaction (burst) tests ----


def test_weighted_count_normal_only():
    assert _weighted_count(EMOJI_STAR, {EMOJI_STAR: [USER_A, USER_B]}, {}) == 2.0


def test_weighted_count_super_only():
    assert _weighted_count(EMOJI_STAR, {}, {EMOJI_STAR: [USER_A, USER_B]}) == 3.0


def test_weighted_count_mixed():
    # 2 normal (2.0) + 1 super (1.5) = 3.5
    assert _weighted_count(EMOJI_STAR, {EMOJI_STAR: [USER_A, USER_B]}, {EMOJI_STAR: [USER_C]}) == 3.5


def test_weighted_count_missing_emoji():
    assert _weighted_count(EMOJI_STAR, {}, {}) == 0.0


def test_fmt_count_whole_number():
    assert _fmt_count(4.0) == '4'


def test_fmt_count_fractional():
    assert _fmt_count(4.5) == '4.5'


def test_fmt_count_one_and_half():
    assert _fmt_count(1.5) == '1.5'


def test_build_content_super_only():
    """one super reactor should display as 1.5"""
    result = build_content({}, JUMP_URL, EMOJI_MAP, super_reactions={EMOJI_STAR: [USER_A]})
    assert f'{EMOJI_STAR} **1.5**' in result
    assert JUMP_URL in result


def test_build_content_normal_and_super_no_double_count():
    """two normal + one super should display as 3.5, not 3"""
    reactions = {EMOJI_STAR: [USER_A, USER_B]}
    super_reactions = {EMOJI_STAR: [USER_C]}
    result = build_content(reactions, JUMP_URL, EMOJI_MAP, super_reactions=super_reactions)
    assert f'{EMOJI_STAR} **3.5**' in result


def test_build_content_super_reaction_sorts_correctly():
    """emoji with higher weighted count (via super) should sort before one with more raw reactors"""
    emoji2 = '🌟'
    emoji_map = {EMOJI_STAR: '#EEDD20', emoji2: '#FF0000'}
    # star: 1 normal + 1 super = 2.5; emoji2: 2 normal = 2.0 - star should win
    reactions = {EMOJI_STAR: [USER_A], emoji2: [USER_A, USER_B]}
    super_reactions = {EMOJI_STAR: [USER_B]}
    result = build_content(reactions, JUMP_URL, emoji_map, super_reactions=super_reactions)
    assert result.index(EMOJI_STAR) < result.index(emoji2)


def test_dominant_color_super_reaction_wins():
    """emoji with lower raw count but higher weighted count should win dominant color"""
    emoji2 = '🌟'
    emoji_map = {EMOJI_STAR: '#EEDD20', emoji2: '#FF0000'}
    # star: 0 normal + 2 super = 3.0; emoji2: 2 normal = 2.0
    reactions = {emoji2: [USER_A, USER_B]}
    super_reactions = {EMOJI_STAR: [USER_A, USER_B]}
    assert dominant_color(reactions, emoji_map, super_reactions=super_reactions) == 0xEEDD20


async def test_handle_star_add_super_calls_add_super_reaction(make_starboard_guild, mock_sb_and_msg_repos):
    """is_burst=True must call add_super_reaction, not add_reaction"""
    from attubot.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    msg_doc = _make_msg_doc(author_id=TEST_AUTHOR)
    msg_repo.get = AsyncMock(return_value=msg_doc)
    sb_repo.get = AsyncMock(return_value=None)

    updated = _make_star_doc(super_reactions={EMOJI_STAR: [USER_A]}, total_reactions=1, weighted_total=1.5)
    sb_repo.add_super_reaction = AsyncMock(return_value=updated)

    with patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock):
        await handle_star_add(TEST_GUILD, TEST_CHANNEL, TEST_MESSAGE, user_id=USER_A, emoji_str=EMOJI_STAR, is_burst=True)

    sb_repo.add_super_reaction.assert_called_once_with(TEST_MESSAGE, EMOJI_STAR, USER_A)
    sb_repo.add_reaction.assert_not_called()


async def test_handle_star_add_normal_does_not_call_super(make_starboard_guild, mock_sb_and_msg_repos):
    """is_burst=False must call add_reaction, not add_super_reaction"""
    from attubot.starboard import handle_star_add

    sb_repo, msg_repo = mock_sb_and_msg_repos
    make_starboard_guild()

    msg_doc = _make_msg_doc(author_id=TEST_AUTHOR)
    msg_repo.get = AsyncMock(return_value=msg_doc)
    sb_repo.get = AsyncMock(return_value=None)

    updated = _make_star_doc(reactions={EMOJI_STAR: [USER_A]}, total_reactions=1, weighted_total=1.0)
    sb_repo.add_reaction = AsyncMock(return_value=updated)

    with patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock):
        await handle_star_add(TEST_GUILD, TEST_CHANNEL, TEST_MESSAGE, user_id=USER_A, emoji_str=EMOJI_STAR, is_burst=False)

    sb_repo.add_reaction.assert_called_once_with(TEST_MESSAGE, EMOJI_STAR, USER_A)
    sb_repo.add_super_reaction.assert_not_called()


async def test_handle_star_remove_super_calls_remove_super_reaction(make_starboard_guild, mock_sb_and_msg_repos):
    """is_burst=True on remove must call remove_super_reaction"""
    from attubot.starboard import handle_star_remove

    sb_repo, _ = mock_sb_and_msg_repos
    make_starboard_guild()

    updated = _make_star_doc(super_reactions={EMOJI_STAR: []}, total_reactions=0, weighted_total=0.0)
    sb_repo.remove_super_reaction = AsyncMock(return_value=updated)

    with patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock):
        await handle_star_remove(TEST_GUILD, TEST_CHANNEL, TEST_MESSAGE, user_id=USER_A, emoji_str=EMOJI_STAR, is_burst=True)

    sb_repo.remove_super_reaction.assert_called_once_with(TEST_MESSAGE, EMOJI_STAR, USER_A)
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
    assert _count_streak([], TEST_AUTHOR) == 0


def test_count_streak_single_match():
    docs = [_make_star_doc(message_id=1001, author_id=TEST_AUTHOR, starboard_message_id=2001)]
    assert _count_streak(docs, TEST_AUTHOR) == 1


def test_count_streak_single_mismatch():
    docs = [_make_star_doc(message_id=1001, author_id=USER_A, starboard_message_id=2001)]
    assert _count_streak(docs, TEST_AUTHOR) == 0


def test_count_streak_three_in_a_row():
    docs = [_make_star_doc(message_id=1000 + i, author_id=TEST_AUTHOR, starboard_message_id=2000 + i) for i in range(3)]
    assert _count_streak(docs, TEST_AUTHOR) == 3


def test_count_streak_five_in_a_row():
    docs = [_make_star_doc(message_id=1000 + i, author_id=TEST_AUTHOR, starboard_message_id=2000 + i) for i in range(5)]
    assert _count_streak(docs, TEST_AUTHOR) == 5


def test_count_streak_eleven_in_a_row():
    docs = [_make_star_doc(message_id=1000 + i, author_id=TEST_AUTHOR, starboard_message_id=2000 + i) for i in range(11)]
    assert _count_streak(docs, TEST_AUTHOR) == 11


def test_count_streak_broken_by_other_author():
    # 2 by TEST_AUTHOR at tail, 1 by USER_A before, then TEST_AUTHOR earlier - streak is 2
    docs = [
        _make_star_doc(message_id=1001, author_id=TEST_AUTHOR, starboard_message_id=2001),
        _make_star_doc(message_id=1002, author_id=USER_A, starboard_message_id=2002),
        _make_star_doc(message_id=1003, author_id=TEST_AUTHOR, starboard_message_id=2003),
        _make_star_doc(message_id=1004, author_id=TEST_AUTHOR, starboard_message_id=2004),
    ]
    assert _count_streak(docs, TEST_AUTHOR) == 2


def test_count_streak_other_author_at_tail():
    docs = [
        _make_star_doc(message_id=1001, author_id=TEST_AUTHOR, starboard_message_id=2001),
        _make_star_doc(message_id=1002, author_id=TEST_AUTHOR, starboard_message_id=2002),
        _make_star_doc(message_id=1003, author_id=USER_A, starboard_message_id=2003),
    ]
    assert _count_streak(docs, TEST_AUTHOR) == 0


def test_count_streak_unordered_input():
    # same docs as three_in_a_row but reversed - should still return 3
    docs = [_make_star_doc(message_id=1000 + i, author_id=TEST_AUTHOR, starboard_message_id=2000 + i) for i in range(3)]
    assert _count_streak(list(reversed(docs)), TEST_AUTHOR) == 3


def test_count_streak_author_in_middle_only():
    docs = [
        _make_star_doc(message_id=1001, author_id=USER_A, starboard_message_id=2001),
        _make_star_doc(message_id=1002, author_id=TEST_AUTHOR, starboard_message_id=2002),
        _make_star_doc(message_id=1003, author_id=USER_B, starboard_message_id=2003),
    ]
    assert _count_streak(docs, TEST_AUTHOR) == 0


# ---- _sweep_message pure function tests ----


def test_sweep_message_streak_3():
    result = _sweep_message(3, TEST_AUTHOR)
    assert result is not None
    assert f'<@{TEST_AUTHOR}>' in result
    assert 'sweeps!' in result
    assert ':broom:' in result


def test_sweep_message_streak_5():
    result = _sweep_message(5, TEST_AUTHOR)
    assert result is not None
    assert 'sweeps more!' in result
    assert ':silver_medal:' in result


def test_sweep_message_streak_11():
    result = _sweep_message(11, TEST_AUTHOR)
    assert result is not None
    assert 'sweeps even more!' in result
    assert ':gold_medal:' in result


def test_sweep_message_streak_0_is_none():
    assert _sweep_message(0, TEST_AUTHOR) is None


def test_sweep_message_streak_1_is_none():
    assert _sweep_message(1, TEST_AUTHOR) is None


def test_sweep_message_streak_2_is_none():
    assert _sweep_message(2, TEST_AUTHOR) is None


def test_sweep_message_streak_4_is_none():
    assert _sweep_message(4, TEST_AUTHOR) is None


def test_sweep_message_streak_6_is_none():
    assert _sweep_message(6, TEST_AUTHOR) is None


def test_sweep_message_streak_10_is_none():
    assert _sweep_message(10, TEST_AUTHOR) is None


def test_sweep_message_streak_12_is_none():
    assert _sweep_message(12, TEST_AUTHOR) is None


def test_sweep_message_mention_format():
    result = _sweep_message(3, TEST_AUTHOR)
    assert result is not None
    assert result.startswith(f'<@{TEST_AUTHOR}>')


# ---- _check_and_announce_sweep integration tests ----


@pytest.fixture
def mock_sb_repo_for_sweep():
    """patch _starboard_repo with a fresh MagicMock for sweep tests"""
    repo = MagicMock()
    repo.all_for_guild = AsyncMock()
    with patch('attubot.starboard._starboard_repo', repo):
        yield repo


async def test_check_and_announce_sweep_sends_on_streak_3(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=TEST_AUTHOR, starboard_message_id=2000 + i) for i in range(3)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(TEST_GUILD, TEST_AUTHOR, channel)

    channel.send.assert_called_once()
    text = channel.send.call_args.kwargs['content']
    assert f'<@{TEST_AUTHOR}>' in text
    assert 'sweeps!' in text
    assert ':broom:' in text


async def test_check_and_announce_sweep_sends_on_streak_5(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=TEST_AUTHOR, starboard_message_id=2000 + i) for i in range(5)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(TEST_GUILD, TEST_AUTHOR, channel)

    channel.send.assert_called_once()
    text = channel.send.call_args.kwargs['content']
    assert 'sweeps more!' in text
    assert ':silver_medal:' in text


async def test_check_and_announce_sweep_sends_on_streak_11(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=TEST_AUTHOR, starboard_message_id=2000 + i) for i in range(11)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(TEST_GUILD, TEST_AUTHOR, channel)

    channel.send.assert_called_once()
    text = channel.send.call_args.kwargs['content']
    assert 'sweeps even more!' in text
    assert ':gold_medal:' in text


async def test_check_and_announce_sweep_no_send_on_streak_2(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=TEST_AUTHOR, starboard_message_id=2000 + i) for i in range(2)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(TEST_GUILD, TEST_AUTHOR, channel)

    channel.send.assert_not_called()


async def test_check_and_announce_sweep_no_send_on_streak_4(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=TEST_AUTHOR, starboard_message_id=2000 + i) for i in range(4)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(TEST_GUILD, TEST_AUTHOR, channel)

    channel.send.assert_not_called()


async def test_check_and_announce_sweep_no_send_when_streak_broken(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    # 2 by TEST_AUTHOR at tail, then USER_A breaks the streak
    docs = [
        _make_star_doc(message_id=1001, author_id=USER_A, starboard_message_id=2001),
        _make_star_doc(message_id=1002, author_id=TEST_AUTHOR, starboard_message_id=2002),
        _make_star_doc(message_id=1003, author_id=TEST_AUTHOR, starboard_message_id=2003),
    ]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(TEST_GUILD, TEST_AUTHOR, channel)

    channel.send.assert_not_called()


async def test_check_and_announce_sweep_ignores_unposted_docs(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    # 3 docs by TEST_AUTHOR but one lacks starboard_message_id - only 2 are "posted"
    docs = [
        _make_star_doc(message_id=1001, author_id=TEST_AUTHOR, starboard_message_id=2001),
        _make_star_doc(message_id=1002, author_id=TEST_AUTHOR, starboard_message_id=2002),
        _make_star_doc(message_id=1003, author_id=TEST_AUTHOR, starboard_message_id=None),
    ]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()

    await _check_and_announce_sweep(TEST_GUILD, TEST_AUTHOR, channel)

    # streak of 2 posted docs - no announce
    channel.send.assert_not_called()


async def test_check_and_announce_sweep_swallows_repo_error(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    repo.all_for_guild = AsyncMock(side_effect=RuntimeError('db error'))
    channel = AsyncMock()

    # must not raise
    await _check_and_announce_sweep(TEST_GUILD, TEST_AUTHOR, channel)

    channel.send.assert_not_called()


async def test_check_and_announce_sweep_swallows_send_error(mock_sb_repo_for_sweep):
    repo = mock_sb_repo_for_sweep
    docs = [_make_star_doc(message_id=1000 + i, author_id=TEST_AUTHOR, starboard_message_id=2000 + i) for i in range(3)]
    repo.all_for_guild = AsyncMock(return_value=docs)
    channel = AsyncMock()
    channel.send = AsyncMock(side_effect=RuntimeError('discord error'))

    # must not raise
    await _check_and_announce_sweep(TEST_GUILD, TEST_AUTHOR, channel)
