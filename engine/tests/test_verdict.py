"""Unit tests for verdict.py — the threshold-based decision engine."""

from __future__ import annotations

import pytest

from models import ModerationScores
from verdict import decide


class TestDecideAllow:
    def test_all_zeros(self):
        scores = ModerationScores(violence=0.0, sexual_violence=0.0, nsfw=0.0, deepfake_suspect=0.0)
        result = decide(scores)
        assert result.verdict == "allow"
        assert result.reasons == []

    def test_all_below_flag_threshold(self):
        scores = ModerationScores(violence=0.1, sexual_violence=0.2, nsfw=0.3, deepfake_suspect=0.1)
        result = decide(scores)
        assert result.verdict == "allow"
        assert result.reasons == []


class TestDecideFlag:
    def test_violence_elevated(self):
        # 0.4 is exactly the flag threshold — should flag but not delete (delete is 0.5)
        scores = ModerationScores(violence=0.4, sexual_violence=0.0, nsfw=0.0, deepfake_suspect=0.0)
        result = decide(scores)
        assert result.verdict == "flag"
        assert "elevated_violence" in result.reasons

    def test_nsfw_elevated(self):
        scores = ModerationScores(violence=0.0, sexual_violence=0.0, nsfw=0.5, deepfake_suspect=0.0)
        result = decide(scores)
        assert result.verdict == "flag"
        assert "elevated_nsfw" in result.reasons

    def test_multiple_elevated(self):
        scores = ModerationScores(violence=0.45, sexual_violence=0.4, nsfw=0.0, deepfake_suspect=0.0)
        result = decide(scores)
        assert result.verdict == "flag"
        assert "elevated_violence" in result.reasons
        assert "elevated_sexual_violence" in result.reasons

    def test_just_below_delete_threshold(self):
        # Default violence threshold is 0.5 — 0.49 should flag, not delete
        scores = ModerationScores(violence=0.49, sexual_violence=0.0, nsfw=0.0, deepfake_suspect=0.0)
        result = decide(scores)
        assert result.verdict == "flag"


class TestDecideDelete:
    def test_violence_at_threshold(self):
        # Default threshold is 0.5 (same as sexual_violence)
        scores = ModerationScores(violence=0.5, sexual_violence=0.0, nsfw=0.0, deepfake_suspect=0.0)
        result = decide(scores)
        assert result.verdict == "delete"
        assert "violence" in result.reasons

    def test_sexual_violence_at_threshold(self):
        # Default threshold is 0.5 (same as violence)
        scores = ModerationScores(violence=0.0, sexual_violence=0.5, nsfw=0.0, deepfake_suspect=0.0)
        result = decide(scores)
        assert result.verdict == "delete"
        assert "sexual_violence" in result.reasons

    def test_nsfw_at_threshold(self):
        # Default threshold is 0.8
        scores = ModerationScores(violence=0.0, sexual_violence=0.0, nsfw=0.8, deepfake_suspect=0.0)
        result = decide(scores)
        assert result.verdict == "delete"
        assert "nsfw" in result.reasons

    def test_deepfake_at_threshold(self):
        # Default threshold is 0.7
        scores = ModerationScores(violence=0.0, sexual_violence=0.0, nsfw=0.0, deepfake_suspect=0.7)
        result = decide(scores)
        assert result.verdict == "delete"
        assert "deepfake_suspect" in result.reasons

    def test_multiple_reasons(self):
        scores = ModerationScores(violence=0.9, sexual_violence=0.8, nsfw=0.0, deepfake_suspect=0.0)
        result = decide(scores)
        assert result.verdict == "delete"
        assert "violence" in result.reasons
        assert "sexual_violence" in result.reasons

    def test_scores_preserved_in_result(self):
        scores = ModerationScores(violence=0.65, sexual_violence=0.0, nsfw=0.0, deepfake_suspect=0.0)
        result = decide(scores)
        assert result.scores.violence == pytest.approx(0.65)
        assert result.verdict == "delete"

    def test_cyberbullying_at_threshold(self):
        # Default cyberbullying threshold is 0.65
        scores = ModerationScores(
            violence=0.0, sexual_violence=0.0, nsfw=0.0, deepfake_suspect=0.0, cyberbullying=0.65
        )
        result = decide(scores)
        assert result.verdict == "delete"
        assert "cyberbullying" in result.reasons

    def test_cyberbullying_below_threshold_flags(self):
        # 0.4 is below the delete threshold (0.65) but above the flag threshold
        scores = ModerationScores(
            violence=0.0, sexual_violence=0.0, nsfw=0.0, deepfake_suspect=0.0, cyberbullying=0.4
        )
        result = decide(scores)
        assert result.verdict == "flag"
        assert "elevated_cyberbullying" in result.reasons


class TestDecideBackwardCompatibility:
    """Ensure old callers that omit cyberbullying still work (default = 0.0)."""

    def test_cyberbullying_defaults_to_zero(self):
        scores = ModerationScores(violence=0.0, sexual_violence=0.0, nsfw=0.0, deepfake_suspect=0.0)
        assert scores.cyberbullying == pytest.approx(0.0)

    def test_result_language_defaults_to_none(self):
        scores = ModerationScores()
        result = decide(scores)
        assert result.language is None


class TestDecideOptInCategories:
    """Opt-in categories (advertising etc.) only count when enabled, and their
    thresholds come from the skill markdown files (single source of truth)."""

    @pytest.fixture()
    def enable_advertising(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "enabled_categories", ["advertising"])

    def test_extra_score_ignored_when_disabled(self):
        # Default: no categories enabled → a high advertising score is ignored
        scores = ModerationScores(extra={"advertising": 0.99})
        result = decide(scores)
        assert result.verdict == "allow"
        assert result.reasons == []

    def test_extra_score_deletes_when_enabled(self, enable_advertising):
        from moderation.registry import ModerationRegistry

        threshold = ModerationRegistry.get("advertising").threshold()
        scores = ModerationScores(extra={"advertising": threshold})
        result = decide(scores)
        assert result.verdict == "delete"
        assert "advertising" in result.reasons

    def test_extra_score_flags_below_threshold(self, enable_advertising):
        # 0.5 is above the flag threshold (0.4) but below the delete threshold (0.85)
        scores = ModerationScores(extra={"advertising": 0.5})
        result = decide(scores)
        assert result.verdict == "flag"
        assert "elevated_advertising" in result.reasons

    def test_core_categories_still_evaluated_alongside_opt_in(self, enable_advertising):
        scores = ModerationScores(cyberbullying=0.65, extra={"advertising": 0.99})
        result = decide(scores)
        assert result.verdict == "delete"
        assert "cyberbullying" in result.reasons
        assert "advertising" in result.reasons
