from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)


class YandexGPTError(RuntimeError):
    pass


async def complete_json(
    *,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any] | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4000,
) -> dict[str, Any]:
    """Call YandexGPT and parse a JSON object from the model response."""
    headers = {
        "Authorization": f"Api-Key {settings.yandex_gpt_api_key}",
        "Content-Type": "application/json",
        "x-folder-id": settings.yandex_folder_id,
    }
    body = {
        "modelUri": settings.resolved_yandex_gpt_model_uri,
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": str(max_tokens),
        },
        "messages": [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": user_prompt},
        ],
    }
    if json_schema:
        body["json_schema"] = {"schema": json_schema}
    else:
        body["json_object"] = True

    logger.info("Sending assessment request to YandexGPT")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            settings.yandex_gpt_url,
            headers=headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=240),
        ) as response:
            payload = await response.json(content_type=None)

    if response.status >= 400:
        logger.error("YandexGPT error %s: %s", response.status, payload)
        raise YandexGPTError(f"YandexGPT returned HTTP {response.status}: {payload}")

    try:
        text = payload["result"]["alternatives"][0]["message"]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise YandexGPTError(f"Unexpected YandexGPT response: {payload}") from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("YandexGPT returned non-JSON text: %s", text)
        raise YandexGPTError("YandexGPT returned invalid JSON") from exc
