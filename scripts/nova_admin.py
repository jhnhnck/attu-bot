#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""scripts.nova_admin | interactive admin repl for attu_server."""

import argparse
import cmd
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

import httpx


_CONFIG_SECTIONS = ('channels', 'epoch', 'roles', 'users', 'starboard', 'ccboard')


def _parse_message_id(arg: str) -> int | None:
    """parse a raw message id or a discord message link; return None if unrecognizable."""
    arg = arg.strip()
    if 'discord.com/channels/' in arg:
        parts = arg.rstrip('/').split('/')
        try:
            return int(parts[-1])
        except (ValueError, IndexError):
            return None
    try:
        return int(arg)
    except ValueError:
        return None


def _parse_message_link(link: str) -> tuple[int, int, int] | None:
    """parse a discord message link into (guild_id, channel_id, message_id)."""
    link = link.strip()
    if 'discord.com/channels/' not in link:
        return None
    parts = link.rstrip('/').split('/')
    try:
        return int(parts[-3]), int(parts[-2]), int(parts[-1])
    except (ValueError, IndexError):
        return None


@dataclass
class _AdminSession:
    """session state shared by all repl commands."""

    api_key: str
    server_url: str
    current_guild: dict | None = None  # {id, name, slug, role}
    channels: list[dict] = field(default_factory=list)  # [{id, name, slug, type}]
    roles: list[dict] = field(default_factory=list)  # [{id, name, slug}]

    def _request(self, client: httpx.Client, method: str, path: str, **kwargs: Any) -> Any:
        """make an authenticated request; print error and return None on non-2xx."""
        url = f'{self.server_url}{path}'
        headers = {'Authorization': f'Bearer {self.api_key}'}
        r = client.request(method, url, headers=headers, **kwargs)
        if r.is_success:
            return r.json()
        try:
            detail = r.json().get('detail', r.text)
        except Exception:
            detail = r.text
        print(f'error {r.status_code}: {detail}')
        return None

    def get_guilds(self, client: httpx.Client) -> list[dict]:
        result = self._request(client, 'GET', '/api/admin/guilds')
        return result if isinstance(result, list) else []

    def select_guild(self, client: httpx.Client, slug: str) -> bool:
        guilds = self.get_guilds(client)
        guild = next((g for g in guilds if g.get('slug') == slug), None)
        if guild is None:
            print(f'guild not found: {slug}')
            return False
        channels = self._request(client, 'GET', f'/api/admin/guilds/{slug}/channels')
        if channels is None:
            return False
        roles = self._request(client, 'GET', f'/api/admin/guilds/{slug}/roles')
        if roles is None:
            return False
        self.current_guild = guild
        self.channels = channels
        self.roles = roles
        return True

    def refresh(self, client: httpx.Client) -> bool:
        if not self.require_guild():
            return False
        slug = self.current_guild['slug']  # type: ignore[index]
        channels = self._request(client, 'GET', f'/api/admin/guilds/{slug}/channels')
        if channels is None:
            return False
        roles = self._request(client, 'GET', f'/api/admin/guilds/{slug}/roles')
        if roles is None:
            return False
        self.channels = channels
        self.roles = roles
        return True

    def resolve_channel_slug(self, slug: str) -> dict | None:
        return next((ch for ch in self.channels if ch.get('slug') == slug), None)

    def resolve_channel_name(self, name: str) -> dict | None:
        """look up a channel by slug or name fragment."""
        name = name.lstrip('#').lower()
        by_slug = next((ch for ch in self.channels if ch.get('slug') == name), None)
        if by_slug:
            return by_slug
        return next((ch for ch in self.channels if ch.get('name', '').lower() == name), None)

    def resolve_role_slug(self, slug: str) -> dict | None:
        return next((r for r in self.roles if r.get('slug') == slug), None)

    def require_guild(self) -> bool:
        if self.current_guild is None:
            print('no guild selected - run: guild use <slug>')
            return False
        return True

    def guild_slug(self) -> str:
        return self.current_guild['slug']  # type: ignore[index]

    def guild_id(self) -> int:
        return int(self.current_guild['id'])  # type: ignore[index]


