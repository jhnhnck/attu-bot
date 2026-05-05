"""
AttuBot - Web Forms Validation Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests for Pydantic form validation models in attubot/web/forms.py
"""

import pytest
from pydantic import ValidationError

from attubot.web.forms import (
    ChatChannelConfigForm,
    ChatConfigForm,
    GuildChannelsForm,
    GuildConfigForm,
    GuildEpochForm,
    GuildRolesForm,
    GuildStarboardForm,
    GuildUsersForm,
    SystemConfigForm,
    ThemeConfigForm,
)


# ========== GuildChannelsForm Tests ==========


class TestGuildChannelsForm:
    def test_valid_channels(self):
        """Test valid channel configuration"""
        form = GuildChannelsForm(
            activity=123456,
            announcements=789012,
            year_vc=345678,
            year_links=901234,
            meta_chat=567890,
            lore_channels=[111, 222, 333],
            canon_channels=[444, 555],
        )
        assert form.activity == 123456
        assert form.announcements == 789012
        assert len(form.lore_channels) == 3
        assert len(form.canon_channels) == 2

    def test_default_values(self):
        """Test default channel values"""
        form = GuildChannelsForm()
        assert form.activity == 0
        assert form.announcements == 0
        assert form.lore_channels == []
        assert form.canon_channels == []

    def test_parse_comma_separated_channels(self):
        """Test parsing comma-separated channel IDs"""
        form = GuildChannelsForm(
            lore_channels='111, 222, 333',  # type: ignore[arg-type]
            canon_channels='444,555,666',  # type: ignore[arg-type]
        )
        assert form.lore_channels == [111, 222, 333]
        assert form.canon_channels == [444, 555, 666]

    def test_parse_empty_channel_list(self):
        """Test parsing empty channel list string"""
        form = GuildChannelsForm(
            lore_channels='',  # type: ignore[arg-type]
            canon_channels='   ',  # type: ignore[arg-type]
        )
        assert form.lore_channels == []
        assert form.canon_channels == []

    def test_negative_channel_id_rejected(self):
        """Test that negative channel IDs are rejected"""
        with pytest.raises(ValidationError) as exc_info:
            GuildChannelsForm(activity=-1)
        errors = exc_info.value.errors()
        assert any(e['loc'] == ('activity',) for e in errors)


# ========== GuildEpochForm Tests ==========


class TestGuildEpochForm:
    def test_valid_epoch(self):
        """Test valid epoch configuration"""
        form = GuildEpochForm(
            time=1704067200,
            year=5,
            length=14,
            paused=False,
            rollover_minutes=1020,
        )
        assert form.time == 1704067200
        assert form.year == 5
        assert form.length == 14
        assert form.paused is False
        assert form.rollover_minutes == 1020

    def test_default_values(self):
        """Test default epoch values"""
        form = GuildEpochForm()
        assert form.time == 0
        assert form.year == 1
        assert form.length == 14
        assert form.paused is True
        assert form.rollover_minutes == 1020

    def test_parse_rollover_time_hhmm(self):
        """Test parsing HH:MM format to rollover minutes"""
        form = GuildEpochForm(rollover_minutes='17:00')  # type: ignore[arg-type]
        assert form.rollover_minutes == 1020

        form = GuildEpochForm(rollover_minutes='00:00')  # type: ignore[arg-type]
        assert form.rollover_minutes == 0

        form = GuildEpochForm(rollover_minutes='23:59')  # type: ignore[arg-type]
        assert form.rollover_minutes == 1439

    def test_rollover_minutes_as_integer(self):
        """Test rollover minutes as direct integer"""
        form = GuildEpochForm(rollover_minutes=720)
        assert form.rollover_minutes == 720

    def test_invalid_rollover_time_format(self):
        """Test invalid rollover time format"""
        with pytest.raises(ValidationError):
            GuildEpochForm(rollover_minutes='25:00')  # type: ignore[arg-type]

        with pytest.raises(ValidationError):
            GuildEpochForm(rollover_minutes='invalid')  # type: ignore[arg-type]

    def test_rollover_minutes_bounds(self):
        """Test rollover minutes must be within valid range"""
        with pytest.raises(ValidationError):
            GuildEpochForm(rollover_minutes=-1)

        with pytest.raises(ValidationError):
            GuildEpochForm(rollover_minutes=1440)

    def test_year_must_be_positive(self):
        """Test year must be at least 1"""
        with pytest.raises(ValidationError):
            GuildEpochForm(year=0)

        with pytest.raises(ValidationError):
            GuildEpochForm(year=-1)

    def test_length_bounds(self):
        """Test year length must be between 1 and 365"""
        with pytest.raises(ValidationError):
            GuildEpochForm(length=0)

        with pytest.raises(ValidationError):
            GuildEpochForm(length=366)

        # Valid bounds
        form = GuildEpochForm(length=1)
        assert form.length == 1

        form = GuildEpochForm(length=365)
        assert form.length == 365


