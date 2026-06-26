"""Tests for the hate_speech / incitement moderation skill."""

from __future__ import annotations

import pytest

from moderation.registry import ModerationRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    ModerationRegistry.reset()
    yield
    ModerationRegistry.reset()


@pytest.fixture()
def skill():
    return ModerationRegistry.get("hate_speech")


class TestHateSpeechSkill:
    def test_skill_exists_and_is_opt_in(self, skill):
        assert skill is not None
        assert skill.core is False

    @pytest.mark.parametrize(
        "text",
        [
            "we should deport all the immigrants",
            "those refugees are vermin",
            "all muslims are terrorists and should be removed",
            "go back to your country, you don't belong here",
        ],
    )
    def test_english_hate_triggers(self, skill, text):
        assert skill.score_text(text, "en") > 0.0

    def test_calls_for_violence_weighted_high(self, skill):
        # Incitement should score high enough to delete under the default profile
        assert skill.score_text("kill all the refugees", "en") >= skill.thresholds["default"]

    @pytest.mark.parametrize(
        "text",
        [
            "wir sollten alle Ausländer abschieben",
            "diese Flüchtlinge sind Ungeziefer",
            "geh zurück nach wo du herkommst",
        ],
    )
    def test_german_hate_triggers(self, skill, text):
        assert skill.score_text(text, "de") > 0.0

    def test_benign_disagreement_scores_zero(self, skill):
        assert skill.score_text(
            "I disagree with the current immigration policy", "en"
        ) == pytest.approx(0.0)

    def test_score_is_bounded(self, skill):
        assert 0.0 <= skill.score_text("kill all immigrants vermin scum", "en") <= 1.0
