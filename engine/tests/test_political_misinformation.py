"""Tests for the political-misinformation moderation skill."""

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
    return ModerationRegistry.get("political_misinformation")


class TestPoliticalMisinformationSkill:
    def test_skill_exists_and_is_opt_in(self, skill):
        assert skill is not None
        assert skill.core is False
        assert "text" in skill.modalities

    @pytest.mark.parametrize(
        "text",
        [
            "Wake up sheeple, do your own research!",
            "The election was stolen, stop the steal",
            "5G spreads covid and the vaccine contains a microchip",
            "It was a false flag by the deep state",
        ],
    )
    def test_english_hoax_framing_triggers(self, skill, text):
        assert skill.score_text(text, "en") > 0.0

    @pytest.mark.parametrize(
        "text",
        [
            "Lügenpresse! Macht die Augen auf",
            "Die Wahl wurde gefälscht, Wahlbetrug",
        ],
    )
    def test_german_hoax_framing_triggers(self, skill, text):
        assert skill.score_text(text, "de") > 0.0

    def test_benign_political_discussion_scores_zero(self, skill):
        # Ordinary political talk should not match the conservative patterns
        text = "I think the new transport policy will help reduce traffic downtown."
        assert skill.score_text(text, "en") == pytest.approx(0.0)

    def test_flag_leaning_thresholds(self, skill):
        # Delete threshold should be high so most matches flag rather than delete
        assert skill.thresholds["default"] >= 0.8
        assert skill.flag_threshold <= 0.4

    def test_score_is_bounded(self, skill):
        score = skill.score_text("wake up sheeple the election was stolen plandemic", "en")
        assert 0.0 <= score <= 1.0