# ========== GuildRolesForm Tests ==========


class TestGuildRolesForm:
    def test_valid_roles(self):
        """all four role fields accept positive snowflake IDs."""
        form = GuildRolesForm(
            announcements=123456789,
            bot_color=234567890,
            trees_admin_role=345678901,
            trees_user_role=456789012,
        )
        assert form.announcements == 123456789
        assert form.bot_color == 234567890
        assert form.trees_admin_role == 345678901
        assert form.trees_user_role == 456789012

    def test_default_values(self):
        """unset role IDs default to 0 so the page renders Not Set."""
        form = GuildRolesForm()
        assert form.announcements == 0
        assert form.bot_color == 0
        assert form.trees_admin_role == 0
        assert form.trees_user_role == 0

    @pytest.mark.parametrize('field', ['announcements', 'bot_color', 'trees_admin_role', 'trees_user_role'])
    def test_negative_role_id_rejected(self, field):
        """negative IDs are rejected on every role field."""
        with pytest.raises(ValidationError):
            GuildRolesForm(**{field: -1})


# ========== GuildUsersForm Tests ==========


class TestGuildUsersForm:
    def test_valid_users(self):
        """Test valid users configuration"""
        form = GuildUsersForm(markers=[111, 222, 333])
        assert form.markers == [111, 222, 333]

    def test_default_values(self):
        """Test default user values"""
        form = GuildUsersForm()
        assert form.markers == []

    def test_parse_comma_separated_users(self):
        """Test parsing comma-separated user IDs"""
        form = GuildUsersForm(markers='111, 222, 333')  # type: ignore[arg-type]
        assert form.markers == [111, 222, 333]

    def test_parse_empty_user_list(self):
        """Test parsing empty user list string"""
        form = GuildUsersForm(markers='')  # type: ignore[arg-type]
        assert form.markers == []


# ========== GuildStarboardForm Tests ==========


class TestGuildStarboardForm:
    def test_valid_unicode_emoji(self):
        """test a valid unicode emoji with a hex color"""
        form = GuildStarboardForm(emojis={'⭐': '#EEDD20'})
        assert form.emojis == {'⭐': '#EEDD20'}

    def test_valid_custom_emoji(self):
        """test a custom discord emoji string - the format that was silently wiped before"""
        form = GuildStarboardForm(emojis={'<:rockball:1308981475114225694>': '#FF0000'})
        assert form.emojis == {'<:rockball:1308981475114225694>': '#FF0000'}

    def test_valid_multiple_emojis(self):
        """test multiple emojis including a custom one"""
        emojis = {'⭐': '#EEDD20', '<:rockball:1308981475114225694>': '#FF0000'}
        form = GuildStarboardForm(emojis=emojis)
        assert form.emojis == emojis

    def test_emojis_as_json_string(self):
        """test that a valid JSON string is parsed correctly (frontend serialization path)"""
        import json

        payload = json.dumps({'⭐': '#EEDD20'})
        form = GuildStarboardForm(emojis=payload)  # type: ignore[arg-type]
        assert form.emojis == {'⭐': '#EEDD20'}

    def test_custom_emoji_as_json_string(self):
        """test that a custom emoji key in a JSON string is preserved after parsing"""
        import json

        payload = json.dumps({'<:rockball:1308981475114225694>': '#FF0000'})
        form = GuildStarboardForm(emojis=payload)  # type: ignore[arg-type]
        assert form.emojis == {'<:rockball:1308981475114225694>': '#FF0000'}

    def test_empty_string_returns_empty_dict(self):
        """an empty emojis string should produce an empty dict, not raise"""
        form = GuildStarboardForm(emojis='')  # type: ignore[arg-type]
        assert form.emojis == {}

    def test_invalid_json_string_raises_validation_error(self):
        """invalid JSON must raise ValidationError, not silently return {} (the old bug)"""
        with pytest.raises(ValidationError) as exc_info:
            GuildStarboardForm(emojis='not valid json{{{')  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        assert any('emojis' in str(e['loc']) for e in errors)

    def test_non_dict_value_raises_validation_error(self):
        """non-dict value must raise ValidationError, not silently return {}"""
        with pytest.raises(ValidationError) as exc_info:
            GuildStarboardForm(emojis=['⭐', '#EEDD20'])  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        assert any('emojis' in str(e['loc']) for e in errors)

    def test_invalid_color_raises_validation_error(self):
        """an invalid hex color must raise"""
        with pytest.raises(ValidationError):
            GuildStarboardForm(emojis={'⭐': 'not-a-color'})

        with pytest.raises(ValidationError):
            GuildStarboardForm(emojis={'⭐': '#ZZZ'})

    def test_default_values(self):
        """test default starboard form values"""
        form = GuildStarboardForm()
        assert form.channel_id == 0
        assert form.emojis == {}
        assert form.valid_bots == []

    def test_valid_bots_as_list(self):
        """test valid_bots as a list of ints"""
        form = GuildStarboardForm(valid_bots=[111, 222])
        assert form.valid_bots == [111, 222]

    def test_valid_bots_as_comma_string(self):
        """test valid_bots parsed from comma-separated string"""
        form = GuildStarboardForm(valid_bots='111, 222')  # type: ignore[arg-type]
        assert form.valid_bots == [111, 222]


