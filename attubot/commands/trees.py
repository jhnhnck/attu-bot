"""
AttuBot - Family Tree Editor Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import functools
import hashlib
import hmac
import json
import time
from typing import cast

import discord
import httpx
from discord import ApplicationCommand, ApplicationContext, Bot, SlashCommandGroup

from attubot import bot, config
from attubot.client.util import is_bot_owner
from attubot.logging import get_logger


logger = get_logger(__name__)

# --- Coming Soon Gate ---


def _coming_soon(fn):
    """ephemeral 'coming soon' for non-owners; remove once feature is live"""

    @functools.wraps(fn)
    async def wrapper(ctx: ApplicationContext, *args, **kwargs):
        if not is_bot_owner(ctx):  # type: ignore[arg-type]
            await ctx.respond('this feature is coming soon.', ephemeral=True)
            return
        return await fn(ctx, *args, **kwargs)

    return wrapper


# --- Helpers ---


def _sign(body: bytes) -> tuple[str, str]:
    """return (X-Attu-Timestamp, X-Attu-Signature) header values for a request body"""
    ts = str(int(time.time()))
    payload = f'{ts}.'.encode() + body
    sig = hmac.new(config.trees.hmac_secret.encode(), payload, hashlib.sha256).hexdigest()
    return ts, f'sha256={sig}'


def _route_for(code: str) -> str:
    """pick dev or prod backend based on the second alpha character of the link code"""
    norm = ''.join(ch for ch in code.upper() if ch.isalnum())
    if len(norm) < 2:
        return config.trees.prod_base_url
    return config.trees.dev_base_url if norm[1] in {'X', 'Z'} else config.trees.prod_base_url


async def _api_call(method: str, url: str, body: dict | None = None) -> httpx.Response:
    body_bytes = (json.dumps(body) if body is not None else '{}').encode()
    ts, sig = _sign(body_bytes)
    headers = {
        'Content-Type': 'application/json',
        'X-Attu-Timestamp': ts,
        'X-Attu-Signature': sig,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        return await client.request(method, url, json=body, headers=headers)


def _extract_roles(user_id: int) -> list[str] | None:
    """check primary guild membership and build trees role list; returns None if not a member"""
    guild = bot.get_guild(config.primary_guild)
    if guild is None:
        return None
    member = guild.get_member(user_id)
    if member is None:
        return None
    guild_roles = config.guild(config.primary_guild).roles
    member_role_ids = {r.id for r in member.roles}
    roles = []
    if guild_roles.trees_admin_role and guild_roles.trees_admin_role in member_role_ids:
        roles.append('admin')
    if guild_roles.trees_user_role and guild_roles.trees_user_role in member_role_ids:
        roles.append('user')
    return roles


async def _fetch_view_url(tree_id: str, actor_discord_id: str) -> str | None:
    """fetch a view link url for a tree; returns None on any failure"""
    try:
        resp = await _api_call('POST', f'{config.trees.prod_base_url}/api/bot/trees/{tree_id}/view-link', {'actor_discord_id': actor_discord_id})
        if resp.status_code == 200:
            return resp.json().get('url')
    except Exception as e:
        logger.debug(f'_fetch_view_url: {e}')
    return None


async def _fetch_tree_name(actor_discord_id: str, tree_id: str) -> str | None:
    """fetch the display name of a tree from the user's tree list; returns None on any failure"""
    try:
        resp = await _api_call('GET', f'{config.trees.prod_base_url}/api/bot/users/{actor_discord_id}/trees')
        if resp.status_code == 200:
            return next((t['name'] for t in resp.json().get('trees', []) if t['id'] == tree_id), None)
    except Exception as e:
        logger.debug(f'_fetch_tree_name: {e}')
    return None


async def _tree_autocomplete(ctx: discord.AutocompleteContext) -> list[discord.OptionChoice]:
    """autocomplete handler shared by /trees share and /trees unshare"""
    if not config.is_owner(ctx.interaction.user.id):
        return []
    try:
        resp = await _api_call('GET', f'{config.trees.prod_base_url}/api/bot/users/{ctx.interaction.user.id}/trees')
        if resp.status_code != 200:
            return []
        trees = resp.json().get('trees', [])
        q = (ctx.value or '').lower()
        return [discord.OptionChoice(name=t['name'], value=t['id']) for t in trees if q in t['name'].lower()][:25]
    except Exception as e:
        logger.debug(f'_tree_autocomplete: {e}')
        return []


