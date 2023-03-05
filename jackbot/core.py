"""
JackBot - Main file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from os import getenv

import discord
from discord.utils import escape_mentions

from jackbot.logging import get_logger
logger = get_logger(__name__)

# --- Initialization ---

logger.info('Initializing...')

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = discord.Bot(intents=intents)

# --- Slash Commands ---

@bot.slash_command(guilds_only=True)
async def gametime(ctx, message: str=None):
    if message != None and len(message) > 0:
        await ctx.respond(f"<@&1082043670620024924> from {ctx.author.mention}: `{escape_mentions(message)}`")
    else:
        await ctx.respond(f"<@&1082043670620024924> from {ctx.author.mention}!")

# --- Reactions ---

@bot.event
async def on_raw_reaction_add(payload):
    user = payload.member
    reaction = payload.emoji
    logger.info(f'Message from {reaction}: {user}')

# --- Events ---

@bot.event
async def on_ready():
    perms = '1512634297568'

    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})!')
    logger.info(f'Add to a server:\n\thttps://discordapp.com/oauth2/authorize?client_id={bot.application_id}&scope=bot&permissions={perms}')

    # await load_role_menu()

@bot.event
async def on_message(message):
    logger.info(f'Message from {message.author}: {message.content}')

# --- Trigger Function ---

def start_bot_loop():
    global bot

    logger.info('Starting bot...')
    bot.run(getenv('BOT_TOKEN'))