# ========== GuildConfigForm Tests ==========


class TestGuildConfigForm:
    def test_valid_nested_config(self):
        """Test valid nested guild configuration"""
        form = GuildConfigForm(
            channels={'activity': 123456, 'lore_channels': [111, 222]},  # type: ignore[arg-type]
            epoch={'time': 1704067200, 'year': 5, 'rollover_minutes': '17:00'},  # type: ignore[arg-type]
            roles={'announcements': 789012},  # type: ignore[arg-type]
            users={'markers': [333, 444]},  # type: ignore[arg-type]
        )
        assert form.channels.activity == 123456
        assert form.epoch.year == 5
        assert form.epoch.rollover_minutes == 1020
        assert form.roles.announcements == 789012
        assert form.users.markers == [333, 444]

    def test_flatten_form_data(self):
        """Test flattening of form data from flat keys"""
        form = GuildConfigForm(**{
            'channels.activity': 123456,
            'channels.announcements': 789012,
            'epoch.time': 1704067200,
            'epoch.year': 5,
            'epoch.rollover_minutes': 1020,
            'roles.announcements': 555555,
            'users.markers': '111,222',
        })
        assert form.channels.activity == 123456
        assert form.channels.announcements == 789012
        assert form.epoch.time == 1704067200
        assert form.epoch.year == 5
        assert form.epoch.rollover_minutes == 1020
        assert form.roles.announcements == 555555
        assert form.users.markers == [111, 222]

    def test_default_values(self):
        """Test default values for guild config"""
        form = GuildConfigForm()
        assert form.channels.activity == 0
        assert form.epoch.year == 1
        assert form.roles.announcements == 0
        assert form.users.markers == []

    def test_already_nested_data(self):
        """Test handling already-nested data structure"""
        form = GuildConfigForm(
            channels={'activity': 123456},  # type: ignore[arg-type]
            epoch={'year': 10},  # type: ignore[arg-type]
            roles={'announcements': 999},  # type: ignore[arg-type]
        )
        assert form.channels.activity == 123456
        assert form.epoch.year == 10
        assert form.roles.announcements == 999


# ========== ThemeConfigForm Tests ==========


class TestThemeConfigForm:
    def test_valid_theme(self):
        """Test valid theme configuration"""
        form = ThemeConfigForm(
            rotation=180.0,
            max_rate=0.75,
            bot_color='#ff0000',
            guild_color='#00ff00',
        )
        assert form.rotation == 180.0
        assert form.max_rate == 0.75
        assert form.bot_color == '#ff0000'
        assert form.guild_color == '#00ff00'

    def test_default_values(self):
        """Test default theme values"""
        form = ThemeConfigForm()
        assert form.rotation == 0.0
        assert form.max_rate == 0.5
        assert form.bot_color == '#ff0000'
        assert form.guild_color == '#ffffff'

    def test_max_rate_bounds(self):
        """Test max_rate must be between 0 and 360"""
        with pytest.raises(ValidationError):
            ThemeConfigForm(max_rate=-0.1)

        with pytest.raises(ValidationError):
            ThemeConfigForm(max_rate=360.1)

        # Valid bounds
        form = ThemeConfigForm(max_rate=0.0)
        assert form.max_rate == 0.0

        form = ThemeConfigForm(max_rate=360.0)
        assert form.max_rate == 360.0

    def test_color_hex_validation(self):
        """Test color hex pattern validation"""
        # Valid colors
        form = ThemeConfigForm(bot_color='#abcdef')
        assert form.bot_color == '#abcdef'

        form = ThemeConfigForm(bot_color='#ABCDEF')
        assert form.bot_color == '#ABCDEF'

        form = ThemeConfigForm(bot_color='#123456')
        assert form.bot_color == '#123456'

        # Invalid colors
        with pytest.raises(ValidationError):
            ThemeConfigForm(bot_color='abcdef')  # Missing #

        with pytest.raises(ValidationError):
            ThemeConfigForm(bot_color='#abc')  # Too short

        with pytest.raises(ValidationError):
            ThemeConfigForm(bot_color='#abcdefg')  # Too long

        with pytest.raises(ValidationError):
            ThemeConfigForm(bot_color='#gggggg')  # Invalid hex


