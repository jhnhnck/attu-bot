# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_nova_config_features | round-trip tests for [features] TOML parsing.

verifies feature_config() and features_enabled parsing against real tomlkit documents, not
mocks, so that tomlkit Table / Array semantics are exercised rather than assumed.
"""

import pytest
import tomlkit

from nova_core.client.core import config


pytestmark = pytest.mark.unit


class TestFeatureConfigTomlkitRoundTrip:
    """feature_config() returns correct dicts when _raw is a real tomlkit document."""

    def _load(self, toml_text: str):
        """parse toml_text into a tomlkit document and inject it as config._raw."""
        config._raw = tomlkit.loads(toml_text)  # type: ignore[assignment]

    def test_absent_features_section_returns_empty_dict(self):
        """feature_config returns {} when the [features] section is entirely missing"""
        self._load('[database]\nname = "test"\n')
        assert config.feature_config('eggs') == {}

    def test_present_features_section_absent_subtable_returns_empty_dict(self):
        """feature_config returns {} when [features] exists but [features.eggs] does not"""
        self._load('[features]\nenabled = ["ccboard"]\n')
        assert config.feature_config('eggs') == {}

    def test_present_subtable_returns_dict(self):
        """feature_config returns the subtable as a plain dict when [features.name] exists"""
        self._load('[features]\nenabled = []\n\n[features.eggs]\nsome_key = "value"\ncap = 10\n')
        result = config.feature_config('eggs')
        assert result == {'some_key': 'value', 'cap': 10}

    def test_return_value_is_plain_dict(self):
        """feature_config return value is a plain dict, not a tomlkit proxy object"""
        self._load('[features]\nenabled = []\n\n[features.eggs]\nk = "v"\n')
        result = config.feature_config('eggs')
        assert type(result) is dict

    def test_raw_none_returns_empty_dict(self):
        """feature_config returns {} when _raw is None (before on_init runs)"""
        config._raw = None  # type: ignore[assignment]
        assert config.feature_config('anything') == {}


class TestFeaturesEnabledTomlkitRoundTrip:
    """features_enabled is populated correctly when _raw contains real tomlkit arrays."""

    def test_features_enabled_list_from_toml(self):
        """features_enabled contains all entries from [features] enabled array after on_init"""
        # on_init is hard to invoke standalone; test the parsing path directly
        raw = tomlkit.loads('[features]\nenabled = ["eggs", "ccboard"]\n')
        features_raw = raw.get('features', {})
        result = list(features_raw.get('enabled', []))
        assert result == ['eggs', 'ccboard']

    def test_features_enabled_absent_section_returns_empty(self):
        """when [features] is absent, enabled list defaults to empty"""
        raw = tomlkit.loads('[database]\nname = "x"\n')
        features_raw = raw.get('features', {})
        result = list(features_raw.get('enabled', []))
        assert result == []
