# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_ccboard_builder | unit tests for the ccboard rule pipeline."""

import pytest

from attu_models import BoardEntryDocument, MessageAuthor, MessageContent, MessageDocument, MessageRefs
from doom_bot.ccboard.builder import build_embeds
from doom_bot.config import GuildCCBoard


# --- Constants ---

guild_id = 1234567890
channel_id = 5555555555
message_id = 111000111000111000
reply_message_id = 222000222000222000
author_id = 573360359566737409
reply_author_id = 600000000000000000

jump_url = f'https://discord.com/channels/{guild_id}/{channel_id}/{message_id}'
reply_jump_url = f'https://discord.com/channels/{guild_id}/{channel_id}/{reply_message_id}'

positive_color_hex = '#EEDD20'
negative_color_hex = '#DD2020'
reply_color_int = 0x2B2D31


# --- Fixtures ---


@pytest.fixture(autouse=True)
def _stub_bot(monkeypatch):
    """stub doom_bot.client.core.bot so rule_base / rule_reply_context don't hit a live bot.

    the builder calls bot.get_user(...) for avatar resolution; under unit tests the bot
    singleton may be a real bot that hasn't connected. returning None makes the avatar
    fall back to None deterministically.
    """

    class _StubBot:
        def get_user(self, _user_id):
            return None

    import doom_bot.client.core as core_module

    monkeypatch.setattr(core_module, 'bot', _StubBot(), raising=False)


def make_msg(
    *,
    msg_id: int = message_id,
    chan_id: int = channel_id,
    g_id: int = guild_id,
    auth_id: int = author_id,
    auth_name: str = 'TestUser',
    auth_bot: bool = False,
    text: str = '',
    attachments: list[dict] | None = None,
    embeds: list[dict] | None = None,
    sticker_urls: list[str] | None = None,
    forwarded: bool = False,
    reply_to: int | None = None,
    poll_text: str | None = None,
    created_at: int = 1704067200,
) -> MessageDocument:
    return MessageDocument(
        message_id=msg_id,
        guild_id=g_id,
        channel_id=chan_id,
        author=MessageAuthor(id=auth_id, name=auth_name, bot=auth_bot),
        content=MessageContent(
            text=text,
            attachments=attachments or [],
            embeds=embeds or [],
            sticker_urls=sticker_urls or [],
            poll_text=poll_text,
            forwarded=forwarded,
        ),
        refs=MessageRefs(reply_to=reply_to),
        created_at=created_at,
    )


def make_entry(
    *,
    snapshot: MessageDocument | None = None,
    reply_snapshot: MessageDocument | None = None,
    net_points: int = 1,
    positive_points: int = 1,
) -> BoardEntryDocument:
    snap = snapshot or make_msg()
    return BoardEntryDocument(
        message_id=snap.message_id,
        channel_id=snap.channel_id,
        guild_id=snap.guild_id,
        author_id=snap.author.id,
        net_points=net_points,
        positive_points=positive_points,
        snapshot=snap,
        reply_snapshot=reply_snapshot,
    )


def make_config(**overrides) -> GuildCCBoard:
    defaults = {
        'enabled': True,
        'channel_id': 0,
        'emojis': {'⭐': 1},
        'super_bonus': 1,
        'threshold': 2,
        'points_label': 'stars',
        'positive_color': positive_color_hex,
        'negative_color': negative_color_hex,
    }
    defaults.update(overrides)
    return GuildCCBoard(**defaults)


# --- Tests ---


def test_text_only_message_uses_positive_color():
    snap = make_msg(text='hello world')
    entry = make_entry(snapshot=snap, net_points=4, positive_points=4)
    embeds = build_embeds(entry, make_config())
    assert len(embeds) == 1
    main = embeds[0]
    assert main.description == 'hello world'
    assert main.color is not None
    assert main.color.value == 0xEEDD20
    assert main.author.name == 'TestUser'
    assert main.author.url == jump_url


