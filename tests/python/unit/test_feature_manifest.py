# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_feature_manifest | type-checked fixture for FeatureManifest.

instantiates a full ccboard-shaped manifest (from notes/nova-core.md) with mock classes
to validate field types before nova-w3 declares real manifests.
"""

import pytest
from discord import Bot
from pydantic import BaseModel

from nova_core.manifest import FeatureManifest
from nova_core.tasks.base import BaseTask


pytestmark = pytest.mark.unit


# --- mock classes ---


class _ManagerTask(BaseTask):
    """synthetic ccboard manager task"""

    name = 'ccboard.manager'
    interval = None
    run_once = False

    async def run(self) -> None:
        pass


class _AuditorTask(BaseTask):
    """synthetic ccboard auditor task"""

    name = 'ccboard.auditor'
    interval = None
    run_once = False

    async def run(self) -> None:
        pass


class _GuildCCBoard(BaseModel):
    """minimal ccboard guild config model"""

    enabled: bool = False
    channel_id: int = 0


class _ReactionDocument:
    pass


class _BoardEntryDocument:
    pass


class _ReactionRepository:
    pass


class _EntryRepository:
    pass


async def _handle_reaction_add(payload) -> None:
    pass


async def _handle_reaction_remove(payload) -> None:
    pass


async def _handle_reaction_clear(payload) -> None:
    pass


async def _handle_reaction_clear_emoji(payload) -> None:
    pass


def _setup(bot: Bot) -> None:
    pass


_migration_sentinel = object()


# --- fixture manifest ---


_ccboard_manifest = FeatureManifest(
    name='ccboard',
    tasks=[_ManagerTask(), _AuditorTask()],
    event_handlers={
        'on_raw_reaction_add': _handle_reaction_add,
        'on_raw_reaction_remove': _handle_reaction_remove,
        'on_raw_reaction_clear': _handle_reaction_clear,
        'on_raw_reaction_clear_emoji': _handle_reaction_clear_emoji,
    },
    setup=_setup,
    guild_config_key='ccboard',
    guild_config_model=_GuildCCBoard,
    document_classes=[_ReactionDocument, _BoardEntryDocument],
    repository_classes=[_ReactionRepository, _EntryRepository],
    migrations=[_migration_sentinel],
)


# --- tests ---


class TestCCBoardManifestFixture:
    def test_name_field(self):
        assert _ccboard_manifest.name == 'ccboard'

    def test_tasks_count(self):
        assert len(_ccboard_manifest.tasks) == 2

    def test_tasks_are_base_task_instances(self):
        assert all(isinstance(t, BaseTask) for t in _ccboard_manifest.tasks)

    def test_event_handlers_count(self):
        assert len(_ccboard_manifest.event_handlers) == 4

    def test_event_handler_keys(self):
        assert set(_ccboard_manifest.event_handlers.keys()) == {
            'on_raw_reaction_add',
            'on_raw_reaction_remove',
            'on_raw_reaction_clear',
            'on_raw_reaction_clear_emoji',
        }

    def test_setup_callable(self):
        assert callable(_ccboard_manifest.setup)

    def test_guild_config_key(self):
        assert _ccboard_manifest.guild_config_key == 'ccboard'

    def test_guild_config_model_is_base_model_subclass(self):
        assert _ccboard_manifest.guild_config_model is _GuildCCBoard
        assert issubclass(_ccboard_manifest.guild_config_model, BaseModel)

    def test_document_classes(self):
        assert _ccboard_manifest.document_classes == [_ReactionDocument, _BoardEntryDocument]

    def test_repository_classes(self):
        assert _ccboard_manifest.repository_classes == [_ReactionRepository, _EntryRepository]

    def test_migrations(self):
        assert _ccboard_manifest.migrations == [_migration_sentinel]

    def test_default_fields_round_trip(self):
        """verify a minimal manifest still has correct defaults"""
        minimal = FeatureManifest(name='minimal')
        assert minimal.tasks == []
        assert minimal.event_handlers == {}
        assert minimal.setup is None
        assert minimal.guild_config_key is None
        assert minimal.guild_config_model is None
        assert minimal.document_classes == []
        assert minimal.repository_classes == []
        assert minimal.migrations == []
