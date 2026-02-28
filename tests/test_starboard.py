"""
AttuBot - Starboard Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from unittest.mock import AsyncMock, patch

import pytest

from attubot.database.models import MessageDocument, StarredMessageDocument
from attubot.starboard import (
    _is_image,
    _parse_color,
    build_content,
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
    counts, url = parse_starboard_content(f'{EMOJI_STAR} **3** | no url here')
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


# ---- make_message_doc helper ----


def _make_msg_doc(**kwargs) -> MessageDocument:
    defaults = {
        'message_id': TEST_MESSAGE,
        'guild_id': TEST_GUILD,
        'channel_id': TEST_CHANNEL,
        'author_id': TEST_AUTHOR,
        'author_name': 'TestUser',
        'content': 'hello world',
        'created_at': 1704067200,
    }
    defaults.update(kwargs)
    return MessageDocument(**defaults)


def _make_star_doc(**kwargs) -> StarredMessageDocument:
    defaults = {
        'message_id': TEST_MESSAGE,
        'channel_id': TEST_CHANNEL,
        'guild_id': TEST_GUILD,
        'author_id': TEST_AUTHOR,
    }
    defaults.update(kwargs)
    return StarredMessageDocument(**defaults)


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
    sb_repo.get = AsyncMock(return_value=None)   # no existing document

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
            starboard_message_id=0,    # no sb post - skips the second fetch
        )
        mock_sb_repo.all_for_guild = AsyncMock(return_value=[doc])

        orig_msg = MagicMock()
        orig_msg.author = MagicMock(id=TEST_AUTHOR)
        orig_msg.reactions = [self._make_reaction(EMOJI_STAR, [USER_A, USER_B])]

        orig_channel = AsyncMock()
        orig_channel.fetch_message = AsyncMock(return_value=orig_msg)

        # bot and _sync_starboard_post are imported inside the function, so patch at source
        with patch('attubot.bot') as mock_bot, \
             patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
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

        with patch('attubot.bot') as mock_bot, \
             patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
            mock_bot.get_channel = MagicMock(return_value=orig_channel)
            await job_recount_starboard(TEST_GUILD)

        mock_sync.assert_called_once()
        mock_sb_repo.upsert.assert_called_once()

    async def test_skip_when_message_not_found(self, make_starboard_guild, mock_sb_repo):
        """discord.NotFound on the original message should not raise - just count as skipped"""
        import discord
        from unittest.mock import AsyncMock, MagicMock, patch

        from attubot.commands.fix import job_recount_starboard

        make_starboard_guild()

        doc = _make_star_doc(reactions={EMOJI_STAR: [USER_A]}, total_reactions=1)
        mock_sb_repo.all_for_guild = AsyncMock(return_value=[doc])

        orig_channel = AsyncMock()
        orig_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))

        with patch('attubot.bot') as mock_bot, \
             patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
            mock_bot.get_channel = MagicMock(return_value=orig_channel)
            await job_recount_starboard(TEST_GUILD)   # must not raise

        mock_sync.assert_not_called()

    async def test_safe_edit_returns_none_on_http_exception(self):
        """_safe_edit should return None and log a warning rather than raising"""
        import discord
        from unittest.mock import AsyncMock, MagicMock

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

        with patch('attubot.bot') as mock_bot, \
             patch('attubot.starboard._sync_starboard_post', new_callable=AsyncMock) as mock_sync:
            mock_bot.get_channel = MagicMock(return_value=orig_channel)
            await job_recount_starboard(TEST_GUILD)

        # same users, just different storage order - should be skipped
        mock_sync.assert_not_called()


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
        parsed = parse_jump_url(url)
        assert parsed is not None
        assert parsed[2] == exp_msg_id