def test_zero_net_points_uses_negative_color():
    # spec: positive_color when net > 0, negative_color when net <= 0 (so 0 is negative)
    snap = make_msg(text='controversial')
    entry = make_entry(snapshot=snap, net_points=0, positive_points=2)
    embeds = build_embeds(entry, make_config())
    assert embeds[0].color is not None
    assert embeds[0].color.value == 0xDD2020


def test_negative_net_points_uses_negative_color():
    snap = make_msg(text='downvoted')
    entry = make_entry(snapshot=snap, net_points=-3, positive_points=0)
    embeds = build_embeds(entry, make_config())
    assert embeds[0].color is not None
    assert embeds[0].color.value == 0xDD2020


def test_single_image_attachment_sets_main_image_and_url():
    attachments = [{'filename': 'a.png', 'url': 'https://cdn.example/a.png', 'content_type': 'image/png', 'size': 100}]
    snap = make_msg(text='look', attachments=attachments)
    entry = make_entry(snapshot=snap)
    embeds = build_embeds(entry, make_config())
    assert len(embeds) == 1
    main = embeds[0]
    assert main.image.url == 'https://cdn.example/a.png'
    # multi-image gallery url-share fix: even single-image posts set url so a future
    # extra embed (e.g. from rule_link_previews) joins the same gallery
    assert main.url == jump_url


def test_multi_image_gallery_shares_jump_url_across_all_embeds():
    """regression test for the legacy starboard's broken multi-image rendering.

    discord groups embeds into a single connected gallery only when every embed
    shares the same `url`. the legacy starboard set image but not url on the
    main embed, so each extra image rendered as a disconnected block.
    """
    attachments = [
        {'filename': 'a.png', 'url': 'https://cdn.example/a.png', 'content_type': 'image/png', 'size': 100},
        {'filename': 'b.png', 'url': 'https://cdn.example/b.png', 'content_type': 'image/png', 'size': 100},
        {'filename': 'c.png', 'url': 'https://cdn.example/c.png', 'content_type': 'image/png', 'size': 100},
    ]
    snap = make_msg(text='gallery', attachments=attachments)
    entry = make_entry(snapshot=snap)
    embeds = build_embeds(entry, make_config())
    assert len(embeds) == 3
    # every embed in the gallery shares the same url so discord groups them visually
    assert all(e.url == jump_url for e in embeds), [e.url for e in embeds]
    # images should map in order: main, extra1, extra2
    image_urls = [e.image.url for e in embeds]
    assert image_urls == [
        'https://cdn.example/a.png',
        'https://cdn.example/b.png',
        'https://cdn.example/c.png',
    ]


def test_image_url_detected_by_extension_when_content_type_missing():
    # files uploaded without a content_type still fall through _is_image via the extension
    attachments = [{'filename': 'mystery.gif', 'url': 'https://cdn.example/mystery.gif', 'content_type': '', 'size': 100}]
    snap = make_msg(attachments=attachments)
    entry = make_entry(snapshot=snap)
    embeds = build_embeds(entry, make_config())
    assert embeds[0].image.url == 'https://cdn.example/mystery.gif'


def test_reply_context_prepends_reply_embed():
    reply_snap = make_msg(
        msg_id=reply_message_id,
        auth_id=reply_author_id,
        auth_name='OriginalAuthor',
        text='the original message',
    )
    snap = make_msg(text='replying!', reply_to=reply_message_id)
    entry = make_entry(snapshot=snap, reply_snapshot=reply_snap)
    embeds = build_embeds(entry, make_config())
    assert len(embeds) == 2
    # reply embed comes first
    reply_embed = embeds[0]
    assert reply_embed.color is not None
    assert reply_embed.color.value == reply_color_int
    assert reply_embed.author.name == 'replying to OriginalAuthor'
    assert reply_embed.author.url == reply_jump_url
    assert reply_embed.description == 'the original message'
    # main embed follows
    assert embeds[1].description == 'replying!'


def test_reply_context_with_image_attachment():
    reply_snap = make_msg(
        msg_id=reply_message_id,
        auth_name='ImagePoster',
        attachments=[{'filename': 'reply.png', 'url': 'https://cdn.example/reply.png', 'content_type': 'image/png', 'size': 100}],
    )
    snap = make_msg(text='cool pic', reply_to=reply_message_id)
    entry = make_entry(snapshot=snap, reply_snapshot=reply_snap)
    embeds = build_embeds(entry, make_config())
    assert embeds[0].image.url == 'https://cdn.example/reply.png'