# --- Views ---


class _TreeSelectMenu(discord.ui.Select):
    def __init__(self, trees: list[dict]):
        options = [discord.SelectOption(label=t['name'][:100], value=t['id']) for t in trees[:25]]
        super().__init__(placeholder='select a tree...', options=options)
        self._trees = {t['id']: t['name'] for t in trees}

    async def callback(self, interaction: discord.Interaction):
        tree_id = self.values[0]
        tree_name = self._trees.get(tree_id, tree_id)
        await interaction.response.defer()
        try:
            resp = await _api_call(
                'POST',
                f'{config.trees.prod_base_url}/api/bot/trees/{tree_id}/view-link',
                {'actor_discord_id': str(interaction.user.id)},
            )
            if resp.status_code == 200:
                url = resp.json()['url']
                view = discord.ui.View(timeout=None)
                view.add_item(discord.ui.Button(label='open tree', style=discord.ButtonStyle.link, url=url))
                await interaction.edit_original_response(content=f'**{tree_name}**', view=view)
            else:
                await interaction.edit_original_response(content='could not generate a view link right now.')
        except Exception:
            await interaction.edit_original_response(content="the family tree service isn't reachable right now.")


class TreesShowView(discord.ui.View):
    def __init__(self, trees: list[dict]):
        super().__init__(timeout=1800)
        self.add_item(_TreeSelectMenu(trees))


# --- Commands ---

trees_group = SlashCommandGroup('trees', description='Family tree editor commands')


@trees_group.command(name='link', description='Link your Discord account to the family tree editor')
@discord.commands.option(name='code', required=True, description='Link code from the editor (e.g. AB-123456)')
@_coming_soon
async def trees_link(ctx: ApplicationContext, code: str):
    await ctx.defer(ephemeral=True)

    roles = _extract_roles(ctx.author.id)
    if roles is None:
        await ctx.respond("you're not in the server. how are you even doing this.", ephemeral=True)
        return
    if not roles:
        await ctx.respond('you must write your island first!', ephemeral=True)
        return

    base_url = _route_for(code)
    payload = {
        'code': code,
        'discord_id': str(ctx.author.id),
        'discord_username': ctx.author.global_name or ctx.author.name,
        'roles': roles,
    }

    try:
        resp = await _api_call('POST', f'{base_url}/api/bot/auth/link', payload)
    except (httpx.TimeoutException, httpx.ConnectError):
        await ctx.respond("the family tree service isn't reachable right now. try again in a moment.", ephemeral=True)
        return
    except Exception as e:
        logger.error(f'trees_link: unexpected http error: {e}')
        await ctx.respond('something went wrong on our end.', ephemeral=True)
        return

    if resp.status_code == 200:
        display_name = resp.json().get('display_name', ctx.author.name)
        await ctx.respond(f'linked as **{display_name}**. return to the editor to start syncing.', ephemeral=True)
    elif resp.status_code == 422:
        detail = resp.json().get('detail', '')
        if detail == 'code_expired':
            await ctx.respond('that code expired. open the editor and click "sign in" to get a new one.', ephemeral=True)
        elif detail == 'code_already_used':
            await ctx.respond("that code was already redeemed. if it wasn't you, generate a fresh one in the editor.", ephemeral=True)
        else:
            await ctx.respond("i don't recognize that code. double-check it in the editor.", ephemeral=True)
    elif resp.status_code == 401:
        logger.alert('trees_link: hmac rejected by server (401); check DISCORD_BOT_HMAC_SECRET')
        await ctx.respond('something went wrong on our end.', ephemeral=True)
    else:
        logger.error(f'trees_link: unexpected status {resp.status_code}')
        await logger.send_to_webhook(Exception(f'trees_link: unexpected status {resp.status_code} from {base_url}'))
        await ctx.respond('something went wrong on our end. an admin has been notified.', ephemeral=True)


@trees_group.command(name='show', description='List your family trees')
@_coming_soon
async def trees_show(ctx: ApplicationContext):
    await ctx.defer()

    try:
        resp = await _api_call('GET', f'{config.trees.prod_base_url}/api/bot/users/{ctx.author.id}/trees')
    except (httpx.TimeoutException, httpx.ConnectError):
        await ctx.respond("the family tree service isn't reachable right now. try again in a moment.")
        return
    except Exception as e:
        logger.error(f'trees_show: unexpected http error: {e}')
        await ctx.respond('something went wrong on our end.')
        return

    if resp.status_code == 404:
        await ctx.respond("you haven't linked your account yet. run `/trees link` with a code from the editor first.")
        return

    if resp.status_code != 200:
        logger.error(f'trees_show: unexpected status {resp.status_code}')
        await ctx.respond('something went wrong on our end.')
        return

    trees = resp.json().get('trees', [])
    if not trees:
        await ctx.respond('no trees yet. open the editor to create one.')
        return

    await ctx.respond('select a tree to view:', view=TreesShowView(trees))


