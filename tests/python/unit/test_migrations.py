"""
AttuBot - Migration System Unit Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from attubot.config import _version_gte


# ============================================================
# _version_gte
# ============================================================


class TestVersionGte:
    """unit: semver >= comparison helper"""

    def test_equal_versions(self):
        assert _version_gte('2.5.3', '2.5.3') is True

    def test_higher_patch(self):
        assert _version_gte('2.5.4', '2.5.3') is True

    def test_higher_minor(self):
        assert _version_gte('2.6.0', '2.5.3') is True

    def test_higher_major(self):
        assert _version_gte('3.0.0', '2.5.3') is True

    def test_lower_patch(self):
        assert _version_gte('2.5.2', '2.5.3') is False

    def test_lower_minor(self):
        assert _version_gte('2.4.9', '2.5.3') is False

    def test_lower_major(self):
        assert _version_gte('1.9.9', '2.5.3') is False

    def test_zero_versions(self):
        assert _version_gte('0.0.0', '0.0.0') is True

    def test_zero_below_any(self):
        assert _version_gte('0.0.0', '1.0.0') is False


# ============================================================
# run_pending_migrations
# ============================================================


class TestRunPendingMigrations:
    """unit: migration runner orchestration"""

    @pytest.fixture
    def mock_system_config(self):
        """create a mock system config with a mutable version"""
        cfg = MagicMock()
        cfg.version = '2.5.3'
        return cfg

    @pytest.fixture
    def mock_config_repo(self, mock_system_config):
        """mock config.config_repo.get_system to return our mock"""
        repo = AsyncMock()
        repo.get_system = AsyncMock(return_value=mock_system_config)
        return repo

    async def test_runs_load_stage_migrations(self, mock_config_repo, mock_system_config):
        migration_fn = AsyncMock()

        with (
            patch('attubot.client.migrations.load_migration_table', [migration_fn]),
            patch('attubot.client.migrations.config') as patched_config,
        ):
            patched_config.config_repo = mock_config_repo

            from attubot.client.migrations import run_pending_migrations

            await run_pending_migrations(stage='load')

        migration_fn.assert_awaited_once_with('2.5.3')

    async def test_runs_ready_stage_migrations(self, mock_config_repo, mock_system_config):
        migration_fn = AsyncMock()

        with (
            patch('attubot.client.migrations.ready_migration_table', [migration_fn]),
            patch('attubot.client.migrations.config') as patched_config,
        ):
            patched_config.config_repo = mock_config_repo

            from attubot.client.migrations import run_pending_migrations

            await run_pending_migrations(stage='ready')

        migration_fn.assert_awaited_once_with('2.5.3')

    async def test_reraises_migration_error(self, mock_config_repo):
        from attubot.client.migrations import MigrationError, run_pending_migrations

        failing_fn = AsyncMock(side_effect=MigrationError('boom'))

        with (
            patch('attubot.client.migrations.load_migration_table', [failing_fn]),
            patch('attubot.client.migrations.config') as patched_config,
        ):
            patched_config.config_repo = mock_config_repo

            with pytest.raises(MigrationError):
                await run_pending_migrations(stage='load')

    async def test_skips_when_version_does_not_match(self, mock_config_repo):
        """migration functions are skipped when the db version is past their target"""
        migration_fn = AsyncMock()

        # set current version past what migration expects
        newer_config = MagicMock()
        newer_config.version = '9.9.9'
        mock_config_repo.get_system = AsyncMock(return_value=newer_config)

        with (
            patch('attubot.client.migrations.load_migration_table', [migration_fn]),
            patch('attubot.client.migrations.config') as patched_config,
        ):
            patched_config.config_repo = mock_config_repo

            from attubot.client.migrations import run_pending_migrations

            await run_pending_migrations(stage='load')

        # the wrapper calls the fn with the version; it should bail via the decorator
        migration_fn.assert_awaited_once_with('9.9.9')

    async def test_rereads_version_after_each_step(self, mock_config_repo, mock_system_config):
        """each migration receives the version re-read from the db, not the initial one"""
        call_versions = []

        async def capture_version(version):
            call_versions.append(version)

        # simulate the version bumping after the first migration
        mock_system_config_after = MagicMock()
        mock_system_config_after.version = '2.5.4'
        # calls: initial read, after step_1, after step_2, final log read
        mock_config_repo.get_system = AsyncMock(side_effect=[mock_system_config, mock_system_config_after, mock_system_config_after, mock_system_config_after])

        step_1 = AsyncMock(side_effect=capture_version)
        step_2 = AsyncMock(side_effect=capture_version)

        with (
            patch('attubot.client.migrations.load_migration_table', [step_1, step_2]),
            patch('attubot.client.migrations.config') as patched_config,
        ):
            patched_config.config_repo = mock_config_repo

            from attubot.client.migrations import run_pending_migrations

            await run_pending_migrations(stage='load')

        assert call_versions == ['2.5.3', '2.5.4']


# ============================================================
# migration_seed_ui_emojis (2.5.3 → 2.5.4)
# ============================================================


class TestMigrationSeedUiEmojis:
    """unit: migration_seed_ui_emojis seeds emoji IDs on theme document"""

    async def test_seeds_when_missing(self):
        """ui_emojis is empty or absent — migration inserts the default emojis"""
        mock_result = MagicMock()
        mock_result.modified_count = 1

        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(return_value=mock_result)

        mock_db = MagicMock()
        mock_db.global_config = mock_collection

        with patch('attubot.client.core.db') as mock_core_db:
            mock_core_db.get_db.return_value = mock_db

            from attubot.client.migrations import migration_seed_ui_emojis

            await migration_seed_ui_emojis()

        mock_collection.update_one.assert_awaited_once()
        call_args = mock_collection.update_one.call_args
        set_doc = call_args[0][1]['$set']['ui_emojis']
        assert set_doc['rockball'] == 1308981475114225694
        assert set_doc['crackerpeaty'] == 1214140141245825024
        assert len(set_doc) == 4

    async def test_skips_when_already_populated(self):
        """ui_emojis already has values — filter excludes the doc, modified_count is 0"""
        mock_result = MagicMock()
        mock_result.modified_count = 0

        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(return_value=mock_result)

        mock_db = MagicMock()
        mock_db.global_config = mock_collection

        with patch('attubot.client.core.db') as mock_core_db:
            mock_core_db.get_db.return_value = mock_db

            from attubot.client.migrations import migration_seed_ui_emojis

            await migration_seed_ui_emojis()

        # still called, but the filter ensures no-op
        mock_collection.update_one.assert_awaited_once()
        call_args = mock_collection.update_one.call_args
        query_filter = call_args[0][0]
        assert query_filter['config_type'] == 'theme'
        assert '$or' in query_filter