# ========== SystemConfigForm Tests ==========


class TestSystemConfigForm:
    def test_valid_system(self):
        """Test valid system configuration"""
        form = SystemConfigForm(
            primary_guild=123456789,
            error_log_guild=987654321,
            error_log_channel=111111111,
            error_hook='https://discord.com/api/webhooks/123/abc',
        )
        assert form.primary_guild == 123456789
        assert form.error_log_guild == 987654321
        assert form.error_log_channel == 111111111
        assert form.error_hook == 'https://discord.com/api/webhooks/123/abc'

    def test_default_values(self):
        """Test default system values (primary_guild is required)"""
        form = SystemConfigForm(primary_guild=123456)
        assert form.primary_guild == 123456
        assert form.error_log_guild == 0
        assert form.error_log_channel == 0
        assert form.error_hook == ''

    def test_empty_webhook_url_allowed(self):
        """Test empty webhook URL is allowed"""
        form = SystemConfigForm(primary_guild=123456, error_hook='')
        assert form.error_hook == ''

    def test_valid_webhook_url(self):
        """Test valid Discord webhook URL"""
        valid_urls = [
            'https://discord.com/api/webhooks/123456/abcdef',
            'https://discord.com/api/webhooks/999/xyz123',
        ]
        for url in valid_urls:
            form = SystemConfigForm(primary_guild=123456, error_hook=url)
            assert form.error_hook == url

    def test_invalid_webhook_url(self):
        """Test invalid webhook URLs are rejected"""
        invalid_urls = [
            'http://discord.com/api/webhooks/123/abc',  # http instead of https
            'https://example.com/webhook',  # Wrong domain
            'discord.com/api/webhooks/123/abc',  # Missing protocol
            'not a url',  # Not a URL at all
        ]
        for url in invalid_urls:
            with pytest.raises(ValidationError):
                SystemConfigForm(primary_guild=123456, error_hook=url)

    def test_parse_error_log_array(self):
        """Test parsing error_log as [guild, channel] array"""
        # Note: error_log is parsed in the model_validator, not as a direct parameter
        data = {
            'primary_guild': 123456,
            'error_log': [987654, 111111],
        }
        form = SystemConfigForm(**data)  # type: ignore[arg-type]
        assert form.error_log_guild == 987654
        assert form.error_log_channel == 111111

    def test_negative_guild_id_rejected(self):
        """Test that negative guild IDs are rejected"""
        with pytest.raises(ValidationError):
            SystemConfigForm(primary_guild=-1)


# ========== ChatChannelConfigForm Tests ==========


class TestChatChannelConfigForm:
    def test_valid_channel_config(self):
        """Test valid channel config with explicit fields"""
        form = ChatChannelConfigForm(
            name='lore-news',
            description='Lore announcements',
            channel_type='roleplay',
            ingest=True,
        )
        assert form.name == 'lore-news'
        assert form.description == 'Lore announcements'
        assert form.channel_type == 'roleplay'
        assert form.ingest is True

    def test_default_values(self):
        """Test default values"""
        form = ChatChannelConfigForm()
        assert form.name == ''
        assert form.description == ''
        assert form.channel_type == 'discussion'
        assert form.ingest is True

    def test_all_valid_channel_types(self):
        """Test all valid channel types are accepted"""
        for channel_type in ('roleplay', 'discussion', 'shitpost', 'forum'):
            form = ChatChannelConfigForm(channel_type=channel_type)
            assert form.channel_type == channel_type

    def test_invalid_channel_type(self):
        """Test invalid channel type raises ValidationError"""
        with pytest.raises(ValidationError):
            ChatChannelConfigForm(channel_type='invalid')


# ========== ChatConfigForm Tests ==========


