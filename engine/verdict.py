"""Verdict logic — turns raw scores into allow / delete / flag decisions.

Core child-safety categories are always evaluated against their thresholds.
Opt-in categories (enabled via ``ENABLED_CATEGORIES``) are evaluated against
the thresholds declared in their skill markdown files; their scores arrive in
:attr:`ModerationScores.extra`.
"""

from __future__ import annotations

from typing import Literal

from config import settings
from models import ModerationResult, ModerationScores

# Score at or above which a core field is considered "elevated" (→ flag)
_FLAG_THRESHOLD = 0.4


def decide(scores: ModerationScores) -> ModerationResult:
    """Apply threshold rules and return the final moderation result."""
    from moderation.registry import ModerationRegistry

    reasons: list[str] = []
    # (name, score, delete_threshold, flag_threshold)
    checks: list[tuple[str, float, float, float]] = [
        ("violence", scores.violence, settings.threshold_violence, _FLAG_THRESHOLD),
        ("sexual_violence", scores.sexual_violence, settings.threshold_sexual_violence, _FLAG_THRESHOLD),
        ("nsfw", scores.nsfw, settings.threshold_nsfw, _FLAG_THRESHOLD),
        ("deepfake_suspect", scores.deepfake_suspect, settings.threshold_deepfake, _FLAG_THRESHOLD),
        ("cyberbullying", scores.cyberbullying, settings.threshold_cyberbullying, _FLAG_THRESHOLD),
    ]

    # Opt-in categories (only those enabled via ENABLED_CATEGORIES)
    for skill in ModerationRegistry.active_opt_in(settings.enabled_categories):
        score = scores.extra.get(skill.category_id, 0.0)
        checks.append((skill.category_id, score, skill.threshold(), skill.flag_threshold))

    for name, score, delete_thr, _flag_thr in checks:
        if score >= delete_thr:
            reasons.append(name)

    verdict: Literal["allow", "delete", "flag"]
    if reasons:
        verdict = "delete"
    else:
        elevated = [name for name, score, _d, flag_thr in checks if score >= flag_thr]
        if elevated:
            verdict = "flag"
            reasons = [f"elevated_{name}" for name in elevated]
        else:
            verdict = "allow"

    return ModerationResult(verdict=verdict, reasons=reasons, scores=scores, language=None)
