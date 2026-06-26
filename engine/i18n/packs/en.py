"""English language pack.

Uses ``facebook/bart-large-mnli`` for zero-shot text classification — the same
model that was previously hard-coded in ``classifiers.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from i18n.base import HarmPattern, Helpline, LanguagePack

logger = logging.getLogger(__name__)

_en_classifier: Any = None


class EnglishPack(LanguagePack):
    lang_code = "en"
    lang_name = "English"

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def detect(self, text: str) -> float:
        """Return probability that *text* is English via langdetect."""
        try:
            from langdetect import detect_langs  # type: ignore[import]

            for lang in detect_langs(text):
                if lang.lang == "en":
                    return float(lang.prob)
        except Exception:
            pass
        return 0.0

    # ------------------------------------------------------------------
    # ML classifier
    # ------------------------------------------------------------------

    def get_classifier(self) -> Any:
        """Return a cached zero-shot classification pipeline (BART MNLI)."""
        global _en_classifier
        if _en_classifier is None:
            try:
                from transformers import pipeline

                _en_classifier = pipeline(
                    "zero-shot-classification",
                    model="facebook/bart-large-mnli",
                    device=-1,  # CPU
                )
                logger.info("English classifier loaded: facebook/bart-large-mnli")
            except Exception:
                logger.warning("Could not load English classifier – using stub scores")
        return _en_classifier

    # ------------------------------------------------------------------
    # Label mapping
    # ------------------------------------------------------------------

    def get_labels(self) -> dict[str, str]:
        """Map model output labels to internal categories (from skill files)."""
        from moderation.registry import ModerationRegistry

        return ModerationRegistry.labels_for_language(self.lang_code)

    # ------------------------------------------------------------------
    # Harm patterns
    # ------------------------------------------------------------------

    def get_patterns(self) -> list[HarmPattern]:
        """Return English harm patterns aggregated from the skill files."""
        from moderation.registry import ModerationRegistry

        return ModerationRegistry.patterns_for_language(self.lang_code)

    # ------------------------------------------------------------------
    # Educational messages
    # ------------------------------------------------------------------

    def get_educational_messages(self) -> dict[str, str]:
        from moderation.registry import ModerationRegistry

        return ModerationRegistry.messages_for_language(self.lang_code)

    # ------------------------------------------------------------------
    # Helplines
    # ------------------------------------------------------------------

    def get_helplines(self) -> list[Helpline]:
        return [
            Helpline(
                name="Crisis Text Line",
                phone="Text HOME to 741741",
                url="https://www.crisistextline.org",
                description="Free, 24/7 crisis support via text.",
            ),
            Helpline(
                name="Cyberbullying Research Center",
                url="https://cyberbullying.org",
                description="Resources and research on cyberbullying prevention.",
            ),
            Helpline(
                name="StopBullying.gov",
                url="https://www.stopbullying.gov",
                description="US government resource on bullying and cyberbullying.",
            ),
        ]
