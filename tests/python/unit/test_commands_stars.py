"""
AttuBot - Stars Command Unit Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Unit tests for stars command helpers: recheck response formatting,
leaderboard embed construction, random message display, and recheck target resolution.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord

from doom_bot.commands.stars import _build_recheck_response, _cc_top_messages_embed, _leaderboard_embed, _resolve_recheck_target, _show_random_message
from doom_bot.database.models import MessageAuthor, MessageContent, MessageDocument, StarredMessageDocument
from tests.conftest import test_guild


# --- constants ---

sb_channel = 4000000001
msg_channel = 4000000002
author_a = 100000001


def _sb_doc(
    message_id: int = 5001,
    reactions: dict | None = None,
    super_reactions: dict | None = None,
    total_reactions: int = 0,
    weighted_total: float = 0.0,
    starboard_message_id: int | None = None,
) -> StarredMessageDocument:
    r = reactions or {}
    sr = super_reactions or {}
    total = total_reactions or sum(len(v) for v in r.values()) + sum(len(v) for v in sr.values())
    return StarredMessageDocument(
        message_id=message_id,
        channel_id=msg_channel,
        guild_id=test_guild,
        author_id=author_a,
        reactions=r,
        super_reactions=sr,
        total_reactions=total,
        weighted_total=weighted_total,
        starboard_message_id=starboard_message_id,
    )


def _msg_doc(message_id: int = 5001) -> MessageDocument:
    return MessageDocument(
        message_id=message_id,
        guild_id=test_guild,
        channel_id=msg_channel,
        author=MessageAuthor(id=author_a, name='testuser'),
        content=MessageContent(text=f'message {message_id}'),
        created_at=1704067200,
    )


def _make_sb_config(channel_id: int = sb_channel, emojis: dict | None = None):
    cfg = MagicMock()
    cfg.channel_id = channel_id
    cfg.emojis = emojis or {'⭐': '#EEDD20'}
    return cfg


def _make_guild_config(sb=None):
    gc = MagicMock()
    gc.starboard = sb or _make_sb_config()
    return gc


# --- _build_recheck_response ---


class TestBuildRecheckResponse:
    def test_no_stars_counted(self):
        """returns 'no stars counted' when doc_after is None."""
        sb = _make_sb_config()
        result = _build_recheck_response(None, None, sb, test_guild, 5001)
        assert result == 'recheck complete; no stars counted'

    def test_no_stars_empty_reactions(self):
        """returns 'no stars counted' when both reaction dicts are empty."""
        sb = _make_sb_config()
        doc_after = _sb_doc(reactions={}, super_reactions={})
        result = _build_recheck_response(None, doc_after, sb, test_guild, 5001)
        assert result == 'recheck complete; no stars counted'

    def test_normal_reactions_only(self):
        """formats normal reactions without super annotation."""
        sb = _make_sb_config()
        doc_after = _sb_doc(
            reactions={'⭐': [1, 2, 3]},
            super_reactions={},
            total_reactions=3,
            weighted_total=3.0,
        )
        result = _build_recheck_response(None, doc_after, sb, test_guild, 5001)
        assert '⭐ 3' in result
        assert 'super' not in result
        assert 'updated' in result

    def test_super_reactions_only(self):
        """formats super reactions with the (N super) annotation."""
        sb = _make_sb_config()
        doc_after = _sb_doc(
            reactions={},
            super_reactions={'⭐': [1, 2]},
            total_reactions=2,
            weighted_total=3.0,
        )
        result = _build_recheck_response(None, doc_after, sb, test_guild, 5001)
        assert '⭐ 2 (2 super)' in result

    def test_mixed_reactions(self):
        """formats mixed normal + super reactions correctly."""
        sb = _make_sb_config()
        doc_after = _sb_doc(
            reactions={'⭐': [1, 2]},
            super_reactions={'⭐': [3]},
            total_reactions=3,
            weighted_total=3.5,
        )
        result = _build_recheck_response(None, doc_after, sb, test_guild, 5001)
        # normal=2 + super=1 = total 3, with 1 super
        assert '⭐ 3 (1 super)' in result

    def test_multiple_emojis_sorted_by_count(self):
        """multiple emojis are sorted by total count descending."""
        sb = _make_sb_config(emojis={'⭐': '#EEDD20', '🌟': '#FFD700'})
        doc_after = _sb_doc(
            reactions={'⭐': [1], '🌟': [1, 2, 3]},
            super_reactions={},
            total_reactions=4,
            weighted_total=4.0,
        )
        result = _build_recheck_response(None, doc_after, sb, test_guild, 5001)
        # 🌟 has 3 reactions, ⭐ has 1 — 🌟 should come first
        star_pos = result.index('⭐')
        glowing_pos = result.index('🌟')
        assert glowing_pos < star_pos

    def test_status_post_created(self):
        """status is 'post created' when before had no starboard_message_id but after does."""
        sb = _make_sb_config()
        doc_before = _sb_doc(starboard_message_id=None, reactions={'⭐': [1, 2]}, total_reactions=2)
        doc_after = _sb_doc(starboard_message_id=9001, reactions={'⭐': [1, 2]}, total_reactions=2, weighted_total=2.0)
        result = _build_recheck_response(doc_before, doc_after, sb, test_guild, 5001)
        assert 'post created' in result

    def test_status_post_created_from_none(self):
        """status is 'post created' when doc_before is None and after has starboard_message_id."""
        sb = _make_sb_config()
        doc_after = _sb_doc(starboard_message_id=9001, reactions={'⭐': [1, 2]}, total_reactions=2, weighted_total=2.0)
        result = _build_recheck_response(None, doc_after, sb, test_guild, 5001)
        assert 'post created' in result

    def test_status_updated(self):
        """status is 'updated' when total_reactions changed."""
        sb = _make_sb_config()
        doc_before = _sb_doc(reactions={'⭐': [1]}, total_reactions=1)
        doc_after = _sb_doc(reactions={'⭐': [1, 2]}, total_reactions=2, weighted_total=2.0)
        result = _build_recheck_response(doc_before, doc_after, sb, test_guild, 5001)
        assert 'updated' in result

    def test_status_no_change(self):
        """status is 'no change' when total_reactions is unchanged."""
        sb = _make_sb_config()
        doc_before = _sb_doc(reactions={'⭐': [1, 2]}, total_reactions=2)
        doc_after = _sb_doc(reactions={'⭐': [1, 2]}, total_reactions=2, weighted_total=2.0)
        result = _build_recheck_response(doc_before, doc_after, sb, test_guild, 5001)
        assert 'no change' in result

    def test_includes_starboard_link(self):
        """includes the starboard link when the doc has a starboard_message_id and channel."""
        sb = _make_sb_config(channel_id=sb_channel)
        doc_after = _sb_doc(
            reactions={'⭐': [1, 2]},
            total_reactions=2,
            weighted_total=2.0,
            starboard_message_id=9001,
        )
        result = _build_recheck_response(None, doc_after, sb, test_guild, 5001)
        assert f'https://discord.com/channels/{test_guild}/{sb_channel}/9001' in result

    def test_below_threshold_no_post(self):
        """shows 'below threshold, no post' when weighted_total < 2 and no starboard post."""
        sb = _make_sb_config()
        doc_after = _sb_doc(
            reactions={'⭐': [1]},
            total_reactions=1,
            weighted_total=1.0,
        )
        result = _build_recheck_response(None, doc_after, sb, test_guild, 5001)
        assert 'below threshold, no post' in result


# --- _show_random_message ---


class TestShowRandomMessage:
    async def test_found_message(self, mock_ctx_factory, guild):
        """responds with content and embeds when a random starred message is found."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        doc = _sb_doc(reactions={'⭐': [1, 2]}, total_reactions=2)
        msg_doc = _msg_doc()

        mock_sb_repo = AsyncMock()
        mock_sb_repo.get_random = AsyncMock(return_value=doc)
        mock_msg_repo = AsyncMock()
        mock_msg_repo.get = AsyncMock(return_value=msg_doc)
        mock_msg_repo.upsert = AsyncMock()

        with (
            patch('doom_bot.commands.stars._get_sb_repo', return_value=mock_sb_repo),
            patch('doom_bot.commands.stars._get_msg_repo', return_value=mock_msg_repo),
            patch('doom_bot.client.starboard.build_embeds', new_callable=AsyncMock, return_value=[]),
            patch('doom_bot.client.starboard.build_content', return_value='⭐ **2** | https://discord.com/channels/1/2/3'),
            patch('doom_bot.client.starboard.dominant_color', return_value=0x5865F2),
        ):
            await _show_random_message(ctx, min_total=2)

        assert len(ctx._responses) == 1
        assert 'content' in ctx._responses[0]['kwargs']

    async def test_no_match(self, mock_ctx_factory, guild):
        """responds ephemeral when no message matches."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        mock_sb_repo = AsyncMock()
        mock_sb_repo.get_random = AsyncMock(return_value=None)

        with patch('doom_bot.commands.stars._get_sb_repo', return_value=mock_sb_repo):
            await _show_random_message(ctx, min_total=2)

        assert len(ctx._responses) == 1
        assert 'no messages found' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_no_match_exactly_one_star(self, mock_ctx_factory, guild):
        """label says 'exactly 1 star' when max_total=1."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        mock_sb_repo = AsyncMock()
        mock_sb_repo.get_random = AsyncMock(return_value=None)

        with patch('doom_bot.commands.stars._get_sb_repo', return_value=mock_sb_repo):
            await _show_random_message(ctx, min_total=1, max_total=1)

        assert 'exactly 1 star' in ctx._responses[0]['args'][0]

    async def test_repo_not_initialized(self, mock_ctx_factory, guild):
        """responds ephemeral when the starboard repo is not initialized."""
        ctx = mock_ctx_factory(guild_id=test_guild)

        with patch('doom_bot.commands.stars._get_sb_repo', side_effect=RuntimeError('no repo')):
            await _show_random_message(ctx, min_total=2)

        assert 'not initialized' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_guild_config_not_found(self, mock_ctx_factory):
        """responds ephemeral when guild config cannot be loaded."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        mock_sb_repo = AsyncMock()
        mock_sb_repo.get_random = AsyncMock(return_value=_sb_doc())

        with (
            patch('doom_bot.commands.stars._get_sb_repo', return_value=mock_sb_repo),
            patch('doom_bot.commands.stars.config.guild', side_effect=Exception('not found')),
        ):
            await _show_random_message(ctx, min_total=2)

        assert 'guild configuration not found' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_original_message_not_in_db(self, mock_ctx_factory, guild):
        """responds ephemeral when the original message is not in the database."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        doc = _sb_doc(reactions={'⭐': [1, 2]}, total_reactions=2)

        mock_sb_repo = AsyncMock()
        mock_sb_repo.get_random = AsyncMock(return_value=doc)
        mock_msg_repo = AsyncMock()
        mock_msg_repo.get = AsyncMock(return_value=None)

        with (
            patch('doom_bot.commands.stars._get_sb_repo', return_value=mock_sb_repo),
            patch('doom_bot.commands.stars._get_msg_repo', return_value=mock_msg_repo),
        ):
            await _show_random_message(ctx, min_total=2)

        assert 'original message not found' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True


