"""Moderation threshold profiles.

Profiles let operators choose a pre-configured strictness level instead of
tuning individual thresholds.  Individual env-var overrides still take
precedence (handled in :class:`~config.Settings`).

The threshold *values* now live in the per-category skill files
(``engine/moderation/skills/*.md``) — those markdown files are the single,
human-editable source of truth.  :func:`get_profile` reads the core skills via
:class:`~moderation.registry.ModerationRegistry` and assembles a
:class:`ThresholdProfile` for backwards compatibility with existing callers.

Available profiles:

* ``minors_strict`` — lowest thresholds; suitable for groups with minors
  where zero-tolerance is appropriate.
* ``default`` — balanced thresholds.
* ``permissive`` — higher thresholds; fewer interventions for adult
  communities where some rough language is acceptable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdProfile:
    """Immutable set of delete-thresholds for the core moderation categories."""

    violence: float
    sexual_violence: float
    nsfw: float
    deepfake: float
    cyberbullying: float


# Maps a ThresholdProfile field to the skill ``category_id`` that supplies it.
_FIELD_TO_SKILL = {
    "violence": "violence",
    "sexual_violence": "sexual_violence",
    "nsfw": "nsfw",
    "deepfake": "deepfake_suspect",
    "cyberbullying": "cyberbullying",
}

# Defensive fallback used only if a skill file is missing or unparseable, so the
# engine keeps working even with a broken skills directory.
_FALLBACK: dict[str, ThresholdProfile] = {
    "minors_strict": ThresholdProfile(0.5, 0.3, 0.4, 0.6, 0.4),
    "default": ThresholdProfile(0.5, 0.5, 0.8, 0.7, 0.65),
    "permissive": ThresholdProfile(0.85, 0.7, 0.75, 0.9, 0.8),
}


def get_profile(name: str) -> ThresholdProfile:
    """Return the threshold profile *name*, sourced from the skill files."""
    from moderation.registry import ModerationRegistry

    skills = {s.category_id: s for s in ModerationRegistry.core_skills()}
    fallback = _FALLBACK.get(name, _FALLBACK["default"])

    def _thr(field: str) -> float:
        skill = skills.get(_FIELD_TO_SKILL[field])
        if skill is None:
            return getattr(fallback, field)
        if name in skill.thresholds:
            return skill.thresholds[name]
        if "default" in skill.thresholds:
            return skill.thresholds["default"]
        return getattr(fallback, field)

    return ThresholdProfile(
        violence=_thr("violence"),
        sexual_violence=_thr("sexual_violence"),
        nsfw=_thr("nsfw"),
        deepfake=_thr("deepfake"),
        cyberbullying=_thr("cyberbullying"),
    )
