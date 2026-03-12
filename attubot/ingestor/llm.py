"""
AttuBot - LLM Client (llama.cpp OpenAI-compatible API)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import json
from collections.abc import AsyncIterator

import httpx

from attubot.core import config
from attubot.logging import get_logger


logger = get_logger(__name__)

_LLM_CONNECT_TIMEOUT = 10.0  # seconds; fail fast if server isn't reachable
_LLM_READ_TIMEOUT = None      # no cap; let inference take as long as it needs on cpu

_llm: 'LLMClient | None' = None


def _get_llm() -> 'LLMClient':
    global _llm  # noqa: PLW0603 - lazy singleton initialization requires global
    if _llm is None:
        _llm = LLMClient(config.chat.llm_primary_url, config.chat.llm_fallback_url)
    return _llm


class LLMClient:
    """http client for llama.cpp openai-compatible /v1/chat/completions endpoint"""

    def __init__(self, primary_url: str, fallback_url: str):
        self._primary = primary_url.rstrip('/')
        self._fallback = fallback_url.rstrip('/')

    async def complete(self, system: str, context: str, query: str) -> AsyncIterator[str]:
        """stream a chat completion; tries primary url first, falls back on connection error or timeout"""
        payload = {
            'messages': [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': f'{context}\n\n<query>{query}</query>'},
            ],
            'stream': True,
            'temperature': 0.7,
        }

        for url, label in ((self._primary, 'primary'), (self._fallback, 'fallback')):
            try:
                async for token in self._stream(url, payload):
                    yield token
                return
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warn(f'LLM {label} unavailable ({e!s}); {"falling back" if label == "primary" else "giving up"}')
                if label == 'fallback':
                    raise

    async def _stream(self, base_url: str, payload: dict) -> AsyncIterator[str]:
        """open a streaming SSE connection and yield token strings"""
        timeout = httpx.Timeout(connect=_LLM_CONNECT_TIMEOUT, read=_LLM_READ_TIMEOUT, write=30.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client, client.stream('POST', f'{base_url}/v1/chat/completions', json=payload) as res:
                res.raise_for_status()
                async for line in res.aiter_lines():
                    if not line.startswith('data: '):
                        continue
                    data = line[6:]
                    if data == '[DONE]':
                        return
                    try:
                        chunk = json.loads(data)
                        token = chunk['choices'][0]['delta'].get('content', '')
                        if token:
                            yield token
                    except (KeyError, json.JSONDecodeError):
                        continue