# --- stars_lost ---


class TestStarsLost:
    async def test_lost_calls_show_random_with_max_total_1(self, mock_ctx_factory):
        """stars lost passes min_total=1, max_total=1 to _show_random_message."""
        ctx = mock_ctx_factory(guild_id=test_guild)

        with patch('doom_bot.commands.stars._show_random_message', new_callable=AsyncMock) as mock_show:
            from doom_bot.commands.stars import stars_lost

            await stars_lost(ctx)

        mock_show.assert_called_once_with(ctx, min_total=1, max_total=1)


# --- _leaderboard_embed ---


class TestLeaderboardEmbed:
    async def test_empty_rows(self, mock_ctx_factory):
        """responds ephemeral with 'no data yet' when rows list is empty."""
        ctx = mock_ctx_factory()
        await _leaderboard_embed(ctx, [], 'total_stars', 'stars received', 'Most Stars Received')

        assert len(ctx._responses) == 1
        assert 'no data yet' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_formatting(self, mock_ctx_factory):
        """formats rows as numbered list with user mentions and values."""
        ctx = mock_ctx_factory()
        rows = [
            {'_id': 111, 'total_stars': 50},
            {'_id': 222, 'total_stars': 30},
            {'_id': 333, 'total_stars': 10},
        ]
        await _leaderboard_embed(ctx, rows, 'total_stars', 'stars received', 'Most Stars Received')

        assert len(ctx._responses) == 1
        embed = ctx._responses[0]['kwargs']['embed']
        assert isinstance(embed, discord.Embed)
        assert embed.title == 'Most Stars Received'
        desc = embed.description
        assert desc is not None
        assert '**1.** <@111> - **50** stars received' in desc
        assert '**2.** <@222> - **30** stars received' in desc
        assert '**3.** <@333> - **10** stars received' in desc

    async def test_truncates_at_page_size(self, mock_ctx_factory):
        """only displays up to _PAGE_SIZE entries."""
        ctx = mock_ctx_factory()
        rows = [{'_id': i, 'total_stars': 100 - i} for i in range(15)]
        await _leaderboard_embed(ctx, rows, 'total_stars', 'stars', 'Leaderboard')

        embed = ctx._responses[0]['kwargs']['embed']
        lines = embed.description.strip().split('\n')
        assert len(lines) == 10  # _PAGE_SIZE


