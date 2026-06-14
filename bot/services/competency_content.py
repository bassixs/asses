from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LIBRARY_PATH = Path(__file__).resolve().parent.parent / "resources" / "competency_library.json"


@lru_cache(maxsize=1)
def _load_library() -> dict[str, Any]:
    try:
        with _LIBRARY_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        logger.error("Could not load competency library %s: %s", _LIBRARY_PATH, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _normalize(name: str) -> str:
    return re.sub(r"[^а-яё]", "", (name or "").lower())


@lru_cache(maxsize=1)
def _name_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for key, entry in _load_library().items():
        if isinstance(entry, dict):
            index[_normalize(entry.get("name", ""))] = key
        index[_normalize(key)] = key
    index.pop("", None)
    return index


def get_competency_content(name: str) -> dict[str, Any] | None:
    """Return curated {name, literature, courses, practice_tasks} for a competence name.

    Matches a notebook competence header (any case, extra words/levels) to the library
    by normalized Cyrillic-letters comparison, with a substring fallback.
    """
    library = _load_library()
    if not library:
        return None

    norm = _normalize(name)
    if not norm:
        return None

    index = _name_index()
    key = index.get(norm)
    if key is None:
        for candidate_norm, candidate_key in index.items():
            if candidate_norm and (candidate_norm in norm or norm in candidate_norm):
                key = candidate_key
                break
    if key is None:
        logger.info("No competency library match for '%s'", name)
        return None
    return library.get(key)
