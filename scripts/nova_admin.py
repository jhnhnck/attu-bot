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


@dataclass
class _AdminSession:
    """session state shared by all repl commands.

    session methods are the testability boundary; do_* dispatch methods call these.
    """

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
        print(f'{r.status_code} {detail}')
        return None

    def get_guilds(self, client: httpx.Client) -> list[dict]:
        """fetch all guilds from the server; returns empty list on error."""
        result = self._request(client, 'GET', '/api/admin/guilds')
        return result if isinstance(result, list) else []

    def select_guild(self, client: httpx.Client, slug: str) -> bool:
        """select a guild by slug; fetch and cache its channels and roles.

        returns True on success, False if the guild slug is not found or any
        request fails.
        """
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
        """re-fetch channels and roles for the current guild.

        returns False if no guild is selected or any request fails.
        """
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
        """look up a channel by slug in the cached channel list."""
        return next((ch for ch in self.channels if ch.get('slug') == slug), None)

    def resolve_role_slug(self, slug: str) -> dict | None:
        """look up a role by slug in the cached role list."""
        return next((r for r in self.roles if r.get('slug') == slug), None)

    def require_guild(self) -> bool:
        """print an error and return False if no guild is currently selected."""
        if self.current_guild is None:
            print('no guild selected; run: use <guild-slug>')
            return False
        return True


class AdminCmd(cmd.Cmd):
    """nova-admin interactive repl -- type 'help' or '?' to list commands."""

    prompt = 'nova-admin> '

    def __init__(self, session: _AdminSession, client: httpx.Client) -> None:
        super().__init__()
        self.session = session
        self.client = client

    def do_guilds(self, arg: str) -> None:
        """list all guilds: guilds"""
        guilds = self.session.get_guilds(self.client)
        if not guilds:
            print('(no guilds)')
            return
        for g in guilds:
            print(f'{g["slug"]:<30} {g["name"]}')

    def do_use(self, arg: str) -> None:
        """select a guild by slug: use <guild-slug>"""
        slug = arg.strip()
        if not slug:
            print('usage: use <guild-slug>')
            return
        if self.session.select_guild(self.client, slug):
            print(f'switched to {slug!r}')

    def do_channels(self, arg: str) -> None:
        """list cached channels for the selected guild: channels"""
        if not self.session.require_guild():
            return
        if not self.session.channels:
            print('(no channels; run: use <guild-slug>)')
            return
        for ch in self.session.channels:
            print(f'{ch["slug"]:<30} {ch["name"]:<30} {ch["type"]}')

    def do_roles(self, arg: str) -> None:
        """list cached roles for the selected guild: roles"""
        if not self.session.require_guild():
            return
        if not self.session.roles:
            print('(no roles; run: use <guild-slug>)')
            return
        for r in self.session.roles:
            print(f'{r["slug"]:<30} {r["name"]}')

    def do_config(self, arg: str) -> None:
        """get or set a config value: config get <key> | config set <key> <value>"""
        parts = arg.split(None, 2)
        if not parts:
            print('usage: config get <key> | config set <key> <value>')
            return
        sub = parts[0]
        if sub == 'get':
            if len(parts) < 2:
                print('usage: config get <key>')
                return
            if not self.session.require_guild():
                return
            key = parts[1]
            slug = self.session.current_guild['slug']  # type: ignore[index]
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
            slug = self.session.current_guild['slug']  # type: ignore[index]
            result = self.session._request(self.client, 'PATCH', f'/api/admin/guilds/{slug}/config/{key}', json={'value': value})
            if result is not None:
                print(f'set {result["key"]} = {result["value"]!r}')
        else:
            print('usage: config get <key> | config set <key> <value>')

    def do_feature(self, arg: str) -> None:
        """enable or disable a feature: feature enable <name> | feature disable <name>"""
        parts = arg.split(None, 1)
        if len(parts) < 2 or parts[0] not in ('enable', 'disable'):
            print('usage: feature enable <name> | feature disable <name>')
            return
        sub, name = parts[0], parts[1].strip()
        if not self.session.require_guild():
            return
        slug = self.session.current_guild['slug']  # type: ignore[index]
        result = self.session._request(self.client, 'POST', f'/api/admin/guilds/{slug}/features/{name}/{sub}')
        if result is not None:
            state = 'enabled' if result.get('enabled') else 'disabled'
            print(f'feature {result["feature"]!r} {state}')

    def do_reload(self, arg: str) -> None:
        """trigger a config reload: reload guild | reload theme"""
        target = arg.strip()
        if target == 'guild':
            if not self.session.require_guild():
                return
            slug = self.session.current_guild['slug']  # type: ignore[index]
            result = self.session._request(self.client, 'POST', '/api/admin/reload/guild', json={'guild_slug': slug})
            if result is not None:
                print('guild reload triggered')
        elif target == 'theme':
            result = self.session._request(self.client, 'POST', '/api/admin/reload/theme')
            if result is not None:
                print('theme reload triggered')
        else:
            print('usage: reload guild | reload theme')

    def do_fix(self, arg: str) -> None:
        """run a fix operation: fix recalculate-starboard"""
        target = arg.strip()
        if target == 'recalculate-starboard':
            if not self.session.require_guild():
                return
            slug = self.session.current_guild['slug']  # type: ignore[index]
            result = self.session._request(self.client, 'POST', f'/api/admin/guilds/{slug}/fix/recalculate-starboard')
            if result is not None:
                print('recalculate-starboard completed')
        else:
            print('usage: fix recalculate-starboard')

    def do_refresh(self, arg: str) -> None:
        """re-fetch channels and roles for the current guild: refresh"""
        if self.session.refresh(self.client):
            print('channels and roles refreshed')

    def do_exit(self, arg: str) -> bool:
        """exit the repl: exit"""
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
        print('error: no API key -- set --api-key or $ATTU_ADMIN_KEY', file=sys.stderr)
        return 1

    session = _AdminSession(api_key=args.api_key, server_url=args.server)
    with httpx.Client(timeout=10.0) as client:
        AdminCmd(session, client).cmdloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