# --- _resolve_recheck_target ---


class TestResolveRecheckTarget:
    async def test_normal_channel_passthrough(self, mock_ctx_factory, guild):
        """non-starboard channel returns the original args with force=False."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        guild_config = _make_guild_config()
        discord_msg = MagicMock()

        result = await _resolve_recheck_target(ctx, guild_config, msg_channel, 5001, discord_msg)

        assert result is not None
        ch, mid, msg, force = result
        assert ch == msg_channel
        assert mid == 5001
        assert msg is discord_msg
        assert force is False

    async def test_starboard_channel_bot_message_redirects(self, mock_ctx_factory, guild):
        """bot message in starboard channel redirects to the original message."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        guild_config = _make_guild_config()

        discord_msg = MagicMock()
        discord_msg.author.bot = True

        sb_doc = MagicMock()
        sb_doc.channel_id = msg_channel
        sb_doc.message_id = 7001

        mock_sb_repo = AsyncMock()
        mock_sb_repo.get_by_starboard_message = AsyncMock(return_value=sb_doc)

        orig_discord_msg = MagicMock()
        orig_channel = MagicMock()
        orig_channel.fetch_message = AsyncMock(return_value=orig_discord_msg)

        mock_msg_repo = AsyncMock()
        mock_msg_repo.upsert = AsyncMock()

        with (
            patch('doom_bot.commands.stars._get_sb_repo', return_value=mock_sb_repo),
            patch('doom_bot.commands.stars._get_msg_repo', return_value=mock_msg_repo),
            patch('doom_bot.bot') as mock_bot,
            patch('doom_bot.client.messages.build_message_doc', new_callable=AsyncMock, return_value=_msg_doc(7001)),
        ):
            mock_bot.get_channel.return_value = orig_channel
            result = await _resolve_recheck_target(ctx, guild_config, sb_channel, 9001, discord_msg)

        assert result is not None
        ch, mid, msg, force = result
        assert ch == msg_channel
        assert mid == 7001
        assert msg is orig_discord_msg
        assert force is False

    async def test_starboard_channel_bot_message_not_found(self, mock_ctx_factory, guild):
        """bot message in starboard channel with no matching original returns None."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        guild_config = _make_guild_config()

        discord_msg = MagicMock()
        discord_msg.author.bot = True

        mock_sb_repo = AsyncMock()
        mock_sb_repo.get_by_starboard_message = AsyncMock(return_value=None)

        with patch('doom_bot.commands.stars._get_sb_repo', return_value=mock_sb_repo):
            result = await _resolve_recheck_target(ctx, guild_config, sb_channel, 9001, discord_msg)

        assert result is None
        assert 'no matching original' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_starboard_channel_non_bot_message_force(self, mock_ctx_factory, guild):
        """non-bot message in starboard channel returns force=True."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        guild_config = _make_guild_config()

        discord_msg = MagicMock()
        discord_msg.author.bot = False

        result = await _resolve_recheck_target(ctx, guild_config, sb_channel, 5001, discord_msg)

        assert result is not None
        ch, mid, _msg, force = result
        assert ch == sb_channel
        assert mid == 5001
        assert force is True

    async def test_starboard_channel_bot_fetch_fails(self, mock_ctx_factory, guild):
        """bot message redirect fails when fetching original raises an error."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        guild_config = _make_guild_config()

        discord_msg = MagicMock()
        discord_msg.author.bot = True

        sb_doc = MagicMock()
        sb_doc.channel_id = msg_channel
        sb_doc.message_id = 7001

        mock_sb_repo = AsyncMock()
        mock_sb_repo.get_by_starboard_message = AsyncMock(return_value=sb_doc)

        with (
            patch('doom_bot.commands.stars._get_sb_repo', return_value=mock_sb_repo),
            patch('doom_bot.bot') as mock_bot,
        ):
            mock_bot.get_channel.return_value = None
            mock_bot.fetch_channel = AsyncMock(side_effect=Exception('channel not found'))
            result = await _resolve_recheck_target(ctx, guild_config, sb_channel, 9001, discord_msg)

        assert result is None
        assert 'could not fetch original message' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True


# --- ccboard routing for _show_random_message ---


class TestShowRandomMessageCCBoardRouting:
    async def test_routes_to_ccboard_when_enabled(self, mock_ctx_factory, make_guild):
        """when ccboard.enabled=True, calls _show_ccboard_random instead of legacy path."""
        from doom_bot.config import GuildCCBoard

        gc = make_guild(guild_id=test_guild)
        gc.ccboard = GuildCCBoard(enabled=True, channel_id=sb_channel, emojis={'⭐': 1}, threshold=2, points_label='stars')

        ctx = mock_ctx_factory(guild_id=test_guild)

        with patch('doom_bot.commands.stars._show_ccboard_random', new_callable=AsyncMock) as mock_cc, patch('doom_bot.commands.stars._get_sb_repo') as mock_sb:
            await _show_random_message(ctx, min_total=2)

        mock_cc.assert_called_once()
        mock_sb.assert_not_called()

    async def test_routes_to_legacy_when_ccboard_disabled(self, mock_ctx_factory, make_guild):
        """when ccboard.enabled=False (default), takes the legacy sb_repo path."""
        make_guild(guild_id=test_guild)
        ctx = mock_ctx_factory(guild_id=test_guild)
        mock_sb_repo = AsyncMock()
        mock_sb_repo.get_random = AsyncMock(return_value=None)

        with patch('doom_bot.commands.stars._get_sb_repo', return_value=mock_sb_repo), patch('doom_bot.commands.stars._show_ccboard_random', new_callable=AsyncMock) as mock_cc:
            await _show_random_message(ctx, min_total=2)

        mock_cc.assert_not_called()
        mock_sb_repo.get_random.assert_called_once()

    async def test_ccboard_random_no_match_responds_ephemeral(self, mock_ctx_factory, make_guild):
        """ccboard path: no matching entry → 'no messages found' response."""
        from doom_bot.config import GuildCCBoard

        gc = make_guild(guild_id=test_guild)
        gc.ccboard = GuildCCBoard(enabled=True, channel_id=sb_channel, emojis={'⭐': 1}, threshold=2, points_label='stars')

        ctx = mock_ctx_factory(guild_id=test_guild)
        mock_entry_repo = AsyncMock()
        mock_entry_repo.get_random = AsyncMock(return_value=None)

        with patch('doom_bot.commands.stars._get_entry_repo', return_value=mock_entry_repo):
            await _show_random_message(ctx, min_total=2)

        assert 'no messages found' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_ccboard_not_initialized_responds_ephemeral(self, mock_ctx_factory, make_guild):
        """ccboard path: entry repo not initialized → 'ccboard not initialized' response."""
        from doom_bot.config import GuildCCBoard

        gc = make_guild(guild_id=test_guild)
        gc.ccboard = GuildCCBoard(enabled=True, channel_id=sb_channel, emojis={'⭐': 1}, threshold=2, points_label='stars')

        ctx = mock_ctx_factory(guild_id=test_guild)

        with patch('doom_bot.commands.stars._get_entry_repo', side_effect=RuntimeError('not initialized')):
            await _show_random_message(ctx, min_total=2)

        assert 'ccboard not initialized' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True


# --- _cc_top_messages_embed ---


class TestCCTopMessagesEmbed:
    async def test_empty_entries_responds_ephemeral(self, mock_ctx_factory):
        """responds ephemeral when entries list is empty."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        await _cc_top_messages_embed(ctx, [], test_guild, 'Top Messages')

        assert 'no data yet' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_formats_jump_url_and_stars(self, mock_ctx_factory):
        """formats entries as numbered list with jump urls and star counts."""
        ctx = mock_ctx_factory(guild_id=test_guild)
        entry = MagicMock()
        entry.channel_id = 4000000001
        entry.message_id = 5001
        entry.positive_points = 7

        await _cc_top_messages_embed(ctx, [entry], test_guild, 'Top Messages')

        embed = ctx._responses[0]['kwargs']['embed']
        desc = embed.description
        assert str(5001) in desc
        assert '7' in desc
        assert 'stars' in desc


