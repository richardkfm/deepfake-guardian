"""In-memory representation of a moderation *skill*.

A skill is a single human-editable markdown file in
``engine/moderation/skills/<category_id>.md`` describing one moderation
category: its delete thresholds (per profile), the regex patterns that detect
it, the model labels that map to it, and the educational messages shown to
users.  The :mod:`~moderation.loader` parses each markdown file into one of
these objects and the :class:`~moderation.registry.ModerationRegistry` serves
them to the rest of the engine.

Categories come in two flavours:

* ``core: true``  — always-on child-safety categories (violence, nsfw, …).
* ``core: false`` — opt-in categories (advertising, political misinformation)
  that only run when listed in the ``ENABLED_CATEGORIES`` env var.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from i18n.base import HarmPattern


@dataclass
class ModerationSkill:
    """Parsed, ready-to-use representation of one moderation category."""

    category_id: str
    display_name: str
    core: bool = True
    order: int = 1000
    modalities: list[str] = field(default_factory=lambda: ["text"])
    # Delete thresholds keyed by profile name (minors_strict / default / permissive)
    thresholds: dict[str, float] = field(default_factory=dict)
    flag_threshold: float = 0.4
    description: str = ""
    # Regex patterns keyed by language code, plus language-neutral structural ones
    patterns: dict[str, list[HarmPattern]] = field(default_factory=dict)
    structural_patterns: list[HarmPattern] = field(default_factory=list)
    # model-output-label -> internal-category map, keyed by language code
    labels: dict[str, dict[str, str]] = field(default_factory=dict)
    # Educational message text keyed by language code
    messages: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Threshold resolution
    # ------------------------------------------------------------------

    def threshold(self) -> float:
        """Return the active delete threshold for this category.

        Resolution order:

        1. ``THRESHOLD_<CATEGORY_ID>`` env var, if set.
        2. The value for the active ``MODERATION_PROFILE``.
        3. The ``default`` profile value.
        4. ``0.5`` as a last resort.
        """
        env_key = f"THRESHOLD_{self.category_id.upper()}"
        env_val = os.getenv(env_key)
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass

        from config import settings

        profile = settings.moderation_profile
        if profile in self.thresholds:
            return self.thresholds[profile]
        if "default" in self.thresholds:
            return self.thresholds["default"]
        return 0.5

    # ------------------------------------------------------------------
    # Pattern scoring
    # ------------------------------------------------------------------

    def score_text(self, text: str, lang_code: str) -> float:
        """Return the highest matching pattern weight for *text* (0.0–1.0).

        Combines this category's language-specific patterns with its
        language-neutral structural patterns.  Never raises — a broken pattern
        set must not crash the moderation pipeline.
        """
        best = 0.0
        try:
            for harm in self.patterns.get(lang_code, []):
                if harm.pattern.search(text):
                    best = max(best, harm.weight)
            for harm in self.structural_patterns:
                if harm.pattern.search(text):
                    best = max(best, harm.weight)
        except Exception:
            return best
        return best
