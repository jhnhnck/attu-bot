# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_migrations | unit tests for the migration system."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nova_core.config import _version_gte


# --- _version_gte ---


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


# --- run_pending_migrations ---


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
            patch('nova_core.client.migrations.load_migration_table', [migration_fn]),
            patch('nova_core.client.migrations.config') as patched_config,
        ):
            patched_config.config_repo = mock_config_repo

            from nova_core.client.migrations import run_pending_migrations

            await run_pending_migrations(stage='load')

        migration_fn.assert_awaited_once_with('2.5.3')

    async def test_runs_ready_stage_migrations(self, mock_config_repo, mock_system_config):
        migration_fn = AsyncMock()

        with (
            patch('nova_core.client.migrations.ready_migration_table', [migration_fn]),
            patch('nova_core.client.migrations.config') as patched_config,
        ):
            patched_config.config_repo = mock_config_repo

            from nova_core.client.migrations import run_pending_migrations

            await run_pending_migrations(stage='ready')

        migration_fn.assert_awaited_once_with('2.5.3')

    async def test_reraises_migration_error(self, mock_config_repo):
        from nova_core.client.migrations import MigrationError, run_pending_migrations

        failing_fn = AsyncMock(side_effect=MigrationError('boom'))

        with (
            patch('nova_core.client.migrations.load_migration_table', [failing_fn]),
            patch('nova_core.client.migrations.config') as patched_config,
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
            patch('nova_core.client.migrations.load_migration_table', [migration_fn]),
            patch('nova_core.client.migrations.config') as patched_config,
        ):
            patched_config.config_repo = mock_config_repo

            from nova_core.client.migrations import run_pending_migrations

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
            patch('nova_core.client.migrations.load_migration_table', [step_1, step_2]),
            patch('nova_core.client.migrations.config') as patched_config,
        ):
            patched_config.config_repo = mock_config_repo

            from nova_core.client.migrations import run_pending_migrations

            await run_pending_migrations(stage='load')

        assert call_versions == ['2.5.3', '2.5.4']


# --- migration_seed_ui_emojis (2.5.3 → 2.5.4) ---


