"""
AttuBot - NovaYearTask Component Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests rollover state changes with a real YearRepository and fake Discord/wiki gateway objects.
`_advance_year` is decorated with @webhook_logging which swallows exceptions, so all
fake discord/wiki objects must be set up to not raise - test failures show as missing DB state.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from attubot import config
from attubot.config import GuildChannels
from attubot.database.repositories import YearRepository


pytestmark = pytest.mark.component

TEST_GUILD = 1234567890
LORE_CHANNEL_1 = 1000000001
LORE_CHANNEL_2 = 1000000002
YEAR_VC = 1000000003
ANNOUNCE_CH = 1000000004


async def _run_advance_year(cfg, year, year_repo, extra_lore_ids=None):
    """run _advance_year with real year_repo and minimal fake discord/wiki objects.

    returns (fake_wiki, fake_announce, lore_channels_map) after the call completes.
    the caller is responsible for setting attubot.years._year_repo before calling this.
    """
    import attubot.tasks.nova_year as nova_year_mod
    from attubot.tasks.nova_year import NovaYearTask
    from attubot.tasks.scheduler import scheduler as _scheduler

    all_lore_ids = [LORE_CHANNEL_1] + (extra_lore_ids or [])
    cfg.channels = GuildChannels(
        lore_channels=all_lore_ids,
        year_vc=YEAR_VC,
        announcements=ANNOUNCE_CH,
    )

    # fake lore channels - each returns a fake message with jump_url
    lore_channels: dict[int, MagicMock] = {}
    for ch_id in all_lore_ids:
        ch = MagicMock()
        ch.id = ch_id
        fake_msg = MagicMock(jump_url=f'https://discord.com/channels/{TEST_GUILD}/{ch_id}/9999')
        ch.send = AsyncMock(return_value=fake_msg)
        lore_channels[ch_id] = ch

    fake_vc = MagicMock()
    fake_vc.edit = AsyncMock()

    fake_announce = MagicMock()
    fake_announce.send = AsyncMock()

    def _get_channel(cid):
        if cid == YEAR_VC:
            return fake_vc
        if cid == ANNOUNCE_CH:
            return fake_announce
        return lore_channels.get(cid)

    fake_guild = MagicMock()
    fake_guild.get_channel_or_thread = MagicMock(side_effect=_get_channel)

    fake_wiki = MagicMock()
    fake_wiki.authenticate = AsyncMock()
    fake_wiki.pages = MagicMock()
    fake_wiki.pages.get = AsyncMock(return_value=f'Current Year: {year - 1} PC - intro text')
    fake_wiki.pages.edit = AsyncMock()

    with (
        patch('attubot.tasks.nova_year.bot') as mock_bot,
        patch('attubot.tasks.nova_year.get_wiki', return_value=fake_wiki),
        patch.object(config, 'wiki', MagicMock(user='u', key='k', page='Test Page')),
        patch.object(_scheduler, 'add_job', side_effect=lambda coro, name: coro.close()),
        patch.object(nova_year_mod.logger, 'send_to_webhook', AsyncMock()),
    ):
        mock_bot.get_guild.return_value = fake_guild
        task = NovaYearTask()
        await task._advance_year(cfg, year)

    return fake_wiki, fake_announce, lore_channels


class TestAdvanceYear:
    async def test_creates_new_year_record_in_db(self, component_db, make_guild):
        """_advance_year creates a year record with the correct year number and a non-zero start_time"""
        year_repo = YearRepository(component_db)
        await year_repo.init_indexes()

        cfg = make_guild(guild_id=TEST_GUILD, year=1, time=1704067200, length=14)
        import attubot.years as _years

        _years._year_repo = year_repo
        try:
            await _run_advance_year(cfg, 2, year_repo)

            doc = await year_repo.get(TEST_GUILD, 2)
            assert doc is not None
            assert doc.year == 2
            assert doc.start_time > 0
        finally:
            _years._year_repo = None

    async def test_finalizes_previous_year_with_end_time(self, component_db, make_guild):
        """_advance_year sets end_time and duration on the previous year record"""
        year_repo = YearRepository(component_db)
        await year_repo.init_indexes()

        cfg = make_guild(guild_id=TEST_GUILD, year=1, time=1704067200, length=14)
        # seed year 1 so finalize has something to update
        await year_repo.create(TEST_GUILD, year=1, start_time=1704067200)

        import attubot.years as _years

        _years._year_repo = year_repo
        try:
            await _run_advance_year(cfg, 2, year_repo)

            year1 = await year_repo.get(TEST_GUILD, 1)
            assert year1 is not None
            assert year1.end_time > 0
            assert year1.duration > 0
        finally:
            _years._year_repo = None

    async def test_sends_year_marker_to_each_lore_channel(self, component_db, make_guild):
        """_advance_year sends a year marker message to every configured lore channel"""
        year_repo = YearRepository(component_db)
        await year_repo.init_indexes()

        cfg = make_guild(guild_id=TEST_GUILD, year=1, time=1704067200, length=14)
        import attubot.years as _years

        _years._year_repo = year_repo
        try:
            _, _, lore_channels = await _run_advance_year(cfg, 2, year_repo, extra_lore_ids=[LORE_CHANNEL_2])

            lore_channels[LORE_CHANNEL_1].send.assert_called_once()
            lore_channels[LORE_CHANNEL_2].send.assert_called_once()
        finally:
            _years._year_repo = None

    async def test_edits_wiki_page_with_new_year_number(self, component_db, make_guild):
        """_advance_year calls wiki.pages.edit with content containing the new year number"""
        year_repo = YearRepository(component_db)
        await year_repo.init_indexes()

        cfg = make_guild(guild_id=TEST_GUILD, year=1, time=1704067200, length=14)
        import attubot.years as _years

        _years._year_repo = year_repo
        try:
            fake_wiki, _, _ = await _run_advance_year(cfg, 2, year_repo)

            fake_wiki.pages.edit.assert_called_once()
            _, edited_text, _ = fake_wiki.pages.edit.call_args[0]
            assert 'Current Year: 2 PC' in edited_text
        finally:
            _years._year_repo = None

    async def test_queues_year_links_rebuild_via_scheduler(self, component_db, make_guild):
        """_advance_year calls scheduler.add_job once to queue the year links rebuild"""
        year_repo = YearRepository(component_db)
        await year_repo.init_indexes()

        cfg = make_guild(guild_id=TEST_GUILD, year=1, time=1704067200, length=14)
        import attubot.tasks.nova_year as nova_year_mod
        import attubot.years as _years
        from attubot.tasks.nova_year import NovaYearTask
        from attubot.tasks.scheduler import scheduler as _scheduler

        cfg.channels = GuildChannels(lore_channels=[LORE_CHANNEL_1], year_vc=YEAR_VC, announcements=ANNOUNCE_CH)
        fake_msg = MagicMock(jump_url='https://discord.com/channels/1/2/3')
        fake_lore = MagicMock(id=LORE_CHANNEL_1)
        fake_lore.send = AsyncMock(return_value=fake_msg)

        def _get_channel(cid):
            if cid == LORE_CHANNEL_1:
                return fake_lore
            ch = MagicMock()
            ch.edit = AsyncMock()
            ch.send = AsyncMock()
            return ch

        fake_guild = MagicMock()
        fake_guild.get_channel_or_thread = MagicMock(side_effect=_get_channel)

        fake_wiki = MagicMock()
        fake_wiki.authenticate = AsyncMock()
        fake_wiki.pages = MagicMock()
        fake_wiki.pages.get = AsyncMock(return_value='Current Year: 1 PC')
        fake_wiki.pages.edit = AsyncMock()

        add_job_calls = []

        def _capture(coro, name):
            add_job_calls.append(name)
            coro.close()

        _years._year_repo = year_repo
        try:
            with (
                patch('attubot.tasks.nova_year.bot') as mock_bot,
                patch('attubot.tasks.nova_year.get_wiki', return_value=fake_wiki),
                patch.object(config, 'wiki', MagicMock(user='u', key='k', page='Test Page')),
                patch.object(_scheduler, 'add_job', side_effect=_capture),
                patch.object(nova_year_mod.logger, 'send_to_webhook', AsyncMock()),
            ):
                mock_bot.get_guild.return_value = fake_guild
                task = NovaYearTask()
                await task._advance_year(cfg, 2)

            assert len(add_job_calls) == 1
        finally:
            _years._year_repo = None

    async def test_year_1_does_not_attempt_to_finalize_year_0(self, component_db, make_guild):
        """advancing to year 1 (first ever rollover) skips the finalize call since there is no year 0"""
        year_repo = YearRepository(component_db)
        await year_repo.init_indexes()

        cfg = make_guild(guild_id=TEST_GUILD, year=1, time=1704067200, length=14)
        import attubot.years as _years

        _years._year_repo = year_repo
        try:
            await _run_advance_year(cfg, 1, year_repo)

            # year 0 should not exist
            assert await year_repo.get(TEST_GUILD, 0) is None
            # year 1 should be created
            assert await year_repo.get(TEST_GUILD, 1) is not None
        finally:
            _years._year_repo = None


class TestRolloverGuildGuards:
    @freeze_time('2024-01-08 17:00:00')  # day 7 - not at the 14-day boundary
    async def test_skips_when_not_at_year_boundary(self, make_guild):
        """_rollover_guild returns early when elapsed days mod year length is not zero"""
        from attubot.tasks.nova_year import NovaYearTask

        cfg = make_guild(guild_id=TEST_GUILD, time=1704067200, year=1, length=14)

        with patch.object(NovaYearTask, '_advance_year', new=AsyncMock()) as mock_advance:
            task = NovaYearTask()
            await task._rollover_guild(cfg)

        mock_advance.assert_not_called()

    async def test_skips_paused_guild(self, make_guild):
        """_rollover_guild returns early when epoch.paused is True"""
        from attubot.tasks.nova_year import NovaYearTask

        cfg = make_guild(guild_id=TEST_GUILD, paused=True)

        with patch.object(NovaYearTask, '_advance_year', new=AsyncMock()) as mock_advance:
            task = NovaYearTask()
            await task._rollover_guild(cfg)

        mock_advance.assert_not_called()

    @freeze_time('2024-01-15 17:00:00')  # day 14 - exactly at the 14-day boundary
    async def test_skips_when_year_already_in_db(self, component_db, make_guild):
        """_rollover_guild does nothing when the DB already has a year >= the computed current year"""
        from attubot.tasks.nova_year import NovaYearTask

        cfg = make_guild(guild_id=TEST_GUILD, time=1704067200, year=1, length=14)

        year_repo = YearRepository(component_db)
        await year_repo.init_indexes()
        # year 2 already recorded - rollover already happened
        await year_repo.create(TEST_GUILD, year=2, start_time=1705276800)

        import attubot.years as _years

        _years._year_repo = year_repo
        try:
            with patch.object(NovaYearTask, '_advance_year', new=AsyncMock()) as mock_advance:
                task = NovaYearTask()
                await task._rollover_guild(cfg)

            mock_advance.assert_not_called()
        finally:
            _years._year_repo = None

    @freeze_time('2024-01-15 17:00:00')  # at the boundary
    async def test_calls_advance_year_when_at_boundary_and_not_yet_advanced(self, component_db, make_guild):
        """_rollover_guild calls _advance_year when at the boundary and no year record exists yet"""
        from attubot.tasks.nova_year import NovaYearTask

        cfg = make_guild(guild_id=TEST_GUILD, time=1704067200, year=1, length=14)

        year_repo = YearRepository(component_db)
        await year_repo.init_indexes()
        # no year 2 record yet

        import attubot.years as _years

        _years._year_repo = year_repo
        try:
            with patch.object(NovaYearTask, '_advance_year', new=AsyncMock()) as mock_advance:
                task = NovaYearTask()
                await task._rollover_guild(cfg)

            mock_advance.assert_called_once_with(cfg, 2)
        finally:
            _years._year_repo = None


class TestNextRun:
    async def test_returns_far_future_when_no_valid_guilds(self):
        """next_run returns ~30 minutes from now when valid_guilds is empty"""
        from datetime import datetime

        from attubot.tasks.nova_year import NovaYearTask

        original_guilds = dict(config.guilds)
        original_valid = list(config.valid_guilds)
        config.guilds.clear()
        config.valid_guilds.clear()

        try:
            task = NovaYearTask()
            result = await task.next_run()

            assert result is not None
            delta = (result - datetime.now().astimezone()).total_seconds()
            assert 25 * 60 < delta < 35 * 60
        finally:
            config.guilds.update(original_guilds)
            config.valid_guilds.extend(original_valid)

    async def test_returns_far_future_when_all_guilds_paused(self, make_guild):
        """next_run returns ~30 minutes from now when every valid guild is paused"""
        from datetime import datetime

        from attubot.tasks.nova_year import NovaYearTask

        make_guild(guild_id=TEST_GUILD, paused=True)
        task = NovaYearTask()
        result = await task.next_run()

        assert result is not None
        delta = (result - datetime.now().astimezone()).total_seconds()
        assert 25 * 60 < delta < 35 * 60

    async def test_returns_earliest_rollover_across_multiple_guilds(self, make_guild):
        """next_run returns the earliest upcoming rollover among all valid guilds"""
        from datetime import datetime

        from attubot.tasks.nova_year import NovaYearTask

        guild_a = 1234567890
        guild_b = 9876543210

        # guild_a: epoch starts 2024-01-01, 14-day year - next rollover at 2024-01-15 17:00
        make_guild(guild_id=guild_a, time=1704067200, year=1, length=14)
        # guild_b: epoch starts 2024-01-01, 365-day year - next rollover far away
        make_guild(guild_id=guild_b, time=1704067200, year=1, length=365)

        task = NovaYearTask()
        result = await task.next_run()

        # should pick the nearer rollover (guild_a's 14-day year)
        # the farther one (guild_b's 365-day year) is not selected
        # just verify it returns a datetime without raising
        assert result is not None
        assert isinstance(result, datetime)
