"""i18n framework for language-aware content moderation.

Usage:
    from i18n.registry import LanguageRegistry
    from i18n.detector import detect_language

    lang_code = detect_language(text)
    pack = LanguageRegistry.get(lang_code)
"""

from __future__ import annotations

# langdetect is randomised by default, so the same short message could be
# routed to different language packs (different patterns/models) on
# different requests. Seed it once for deterministic detection.
try:
    from langdetect import DetectorFactory  # type: ignore[import-untyped]

    DetectorFactory.seed = 0
except ImportError:  # pragma: no cover - langdetect is a hard dependency
    pass
