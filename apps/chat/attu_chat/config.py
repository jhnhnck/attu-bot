"""
AttuBot - Chat config schema (dormant)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

defines the [chat] TOML section that the bot used to load into BotConfig.chat
and the runtime ChatConfigDocument loader. detached from the bot's config flow
while chat is offline; revival hooks this back into BotConfig.on_init/on_load.
"""

from pydantic import BaseModel


class ChatConfig(BaseModel):
    """[chat] section in attu-bot.toml; static config consumed by ingestor and /ask."""

    qdrant_url: str = 'http://qdrant:6333'
    ingestor_api_url: str = 'http://ingestor:8001'
    ingestor_token: str = ''
    llm_primary_url: str = 'http://localhost:8080'
    llm_fallback_url: str = 'http://llama-server:8080'
    llm_api_key: str = ''
    anthropic_api_key: str = ''
    ask_cooldown_seconds: int = 30
    embedding_model: str = 'all-MiniLM-L6-v2'
    prompts_dir: str = 'assets/prompts'