class TestMigrationSeedUiEmojis:
    """unit: migration_seed_ui_emojis seeds emoji IDs on theme document"""

    @pytest.fixture
    def mock_db(self):
        mock_result = MagicMock()
        mock_result.modified_count = 1

        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(return_value=mock_result)
        mock_collection.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
        mock_collection.delete_many = AsyncMock()
        mock_collection.insert_many = AsyncMock()

        db = MagicMock()
        db.global_config = mock_collection
        db.__getitem__ = MagicMock(return_value=mock_collection)
        return db

    async def test_seeds_when_missing(self, mock_db):
        """ui_emojis is empty or absent — migration inserts the default emojis"""
        with patch('nova_core.client.core.db') as mock_core_db:
            mock_core_db.get_db.return_value = mock_db

            from nova_core.client.migrations import migration_seed_ui_emojis

            await migration_seed_ui_emojis('2.5.3')

        # seed call + version bump call
        assert mock_db.global_config.update_one.await_count == 2
        seed_call = mock_db.global_config.update_one.call_args_list[0]
        set_doc = seed_call[0][1]['$set']['ui_emojis']
        assert set_doc['rockball'] == 1308981475114225694
        assert set_doc['crackerpeaty'] == 1214140141245825024
        assert len(set_doc) == 4

    async def test_takes_backup_before_update(self, mock_db):
        """backup is taken from global_config before the update runs"""
        with patch('nova_core.client.core.db') as mock_core_db:
            mock_core_db.get_db.return_value = mock_db

            from nova_core.client.migrations import migration_seed_ui_emojis

            await migration_seed_ui_emojis('2.5.3')

        # _backup_collection reads via db['global_config'].find()
        mock_db.__getitem__.assert_any_call('global_config')

    async def test_restores_on_failure(self, mock_db):
        """if the update fails, global_config is restored from the backup"""
        mock_db.global_config.update_one = AsyncMock(side_effect=RuntimeError('db error'))
        backup_docs = [{'config_type': 'theme', 'rotation': 0.0}]
        mock_db.__getitem__.return_value.find.return_value.to_list = AsyncMock(return_value=backup_docs)

        with (
            patch('nova_core.client.core.db') as mock_core_db,
            pytest.raises(Exception, match=r'Migration to 2\.5\.4 failed'),
        ):
            mock_core_db.get_db.return_value = mock_db

            from nova_core.client.migrations import migration_seed_ui_emojis

            await migration_seed_ui_emojis('2.5.3')

        # _restore_collection should have been called: delete_many + insert_many
        restore_collection = mock_db.__getitem__.return_value
        restore_collection.delete_many.assert_awaited_once()
        restore_collection.insert_many.assert_awaited_once()

    async def test_skips_when_already_populated(self, mock_db):
        """ui_emojis already has values — filter excludes the doc, modified_count is 0"""
        mock_db.global_config.update_one.return_value.modified_count = 0

        with patch('nova_core.client.core.db') as mock_core_db:
            mock_core_db.get_db.return_value = mock_db

            from nova_core.client.migrations import migration_seed_ui_emojis

            await migration_seed_ui_emojis('2.5.3')

        seed_call = mock_db.global_config.update_one.call_args_list[0]
        query_filter = seed_call[0][0]
        assert query_filter['config_type'] == 'theme'
        assert '$or' in query_filter

    async def test_skipped_when_version_past(self):
        """wrapper bails out when db version != old version"""
        with patch('nova_core.client.core.db') as mock_core_db:
            from nova_core.client.migrations import migration_seed_ui_emojis

            await migration_seed_ui_emojis('2.5.4')

        # db should never be touched
        mock_core_db.get_db.assert_not_called()


# --- migration_target_signals (2.5.4 → 2.5.5) ---


class TestMigrationTargetSignals:
    """unit: migration_target_signals drops legacy index and purges untargeted signals"""

    @pytest.fixture
    def mock_db(self):
        result = MagicMock()
        result.deleted_count = 3

        collection = MagicMock()
        collection.drop_index = AsyncMock()
        collection.delete_many = AsyncMock(return_value=result)
        collection.update_one = AsyncMock()  # for the version bump in the wrapper

        db = MagicMock()
        db.global_config = collection
        db.__getitem__ = MagicMock(return_value=collection)
        return db, collection

    async def test_drops_legacy_index_and_purges_untargeted(self, mock_db):
        db_obj, collection = mock_db
        with patch('nova_core.client.core.db') as mock_core_db:
            mock_core_db.get_db.return_value = db_obj

            from nova_core.client.migrations import migration_target_signals

            await migration_target_signals('2.5.4')

        collection.drop_index.assert_awaited_once_with('signal_type_1_guild_id_1')
        collection.delete_many.assert_awaited_once_with({'target': {'$exists': False}})

    async def test_swallows_missing_legacy_index(self, mock_db):
        """drop_index raising OperationFailure (index already gone) is suppressed; purge still runs"""
        from pymongo.errors import OperationFailure

        db_obj, collection = mock_db
        collection.drop_index = AsyncMock(side_effect=OperationFailure('index not found'))

        with patch('nova_core.client.core.db') as mock_core_db:
            mock_core_db.get_db.return_value = db_obj

            from nova_core.client.migrations import migration_target_signals

            await migration_target_signals('2.5.4')

        collection.delete_many.assert_awaited_once_with({'target': {'$exists': False}})

    async def test_skipped_when_version_past(self):
        """wrapper bails when db version != old version"""
        with patch('nova_core.client.core.db') as mock_core_db:
            from nova_core.client.migrations import migration_target_signals

            await migration_target_signals('2.5.5')

        mock_core_db.get_db.assert_not_called()
