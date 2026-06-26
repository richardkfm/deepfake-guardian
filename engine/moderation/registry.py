"""Moderation-skill registry with auto-discovery.

On first use the registry loads every ``*.md`` file in
``engine/moderation/skills/`` into a :class:`~moderation.skill.ModerationSkill`.
Adding or editing a moderation category = creating or editing one markdown file
in that directory — no Python changes required.

This mirrors :class:`i18n.registry.LanguageRegistry`, but discovers data files
instead of Python modules.
"""

from __future__ import annotations

import logging
from pathlib import Path

from i18n.base import HarmPattern
from moderation.loader import load_skill
from moderation.skill import ModerationSkill

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


class ModerationRegistry:
    """Singleton registry mapping category ids to :class:`ModerationSkill` instances."""

    _skills: dict[str, ModerationSkill] = {}
    _discovered: bool = False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @classmethod
    def discover(cls) -> None:
        """Load every skill markdown file in the skills directory."""
        cls._skills = {}
        if not _SKILLS_DIR.is_dir():
            logger.warning("Moderation skills directory not found: %s", _SKILLS_DIR)
            cls._discovered = True
            return

        for path in sorted(_SKILLS_DIR.glob("*.md")):
            try:
                skill = load_skill(path)
            except Exception:
                logger.warning("Failed to load moderation skill: %s", path.name)
                continue
            if skill.category_id in cls._skills:
                logger.warning("Duplicate moderation skill id: %s", skill.category_id)
                continue
            cls._skills[skill.category_id] = skill
            logger.info("Moderation skill registered: %s (core=%s)", skill.category_id, skill.core)

        cls._discovered = True

    @classmethod
    def _ensure_discovered(cls) -> None:
        if not cls._discovered:
            cls.discover()

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, category_id: str) -> ModerationSkill | None:
        cls._ensure_discovered()
        return cls._skills.get(category_id)

    @classmethod
    def all_skills(cls) -> list[ModerationSkill]:
        cls._ensure_discovered()
        return sorted(cls._skills.values(), key=lambda s: (s.order, s.category_id))

    @classmethod
    def core_skills(cls) -> list[ModerationSkill]:
        """Always-on categories, in display order."""
        return [s for s in cls.all_skills() if s.core]

    @classmethod
    def opt_in_skills(cls) -> list[ModerationSkill]:
        """Categories that only run when explicitly enabled."""
        return [s for s in cls.all_skills() if not s.core]

    @classmethod
    def active_opt_in(cls, enabled_ids: list[str]) -> list[ModerationSkill]:
        """Opt-in skills whose id appears in *enabled_ids*."""
        return [s for s in cls.opt_in_skills() if s.category_id in enabled_ids]

    # ------------------------------------------------------------------
    # Aggregation helpers (consumed by language packs / classifiers)
    # ------------------------------------------------------------------

    @classmethod
    def patterns_for_language(cls, lang_code: str) -> list[HarmPattern]:
        """All language-specific harm patterns across every skill, tagged by category."""
        out: list[HarmPattern] = []
        for skill in cls.all_skills():
            out.extend(skill.patterns.get(lang_code, []))
        return out

    @classmethod
    def labels_for_language(cls, lang_code: str) -> dict[str, str]:
        """Aggregated ``model-label -> internal-category`` map for *lang_code*."""
        out: dict[str, str] = {}
        for skill in cls.all_skills():
            out.update(skill.labels.get(lang_code, {}))
        return out

    @classmethod
    def messages_for_language(cls, lang_code: str) -> dict[str, str]:
        """Aggregated ``category -> educational message`` map for *lang_code*."""
        out: dict[str, str] = {}
        for skill in cls.all_skills():
            msg = skill.messages.get(lang_code)
            if msg:
                out[skill.category_id] = msg
        return out

    @classmethod
    def score_text_categories(
        cls, text: str, lang_code: str, enabled_ids: list[str]
    ) -> dict[str, float]:
        """Run every enabled opt-in *text* skill and return ``{category_id: score}``."""
        out: dict[str, float] = {}
        for skill in cls.active_opt_in(enabled_ids):
            if "text" not in skill.modalities:
                continue
            out[skill.category_id] = skill.score_text(text, lang_code)
        return out

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    @classmethod
    def reset(cls) -> None:
        """Clear the registry (used in tests to force re-discovery)."""
        cls._skills = {}
        cls._discovered = False