class AdminCmd(cmd.Cmd):
    """nova-admin interactive repl."""

    prompt = 'nova-admin> '

    def __init__(self, session: _AdminSession, client: httpx.Client) -> None:
        super().__init__()
        self.session = session
        self.client = client

    # --- guild ---

    def do_guild(self, arg: str) -> None:
        """guild list | use <slug> | channels | roles | status | refresh."""
        parts = arg.split(None, 1)
        if not parts:
            print('usage: guild list | use <slug> | channels | roles | status | refresh')
            return
        sub = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ''

        if sub == 'list':
            guilds = self.session.get_guilds(self.client)
            if not guilds:
                print('(no guilds)')
            for g in guilds:
                active = ' *' if self.session.current_guild and self.session.current_guild.get('slug') == g.get('slug') else ''
                print(f'{g["slug"]:<30} {g["name"]}{active}')

        elif sub == 'use':
            if not rest:
                print('usage: guild use <slug>')
                return
            if self.session.select_guild(self.client, rest):
                g = self.session.current_guild
                print(f'switched to {rest!r} ({g["name"]}, role={g.get("role")})')

        elif sub == 'channels':
            if not self.session.require_guild():
                return
            if not self.session.channels:
                print('(no channels cached - run: guild use <slug>)')
                return
            for ch in self.session.channels:
                print(f'{ch["slug"]:<30} {ch["name"]:<30} {ch["type"]}')

        elif sub == 'roles':
            if not self.session.require_guild():
                return
            if not self.session.roles:
                print('(no roles cached - run: guild use <slug>)')
                return
            for r in self.session.roles:
                print(f'{r["slug"]:<30} {r["name"]}')

        elif sub == 'status':
            if not self.session.require_guild():
                return
            g = self.session.current_guild
            print(f'guild:    {g["name"]}')
            print(f'slug:     {g["slug"]}')
            print(f'id:       {g["id"]}')
            print(f'role:     {g.get("role", "?")}')
            print(f'channels: {len(self.session.channels)} cached')
            print(f'roles:    {len(self.session.roles)} cached')

        elif sub == 'refresh':
            if self.session.refresh(self.client):
                print('channels and roles refreshed')

        else:
            print('usage: guild list | use <slug> | channels | roles | status | refresh')

    # --- config ---

    def do_config(self, arg: str) -> None:
        """config get <key> | set <key> <value> | list [section]."""
        parts = arg.split(None, 2)
        if not parts:
            print('usage: config get <key> | config set <key> <value> | config list [section]')
            return
        sub = parts[0]

        if sub == 'list':
            if not self.session.require_guild():
                return
            section = parts[1].strip() if len(parts) > 1 else ''
            if section:
                slug = self.session.guild_slug()
                result = self.session._request(self.client, 'GET', f'/api/admin/guilds/{slug}/config/{section}')
                if result is not None:
                    print(json.dumps(result['value'], indent=2))
            else:
                print('sections: ' + ', '.join(_CONFIG_SECTIONS))

        elif sub == 'get':
            if len(parts) < 2:
                print('usage: config get <key>')
                return
            if not self.session.require_guild():
                return
            key = parts[1]
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'GET', f'/api/admin/guilds/{slug}/config/{key}')
            if result is not None:
                print(f'{result["key"]} = {result["value"]!r}')

        elif sub == 'set':
            if len(parts) < 3:
                print('usage: config set <key> <value>')
                return
            if not self.session.require_guild():
                return
            key, raw_value = parts[1], parts[2]
            try:
                value: Any = json.loads(raw_value)
            except json.JSONDecodeError:
                value = raw_value
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'PATCH', f'/api/admin/guilds/{slug}/config/{key}', json={'value': value})
            if result is not None:
                print(f'set {result["key"]} = {result["value"]!r}')

        else:
            print('usage: config get <key> | config set <key> <value> | config list [section]')

    # --- feature ---

    def do_feature(self, arg: str) -> None:
        """feature list | on <name> | off <name>."""
        parts = arg.split(None, 1)
        if not parts:
            print('usage: feature list | on <name> | off <name>')
            return
        sub = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ''

        if sub == 'list':
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'GET', f'/api/admin/guilds/{slug}/features')
            if result is not None:
                for f in result.get('features', []):
                    state = 'on' if f['enabled'] else 'off'
                    print(f'{f["name"]:<20} {state}')

        elif sub in ('on', 'off'):
            if not rest:
                print(f'usage: feature {sub} <name>')
                return
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            action = 'enable' if sub == 'on' else 'disable'
            result = self.session._request(self.client, 'POST', f'/api/admin/guilds/{slug}/features/{rest}/{action}')
            if result is not None:
                state = 'on' if result.get('enabled') else 'off'
                print(f'feature {result["feature"]!r} -> {state}')

        else:
            print('usage: feature list | on <name> | off <name>')

    # --- reload ---

    def do_reload(self, arg: str) -> None:
        """reload guild | reload theme."""
        target = arg.strip()
        if target == 'guild':
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'POST', '/api/admin/reload/guild', json={'guild_slug': slug})
            if result is not None:
                print('guild reload triggered')
        elif target == 'theme':
            result = self.session._request(self.client, 'POST', '/api/admin/reload/theme')
            if result is not None:
                print('theme reload triggered')
        else:
            print('usage: reload guild | reload theme')

    # --- backfill ---

    def do_backfill(self, arg: str) -> None:
        """backfill channel <channel> | backfill guild [--days N]."""
        parts = arg.split()
        if not parts:
            print('usage: backfill channel <channel> | backfill guild [--days N]')
            return
        sub = parts[0]

        if sub == 'channel':
            if len(parts) < 2:
                print('usage: backfill channel <channel>')
                return
            if not self.session.require_guild():
                return
            channel_name = parts[1]
            ch = self.session.resolve_channel_name(channel_name)
            if ch is None:
                print(f'channel not found: {channel_name!r} (run: guild channels)')
                return
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'POST', f'/api/admin/ops/{slug}/backfill/channel', json={'channel_id': int(ch['id'])})
            if result is not None:
                print(f'scheduled: backfill channel #{ch["name"]} - check bot logs for progress')

        elif sub == 'guild':
            days = 1
            if '--days' in parts:
                idx = parts.index('--days')
                if idx + 1 < len(parts):
                    try:
                        days = int(parts[idx + 1])
                    except ValueError:
                        print('--days requires an integer')
                        return
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'POST', f'/api/admin/ops/{slug}/backfill/guild', json={'lookback_days': days})
            if result is not None:
                print(f'scheduled: backfill guild (last {days} days) - check bot logs for progress')

        else:
            print('usage: backfill channel <channel> | backfill guild [--days N]')

    # --- ccboard ---

    def do_ccboard(self, arg: str) -> None:
        """ccboard regen | purge <id> | recover | cleanup [--confirm] | recount [<id>] [--confirm] | reactions <id>."""
        parts = arg.split()
        if not parts:
            print('usage: ccboard regen | purge <id> | recover | cleanup [--confirm] | recount [<id>] [--confirm] | reactions <id>')
            return
        sub = parts[0]

        if sub == 'regen':
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'POST', f'/api/admin/ops/{slug}/ccboard/regen')
            if result is not None:
                print(f'marked {result["affected"]:,} entries dirty')

        elif sub == 'purge':
            if len(parts) < 2:
                print('usage: ccboard purge <message-id-or-link>')
                return
            message_id = _parse_message_id(parts[1])
            if message_id is None:
                print(f'could not parse message id from {parts[1]!r}')
                return
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'POST', f'/api/admin/ops/{slug}/ccboard/purge', json={'message_id': message_id})
            if result is not None:
                post_note = ' + deleted post' if result.get('deleted_post') else ''
                print(f'purged entry {result["message_id"]}{post_note}')

        elif sub == 'recover':
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            print('running (may take up to 90s)...')
            result = self.session._request(self.client, 'POST', f'/api/admin/ops/{slug}/ccboard/recover', json={'dry_run': True})
            if result is not None:
                print(result['summary'])

        elif sub == 'cleanup':
            confirm = '--confirm' in parts
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            if not confirm:
                print('dry-run (pass --confirm to apply)')
            else:
                print('running (may take up to 90s)...')
            result = self.session._request(self.client, 'POST', f'/api/admin/ops/{slug}/ccboard/cleanup', json={'dry_run': not confirm})
            if result is not None:
                print(result['summary'])

        elif sub == 'recount':
            confirm = '--confirm' in parts
            remaining = [p for p in parts[1:] if p != '--confirm']
            message_id: int | None = None
            if remaining:
                message_id = _parse_message_id(remaining[0])
                if message_id is None:
                    print(f'could not parse message id from {remaining[0]!r}')
                    return
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            if not confirm:
                print('dry-run (pass --confirm to apply)')
            if message_id is None:
                print('running guild-wide (may take up to 90s)...')
            result = self.session._request(
                self.client,
                'POST',
                f'/api/admin/ops/{slug}/ccboard/recount',
                json={'message_id': message_id, 'dry_run': not confirm},
            )
            if result is not None:
                print(result['summary'])

        elif sub == 'reactions':
            if len(parts) < 2:
                print('usage: ccboard reactions <message-id-or-link>')
                return
            message_id = _parse_message_id(parts[1])
            if message_id is None:
                print(f'could not parse message id from {parts[1]!r}')
                return
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'GET', f'/api/admin/ops/{slug}/ccboard/reactions', params={'message_id': message_id})
            if result is not None:
                rows = result.get('reactions', [])
                if not rows:
                    print(f'no reactions for {result["message_id"]}')
                else:
                    print(f'{len(rows)} reaction(s) for {result["message_id"]}:')
                    for r in rows:
                        removed = ' [removed]' if r.get('removed') else ''
                        super_tag = ' [super]' if r.get('is_super') else ''
                        print(f'  {r["emoji_str"]} by {r["user_id"]} {r["point_value"]:+d}{super_tag}{removed}')

        else:
            print('usage: ccboard regen | purge <id> | recover | cleanup [--confirm] | recount [<id>] [--confirm] | reactions <id>')

    # --- trigger ---

    def do_trigger(self, arg: str) -> None:
        """trigger logo | trigger year-links | trigger emoji-sync."""
        target = arg.strip()

        if target == 'logo':
            result = self.session._request(self.client, 'POST', '/api/admin/ops/trigger/logo')
            if result is not None:
                print('scheduled: logo update - check bot logs for progress')

        elif target == 'year-links':
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'POST', f'/api/admin/ops/{slug}/trigger/year-links')
            if result is not None:
                print('scheduled: year-links rebuild - check bot logs for progress')

        elif target == 'emoji-sync':
            result = self.session._request(self.client, 'POST', '/api/admin/ops/trigger/emoji-sync')
            if result is not None:
                egg = ', '.join(result.get('egg_emojis', []))
                progress = ', '.join(result.get('progress_emojis', []))
                print(f'done: egg={egg} | progress={progress}')

        else:
            print('usage: trigger logo | trigger year-links | trigger emoji-sync')

    # --- info ---

    def do_info(self, arg: str) -> None:
        """info version | info year-stats | info epoch | info scheduler."""
        target = arg.strip()

        if target == 'version':
            result = self.session._request(self.client, 'GET', '/api/admin/ops/info/version')
            if result is not None:
                print(f'{result["title"]} {result["version"]} ({result["schema"]})')
                print(f'python:    {result["python"]}')
                print(f'distro:    {result["distro"]}')
                print(f'built:     {result["build_time"]}')

        elif target == 'year-stats':
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'GET', f'/api/admin/ops/{slug}/info/year-stats')
            if result is not None:
                print(f'current year:  {result["current_year"]} PC')
                print(f'elapsed days:  {result["elapsed_days"]}')
                print(f'epoch time:    {result["epoch_time"]} (year {result["epoch_year"]} PC)')
                span_d = result["year_span_duration"]
                print(f'year span:     {result["year_span_start"]} - {result["year_span_end"]} ({span_d} days)')

        elif target == 'epoch':
            if not self.session.require_guild():
                return
            slug = self.session.guild_slug()
            result = self.session._request(self.client, 'GET', f'/api/admin/ops/{slug}/info/epoch')
            if result is not None:
                rollover_h = result['rollover_minutes'] // 60
                rollover_m = result['rollover_minutes'] % 60
                print(f'time:     {result["time"]}')
                print(f'year:     {result["year"]} PC')
                print(f'length:   {result["length"]} days')
                print(f'paused:   {result["paused"]}')
                print(f'rollover: {rollover_h:02d}:{rollover_m:02d}')

        elif target == 'scheduler':
            result = self.session._request(self.client, 'GET', '/api/admin/ops/info/scheduler')
            if result is not None:
                tasks = result.get('running', [])
                print(f'running ({result["count"]}): {", ".join(tasks) if tasks else "(none)"}')

        else:
            print('usage: info version | info year-stats | info epoch | info scheduler')

    # --- inspect ---

    def do_inspect(self, arg: str) -> None:
        """inspect message <discord-message-link>."""
        parts = arg.split(None, 1)
        if not parts or parts[0] != 'message':
            print('usage: inspect message <discord-message-link>')
            return
        if len(parts) < 2:
            print('usage: inspect message <discord-message-link>')
            return
        link = parts[1].strip()
        parsed = _parse_message_link(link)
        if parsed is None:
            print('could not parse message link - expected: https://discord.com/channels/GUILD/CHANNEL/MESSAGE')
            return
        guild_id, channel_id, message_id = parsed
        result = self.session._request(
            self.client,
            'GET',
            '/api/admin/ops/inspect/message',
            params={'guild_id': guild_id, 'channel_id': channel_id, 'message_id': message_id},
        )
        if result is not None:
            print(f'message:  {result["id"]}')
            print(f'author:   {result["author"]["name"]} ({result["author"]["id"]})')
            print(f'channel:  {result["channel_id"]}')
            ts = result.get('timestamp', '')
            print(f'time:     {ts}')
            content = result.get('content', '')
            if content:
                preview = (content[:200] + '...') if len(content) > 200 else content
                print(f'content:  {preview}')
            if result.get('attachments'):
                for a in result['attachments']:
                    print(f'attach:   {a["filename"]}')
            if result.get('reactions'):
                rxn = ' '.join(f'{r["emoji"]}x{r["count"]}' for r in result['reactions'])
                print(f'reactions:{rxn}')
            if result.get('embeds'):
                print(f'embeds:   {len(result["embeds"])}')

    # --- exit ---

    def do_exit(self, arg: str) -> bool:
        """exit the repl."""
        return True

    def do_EOF(self, arg: str) -> bool:
        """exit on ctrl-d."""
        print()
        return True


def main() -> int:
    parser = argparse.ArgumentParser(
        prog='nova_admin',
        description='interactive admin repl for attu_server',
    )
    parser.add_argument(
        '--api-key',
        default=os.environ.get('ATTU_ADMIN_KEY'),
        help='admin API key (or set $ATTU_ADMIN_KEY)',
    )
    parser.add_argument(
        '--server',
        default=os.environ.get('ATTU_SERVER_URL', 'http://localhost:8000'),
        help='attu_server base URL (or set $ATTU_SERVER_URL; default: http://localhost:8000)',
    )
    args = parser.parse_args()

    if not args.api_key:
        print('error: no API key - set --api-key or $ATTU_ADMIN_KEY', file=sys.stderr)
        return 1

    session = _AdminSession(api_key=args.api_key, server_url=args.server)
    # no read timeout so long-running ops (90s budget + latency) don't time out at the client
    with httpx.Client(timeout=httpx.Timeout(30.0, read=None)) as client:
        AdminCmd(session, client).cmdloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
