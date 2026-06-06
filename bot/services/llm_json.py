from __future__ import annotations

import asyncio
import json
import re
import socket
from typing import Any

import aiohttp

from bot.config import settings


class LLMJSONError(RuntimeError):
    pass


async def complete_json_openai_compatible(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    json_mode: bool,
) -> dict[str, Any]:
    base_url, api_key, force_ipv4 = _provider_settings(provider)
    if not api_key:
        raise LLMJSONError(f"API key is not configured for provider: {provider}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    connector = aiohttp.TCPConnector(family=socket.AF_INET if force_ipv4 else socket.AF_UNSPEC)

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector) as session:
            async with session.post(f"{base_url.rstrip('/')}/chat/completions", json=body) as response:
                payload = await _read_response(response)
                if response.status >= 400:
                    raise LLMJSONError(f"{provider} returned HTTP {response.status}: {payload}")
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise LLMJSONError(f"{provider} network error: {exc}") from exc

    content = _extract_message_content(payload)
    try:
        parsed = json.loads(_extract_json_object(content))
    except json.JSONDecodeError as exc:
        raise LLMJSONError(f"{provider} returned non-JSON content: {content[:1200]}") from exc

    if not isinstance(parsed, dict):
        raise LLMJSONError(f"{provider} returned non-object JSON: {parsed}")
    return parsed


def _provider_settings(provider: str) -> tuple[str, str | None, bool]:
    normalized = provider.lower().strip()
    if normalized == "neuroapi":
        return settings.neuroapi_base_url, settings.neuroapi_api_key, settings.neuroapi_force_ipv4
    if normalized == "aitunnel":
        return settings.aitunnel_base_url, settings.aitunnel_api_key, settings.aitunnel_force_ipv4
    raise LLMJSONError(f"Unsupported OpenAI-compatible provider: {provider}")


async def _read_response(response: aiohttp.ClientResponse) -> dict[str, Any]:
    try:
        payload = await response.json(content_type=None)
    except (aiohttp.ContentTypeError, ValueError):
        return {"text": await response.text()}
    if isinstance(payload, dict):
        return payload
    return {"payload": payload}


def _extract_message_content(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMJSONError(f"Unexpected LLM response: {payload}") from exc
    if not isinstance(content, str):
        raise LLMJSONError(f"LLM response content is not text: {payload}")
    return content


def _extract_json_object(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]
