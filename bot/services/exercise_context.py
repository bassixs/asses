from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LIBRARY_PATH = Path(__file__).resolve().parent.parent / "resources" / "exercise_library.json"


@lru_cache(maxsize=1)
def _load_library() -> dict[str, Any]:
    try:
        with _LIBRARY_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        logger.error("Could not load exercise library %s: %s", _LIBRARY_PATH, exc)
        return {}
    return data if isinstance(data, dict) else {}


def load_exercise_library() -> dict[str, Any]:
    """The bundled curated exercise library, keyed by slug."""
    return _load_library()


def _normalize(name: str) -> str:
    return re.sub(r"[^а-яёa-z0-9]", "", (name or "").lower())


@lru_cache(maxsize=1)
def _name_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for key, entry in _load_library().items():
        index[_normalize(key)] = key
        if isinstance(entry, dict):
            index[_normalize(entry.get("name", ""))] = key
            for alias in entry.get("aliases", []) or []:
                index[_normalize(alias)] = key
    index.pop("", None)
    return index


def get_exercise_context(name: str | None) -> dict[str, Any] | None:
    """Return curated context for an exercise name.

    Matches an exercise title (any case, extra words) to the library by normalized
    comparison against the canonical name and aliases, with a substring fallback.
    """
    library = _load_library()
    if not library or not name:
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
        logger.info("No exercise library match for '%s'", name)
        return None
    return library.get(key)


def build_exercise_analysis_block(name: str | None, instructions_text: str | None = None) -> str:
    """Render a context block for the observer-notebook analysis prompt.

    Uploaded instruction text (if any) takes precedence; otherwise the bundled
    library is used. Empty string when neither is available, so analysis behaves
    exactly as before.
    """
    if instructions_text and instructions_text.strip():
        return (
            f"Инструкции к упражнению «{name or '—'}» (материалы ведущего, наблюдателя и участника). "
            "Используй их, чтобы понять сценарий: кто ролевой игрок, какие ситуации создаёт упражнение "
            "(это нужно, чтобы корректно ставить «НЗ»):\n"
            f"{instructions_text.strip()}"
        )

    context = get_exercise_context(name)
    if not context:
        return ""

    competencies = ", ".join(context.get("competencies", []) or [])
    parts = [f"Контекст упражнения «{context.get('name', name)}» (помогает решать про «НЗ» и проявления):"]
    if context.get("participant_role"):
        parts.append(f"- Роль оцениваемого участника: {context['participant_role']}")
    if context.get("role_play"):
        parts.append(f"- Что происходит в записи: {context['role_play']}")
    if context.get("observable_notes"):
        parts.append(f"- Какие проявления создаёт упражнение: {context['observable_notes']}")
    if competencies:
        parts.append(f"- Компетенции упражнения: {competencies}")
    return "\n".join(parts)


def build_role_labeling_hint(name: str | None, instructions_text: str | None = None) -> str:
    """Render the role-play context for the role-labeling prompt.

    Tells the model who the role-player ('ведущий') is and who the assessed
    participant ('участник') is in this exercise. Uploaded instructions take
    precedence over the bundled library. Empty when neither is available.
    """
    if instructions_text and instructions_text.strip():
        return (
            f"Инструкции к упражнению «{name or '—'}» (помогают понять, кто ролевой игрок/ведущий, "
            "а кто оцениваемый участник):\n"
            f"{instructions_text.strip()}"
        )

    context = get_exercise_context(name)
    if not context:
        return ""

    parts = [f"Контекст упражнения «{context.get('name', name)}»:"]
    if context.get("role_play"):
        parts.append(context["role_play"])
    if context.get("participant_role"):
        parts.append(f"Оцениваемый участник в этом упражнении: {context['participant_role']}")
    return "\n".join(parts)