def test_sticker_only_message():
    snap = make_msg(text='', sticker_urls=['https://cdn.example/sticker.png'])
    entry = make_entry(snapshot=snap)
    embeds = build_embeds(entry, make_config())
    assert len(embeds) == 1
    assert embeds[0].image.url == 'https://cdn.example/sticker.png'
    assert embeds[0].description == '*sticker*'


def test_sticker_with_text_keeps_text():
    snap = make_msg(text='check this sticker', sticker_urls=['https://cdn.example/sticker.png'])
    entry = make_entry(snapshot=snap)
    embeds = build_embeds(entry, make_config())
    assert embeds[0].description == 'check this sticker'
    assert embeds[0].image.url == 'https://cdn.example/sticker.png'


def test_voice_memo_no_preview_notice():
    attachments = [{'filename': 'voice-message.ogg', 'url': 'https://cdn.example/voice.ogg', 'content_type': 'audio/ogg', 'size': 5000}]
    snap = make_msg(text='', attachments=attachments)
    entry = make_entry(snapshot=snap)
    embeds = build_embeds(entry, make_config())
    assert len(embeds) == 1
    assert embeds[0].description == 'voice memo - playback unavailable'
    # voice memo has no usable preview image - py-cord returns None for unset .image
    assert getattr(embeds[0].image, 'url', None) is None


def test_forwarded_sets_footer():
    snap = make_msg(text='this was forwarded', forwarded=True)
    entry = make_entry(snapshot=snap)
    embeds = build_embeds(entry, make_config())
    assert embeds[0].footer.text == 'forwarded message'


def test_not_forwarded_no_footer():
    snap = make_msg(text='regular message', forwarded=False)
    entry = make_entry(snapshot=snap)
    embeds = build_embeds(entry, make_config())
    # py-cord returns None for an unset .footer; pin via to_dict() so the assertion
    # holds across both proxy and None representations
    assert 'footer' not in embeds[0].to_dict()


def test_link_preview_simple_merges_into_main():
    # a description-only stored embed merges into the main embed when text is empty
    snap = make_msg(text='', embeds=[{'description': 'preview text from a link'}])
    entry = make_entry(snapshot=snap)
    embeds = build_embeds(entry, make_config())
    assert len(embeds) == 1
    assert embeds[0].description == 'preview text from a link'


def test_link_preview_rich_becomes_extra_embed():
    rich = {
        'title': 'Article Title',
        'description': 'a longer summary',
        'url': 'https://example.com/article',
        'author_name': 'Some Author',
        'fields': [{'name': 'Topic', 'value': 'discord bots', 'inline': True}],
    }
    snap = make_msg(text='check this article', embeds=[rich])
    entry = make_entry(snapshot=snap)
    embeds = build_embeds(entry, make_config())
    # main + extra (rich preview pushed to its own embed)
    assert len(embeds) == 2
    extra = embeds[1]
    assert extra.title == 'Article Title'
    assert extra.description == 'a longer summary'
    assert extra.author.name == 'Some Author'
    assert len(extra.fields) == 1


def test_gif_embed_uses_actual_gif_url_not_png_proxy():
    # tenor link previews come back with a video_url for the actual gif and an
    # image_url that points to discord's png preview proxy. we want the gif.
    stored = {
        'url': 'https://tenor.com/view/dancing-cat-gif-12345',
        'image_url': 'https://media.discordapp.net/external/abc/preview.png',
        'video_url': 'https://media.tenor.com/abc/dancing-cat.gif',
    }
    snap = make_msg(text='', embeds=[stored])
    entry = make_entry(snapshot=snap)
    embeds = build_embeds(entry, make_config())
    main = embeds[0]
    assert main.image.url == 'https://media.tenor.com/abc/dancing-cat.gif'
    # gif gets the gallery-share url too so it composes with any future extra embeds
    assert main.url == jump_url