@trees_group.command(name='share', description='Share a tree with another Discord user')
@discord.commands.option(name='tree', required=True, description='Tree to share', autocomplete=_tree_autocomplete)
@discord.commands.option(name='user', required=True, description='User to share with', input_type=discord.Member)
@discord.commands.option(name='role', required=True, description='Access level', choices=['viewer', 'editor'])
@_coming_soon
async def trees_share(ctx: ApplicationContext, tree: str, user: discord.Member, role: str):
    await ctx.defer()

    payload = {
        'actor_discord_id': str(ctx.author.id),
        'target_discord_id': str(user.id),
        'target_discord_username': user.global_name or user.name,
        'role': role,
    }

    try:
        resp = await _api_call('POST', f'{config.trees.prod_base_url}/api/bot/trees/{tree}/grants', payload)
    except (httpx.TimeoutException, httpx.ConnectError):
        await ctx.respond("the family tree service isn't reachable right now. try again in a moment.")
        return
    except Exception as e:
        logger.error(f'trees_share: unexpected http error: {e}')
        await ctx.respond('something went wrong on our end.')
        return

    if resp.status_code == 200:
        tree_name = (await _fetch_tree_name(str(ctx.author.id), tree)) or tree
        view_url = await _fetch_view_url(tree, str(user.id))
        msg = f'shared **{tree_name}** with {user.mention}.'
        if view_url:
            view = discord.ui.View(timeout=None)
            view.add_item(discord.ui.Button(label='open tree', style=discord.ButtonStyle.link, url=view_url))
            await ctx.respond(f'{msg} {user.mention}, you can view it here:', view=view)
        else:
            await ctx.respond(msg)
    elif resp.status_code == 403:
        await ctx.respond('you can only share trees you own.', ephemeral=True)
    elif resp.status_code == 404:
        await ctx.respond("that tree doesn't exist anymore.", ephemeral=True)
    elif resp.status_code == 400:
        await ctx.respond('invalid role; must be viewer or editor.', ephemeral=True)
    else:
        logger.error(f'trees_share: unexpected status {resp.status_code}')
        await ctx.respond('something went wrong on our end.', ephemeral=True)


@trees_group.command(name='unshare', description="Revoke a user's access to one of your trees")
@discord.commands.option(name='tree', required=True, description='Tree to unshare', autocomplete=_tree_autocomplete)
@discord.commands.option(name='user', required=True, description='User to remove', input_type=discord.Member)
@_coming_soon
async def trees_unshare(ctx: ApplicationContext, tree: str, user: discord.Member):
    await ctx.defer(ephemeral=True)

    tree_name = (await _fetch_tree_name(str(ctx.author.id), tree)) or tree
    payload = {
        'actor_discord_id': str(ctx.author.id),
        'target_discord_id': str(user.id),
    }

    try:
        resp = await _api_call('DELETE', f'{config.trees.prod_base_url}/api/bot/trees/{tree}/grants', payload)
    except (httpx.TimeoutException, httpx.ConnectError):
        await ctx.respond("the family tree service isn't reachable right now. try again in a moment.", ephemeral=True)
        return
    except Exception as e:
        logger.error(f'trees_unshare: unexpected http error: {e}')
        await ctx.respond('something went wrong on our end.', ephemeral=True)
        return

    target_display = user.global_name or user.name
    if resp.status_code == 204:
        await ctx.respond(f"removed **{target_display}**'s access to **{tree_name}**.", ephemeral=True)
    elif resp.status_code == 403:
        await ctx.respond('you can only unshare trees you own.', ephemeral=True)
    elif resp.status_code == 404:
        await ctx.respond("that tree doesn't exist anymore.", ephemeral=True)
    else:
        logger.error(f'trees_unshare: unexpected status {resp.status_code}')
        await ctx.respond('something went wrong on our end.', ephemeral=True)


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(cast(ApplicationCommand, trees_group))
