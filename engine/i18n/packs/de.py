"""German language pack.

Uses ``ml6team/distilbert-base-german-cased-toxic-comments`` for multi-label
toxic-comment classification.  The model outputs scores for the labels
``toxic``, ``severe_toxic``, ``obscene``, ``threat``, ``insult``,
``identity_hate``, and ``neutral``; these are mapped to our internal
categories via :meth:`get_labels`.
"""

from __future__ import annotations

import logging
from typing import Any

from i18n.base import HarmPattern, Helpline, LanguagePack

logger = logging.getLogger(__name__)

_de_classifier: Any = None


class GermanPack(LanguagePack):
    lang_code = "de"
    lang_name = "Deutsch"

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def detect(self, text: str) -> float:
        """Return probability that *text* is German via langdetect."""
        try:
            from langdetect import detect_langs  # type: ignore[import]

            for lang in detect_langs(text):
                if lang.lang == "de":
                    return float(lang.prob)
        except Exception:
            pass
        return 0.0

    # ------------------------------------------------------------------
    # ML classifier
    # ------------------------------------------------------------------

    def get_classifier(self) -> Any:
        """Return a cached German toxic-comment classification pipeline."""
        global _de_classifier
        if _de_classifier is None:
            try:
                from transformers import pipeline

                _de_classifier = pipeline(
                    "text-classification",
                    model="ml6team/distilbert-base-german-cased-toxic-comments",
                    device=-1,  # CPU
                    top_k=None,  # return all label scores
                )
                logger.info(
                    "German classifier loaded: "
                    "ml6team/distilbert-base-german-cased-toxic-comments"
                )
            except Exception:
                logger.warning("Could not load German classifier – using stub scores")
        return _de_classifier

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
        """Return German harm patterns aggregated from the skill files."""
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
                name="Nummer gegen Kummer",
                phone="116 111",
                url="https://www.nummergegenkummer.de",
                description="Kostenlose Beratung für Kinder und Jugendliche, Mo–Sa 14–20 Uhr.",
            ),
            Helpline(
                name="Telefonseelsorge",
                phone="0800 111 0 111",
                url="https://www.telefonseelsorge.de",
                description="Kostenlos, 24/7, anonym.",
            ),
            Helpline(
                name="Jugendnotmail",
                url="https://www.jugendnotmail.de",
                description="Online-Beratung per E-Mail für Jugendliche in Krisen.",
            ),
            Helpline(
                name="Klicksafe",
                url="https://www.klicksafe.de",
                description="EU-Initiative für mehr Sicherheit im Internet.",
            ),
        ]
