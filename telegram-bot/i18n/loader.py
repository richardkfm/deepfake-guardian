"""Bot message loader with language fallback.

Loads JSON message files from the ``telegram-bot/i18n/`` directory.
Falls back to English when the requested language file or key is missing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MESSAGES_DIR = Path(__file__).parent
_FALLBACK_LANG = "en"

# In-memory cache: lang_code → {key: template}
_cache: dict[str, dict[str, str]] = {}


def _load(lang: str) -> dict[str, str]:
    """Load and cache the message file for *lang*."""
    if lang not in _cache:
        path = _MESSAGES_DIR / f"{lang}.json"
        if path.exists():
            try:
                _cache[lang] = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("Failed to load i18n file: %s", path)
                _cache[lang] = {}
        else:
            _cache[lang] = {}
    return _cache[lang]


def available_languages() -> frozenset[str]:
    """Return the language codes that ship a message file (e.g. ``{"en", "de"}``)."""
    return frozenset(path.stem for path in _MESSAGES_DIR.glob("*.json"))


def get_message(key: str, lang: str = _FALLBACK_LANG, **kwargs: object) -> str:
    """Return a localised, formatted message string.

    Args:
        key: Message key (e.g. ``"flagged_content"``).
        lang: ISO 639-1 language code (e.g. ``"en"``, ``"de"``).
        **kwargs: Format placeholders injected via :meth:`str.format_map`.

    Returns:
        The formatted message string.  Falls back to English if the language
        file is missing or the key is not found.  Returns the raw key if not
        found even in the fallback language.
    """
    messages = _load(lang)
    template = messages.get(key)

    if template is None and lang != _FALLBACK_LANG:
        # Fallback to English
        fallback = _load(_FALLBACK_LANG)
        template = fallback.get(key)

    if template is None:
        logger.warning("Missing i18n key '%s' for lang '%s'", key, lang)
        return key  # last-resort: return the key itself

    if kwargs:
        try:
            return template.format_map(kwargs)
        except KeyError as exc:
            logger.warning("Missing format placeholder %s in key '%s'", exc, key)
            return template

    return template