# --- ccboard leaderboard routing ---


class TestLeaderboardCCBoardRouting:
    async def test_most_stars_routes_to_ccboard_entry_repo(self, mock_ctx_factory, make_guild):
        """most-stars uses entry_repo.leaderboard_most_stars when ccboard.enabled=True."""
        from doom_bot.config import GuildCCBoard

        gc = make_guild(guild_id=test_guild)
        gc.ccboard = GuildCCBoard(enabled=True, channel_id=sb_channel, emojis={'⭐': 1}, threshold=2, points_label='stars')

        ctx = mock_ctx_factory(guild_id=test_guild)
        mock_entry_repo = AsyncMock()
        mock_entry_repo.leaderboard_most_stars = AsyncMock(return_value=[])

        with patch('doom_bot.commands.stars._get_entry_repo', return_value=mock_entry_repo), patch('doom_bot.commands.stars._get_sb_repo') as mock_sb:
            from doom_bot.commands.stars import stars_most_stars

            await stars_most_stars(ctx)

        mock_entry_repo.leaderboard_most_stars.assert_called_once()
        mock_sb.assert_not_called()

    async def test_most_stars_routes_to_legacy_when_disabled(self, mock_ctx_factory, make_guild):
        """most-stars uses sb_repo when ccboard.enabled=False."""
        make_guild(guild_id=test_guild)
        ctx = mock_ctx_factory(guild_id=test_guild)
        mock_sb_repo = AsyncMock()
        mock_sb_repo.leaderboard_most_stars = AsyncMock(return_value=[])

        with patch('doom_bot.commands.stars._get_sb_repo', return_value=mock_sb_repo), patch('doom_bot.commands.stars._get_entry_repo') as mock_entry:
            from doom_bot.commands.stars import stars_most_stars

            await stars_most_stars(ctx)

        mock_sb_repo.leaderboard_most_stars.assert_called_once()
        mock_entry.assert_not_called()

    async def test_most_given_routes_to_reaction_repo(self, mock_ctx_factory, make_guild):
        """most-given uses reaction_repo.leaderboard_most_given when ccboard.enabled=True."""
        from doom_bot.config import GuildCCBoard

        gc = make_guild(guild_id=test_guild)
        gc.ccboard = GuildCCBoard(enabled=True, channel_id=sb_channel, emojis={'⭐': 1}, threshold=2, points_label='stars')

        ctx = mock_ctx_factory(guild_id=test_guild)
        mock_reaction_repo = AsyncMock()
        mock_reaction_repo.leaderboard_most_given = AsyncMock(return_value=[])

        with patch('doom_bot.commands.stars._get_cc_reaction_repo', return_value=mock_reaction_repo), patch('doom_bot.commands.stars._get_sb_repo') as mock_sb:
            from doom_bot.commands.stars import stars_most_given

            await stars_most_given(ctx)

        mock_reaction_repo.leaderboard_most_given.assert_called_once()
        mock_sb.assert_not_called()

    async def test_top_messages_ccboard_only(self, mock_ctx_factory, make_guild):
        """top-messages returns ephemeral when ccboard is disabled."""
        make_guild(guild_id=test_guild)
        ctx = mock_ctx_factory(guild_id=test_guild)

        from doom_bot.commands.stars import stars_top_messages

        await stars_top_messages(ctx)

        assert 'only available when ccboard is enabled' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_top_messages_calls_entry_repo_when_enabled(self, mock_ctx_factory, make_guild):
        """top-messages calls leaderboard_top_messages when ccboard.enabled=True."""
        from doom_bot.config import GuildCCBoard

        gc = make_guild(guild_id=test_guild)
        gc.ccboard = GuildCCBoard(enabled=True, channel_id=sb_channel, emojis={'⭐': 1}, threshold=2, points_label='stars')

        ctx = mock_ctx_factory(guild_id=test_guild)
        mock_entry_repo = AsyncMock()
        mock_entry_repo.leaderboard_top_messages = AsyncMock(return_value=[])

        with patch('doom_bot.commands.stars._get_entry_repo', return_value=mock_entry_repo):
            from doom_bot.commands.stars import stars_top_messages

            await stars_top_messages(ctx)

        mock_entry_repo.leaderboard_top_messages.assert_called_once()