class TestChatConfigForm:
    def test_default_values(self):
        """Test all 16 fields have correct documented defaults"""
        form = ChatConfigForm()
        assert form.discord_lookback_hours == 6
        assert form.discord_window_minutes == 30
        assert form.noise_filter_min_tokens == 20
        assert form.ignored_user_ids == []
        assert form.ingest_discord is True
        assert form.ingest_wiki is True
        assert form.ingest_documents is True
        assert form.wiki_namespaces == ['0']
        assert form.character_log_channel_id is None
        assert form.chat_channels == {}
        assert form.user_nations == {}
        assert form.retrieval_top_k_wiki == 5
        assert form.retrieval_top_k_discord == 5
        assert form.retrieval_top_k_documents == 3
        assert form.retrieval_top_k_images == 2

    def test_parse_ignored_user_ids_comma_string(self):
        """Test comma-separated string parsed to list of ints"""
        form = ChatConfigForm(ignored_user_ids='111, 222, 333')  # pyright: ignore[reportArgumentType]
        assert form.ignored_user_ids == [111, 222, 333]

    def test_parse_ignored_user_ids_empty_string(self):
        """Test empty string parsed to empty list"""
        form = ChatConfigForm(ignored_user_ids='')  # pyright: ignore[reportArgumentType]
        assert form.ignored_user_ids == []

    def test_parse_ignored_user_ids_list(self):
        """Test list input passes through unchanged"""
        form = ChatConfigForm(ignored_user_ids=[111, 222])
        assert form.ignored_user_ids == [111, 222]

    def test_parse_wiki_namespaces_comma_string(self):
        """Test comma-separated string parsed to list of strings"""
        form = ChatConfigForm(wiki_namespaces='0, 4')  # pyright: ignore[reportArgumentType]
        assert form.wiki_namespaces == ['0', '4']

    def test_character_log_channel_id_zero_becomes_none(self):
        """Test that 0 is coerced to None"""
        form = ChatConfigForm(character_log_channel_id=0)
        assert form.character_log_channel_id is None

    def test_character_log_channel_id_empty_string_becomes_none(self):
        """Test that empty string is coerced to None"""
        form = ChatConfigForm(character_log_channel_id='')  # pyright: ignore[reportArgumentType]
        assert form.character_log_channel_id is None

    def test_character_log_channel_id_set(self):
        """Test that a valid channel ID is stored correctly"""
        form = ChatConfigForm(character_log_channel_id=123456)
        assert form.character_log_channel_id == 123456

    def test_discord_lookback_hours_bounds(self):
        """Test min/max bounds for discord_lookback_hours"""
        assert ChatConfigForm(discord_lookback_hours=1).discord_lookback_hours == 1
        assert ChatConfigForm(discord_lookback_hours=168).discord_lookback_hours == 168
        with pytest.raises(ValidationError):
            ChatConfigForm(discord_lookback_hours=0)
        with pytest.raises(ValidationError):
            ChatConfigForm(discord_lookback_hours=169)

    def test_discord_window_minutes_bounds(self):
        """Test min/max bounds for discord_window_minutes"""
        assert ChatConfigForm(discord_window_minutes=5).discord_window_minutes == 5
        assert ChatConfigForm(discord_window_minutes=720).discord_window_minutes == 720
        with pytest.raises(ValidationError):
            ChatConfigForm(discord_window_minutes=4)
        with pytest.raises(ValidationError):
            ChatConfigForm(discord_window_minutes=721)

    def test_retrieval_top_k_bounds(self):
        """Test min/max bounds for retrieval_top_k_wiki"""
        assert ChatConfigForm(retrieval_top_k_wiki=1).retrieval_top_k_wiki == 1
        assert ChatConfigForm(retrieval_top_k_wiki=20).retrieval_top_k_wiki == 20
        with pytest.raises(ValidationError):
            ChatConfigForm(retrieval_top_k_wiki=0)
        with pytest.raises(ValidationError):
            ChatConfigForm(retrieval_top_k_wiki=21)

    def test_chat_channels_nested_validation(self):
        """Test nested ChatChannelConfigForm is validated correctly"""
        form = ChatConfigForm(
            chat_channels={  # pyright: ignore[reportArgumentType]
                '123456789': {'name': 'lore-news', 'channel_type': 'roleplay', 'ingest': True}
            }
        )
        assert '123456789' in form.chat_channels
        assert form.chat_channels['123456789'].channel_type == 'roleplay'

    def test_chat_channels_invalid_type_propagates(self):
        """Test invalid channel_type in nested dict raises ValidationError"""
        with pytest.raises(ValidationError):
            ChatConfigForm(
                chat_channels={  # pyright: ignore[reportArgumentType]
                    '123456789': {'channel_type': 'invalid'}
                }
            )
