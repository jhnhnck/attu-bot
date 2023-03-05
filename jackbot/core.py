"""
JackBot - Main file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from os import getenv

import discord

from jackbot.logging import get_logger
logger = get_logger(__name__)

# --- Initialization ---

logger.info('Initializing...')

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = discord.Bot(intents=intents)

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