# --- ccboard routing for stars_recheck ---


class TestRecheckCCBoardRouting:
    async def test_recheck_routes_to_auditor_when_ccboard_enabled(self, mock_ctx_factory, make_guild):
        """when ccboard.enabled=True, reconcile_entry is called and its summary responded."""
        from doom_bot.ccboard.auditor import auditor_task
        from doom_bot.config import GuildCCBoard

        gc = make_guild(guild_id=test_guild)
        gc.ccboard = GuildCCBoard(enabled=True, channel_id=sb_channel, emojis={'⭐': 1}, threshold=2, points_label='stars')

        ctx = mock_ctx_factory(guild_id=test_guild)
        mock_result = MagicMock()
        mock_result.summary = 'msg=5001 add=0 replace=0 remove=0 recount=0 match=2 strip_invalid=0 strip_extras=0 APPLIED'

        link = f'https://discord.com/channels/{test_guild}/{msg_channel}/5001'

        with patch.object(auditor_task, 'reconcile_entry', new_callable=AsyncMock, return_value=mock_result) as mock_reconcile:
            from doom_bot.commands.stars import stars_recheck

            await stars_recheck(ctx, link)

        mock_reconcile.assert_called_once_with(test_guild, 5001, dry_run=False)
        assert ctx._responses[0]['args'][0] == mock_result.summary

    async def test_recheck_routes_to_legacy_when_ccboard_disabled(self, mock_ctx_factory, make_guild):
        """when ccboard.enabled=False, legacy _get_sb_repo path is taken."""
        make_guild(guild_id=test_guild)

        ctx = mock_ctx_factory(guild_id=test_guild)
        link = f'https://discord.com/channels/{test_guild}/{msg_channel}/5001'

        from doom_bot.ccboard.auditor import auditor_task

        with (
            patch('doom_bot.commands.stars._get_sb_repo', side_effect=RuntimeError('not init')) as mock_sb,
            patch.object(auditor_task, 'reconcile_entry', new_callable=AsyncMock) as mock_reconcile,
        ):
            from doom_bot.commands.stars import stars_recheck

            await stars_recheck(ctx, link)

        mock_reconcile.assert_not_called()
        mock_sb.assert_called_once()
        assert 'not initialized' in ctx._responses[0]['args'][0]

    async def test_recheck_invalid_link_responds_ephemeral(self, mock_ctx_factory):
        """invalid link responds ephemeral with 'invalid message link'."""
        ctx = mock_ctx_factory(guild_id=test_guild)

        from doom_bot.commands.stars import stars_recheck

        await stars_recheck(ctx, 'not-a-link')

        assert 'invalid message link' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True
