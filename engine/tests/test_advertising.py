"""Tests for the advertising/spam moderation skill."""

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
    return ModerationRegistry.get("advertising")


class TestAdvertisingSkill:
    def test_skill_exists_and_is_opt_in(self, skill):
        assert skill is not None
        assert skill.core is False
        assert "text" in skill.modalities

    @pytest.mark.parametrize(
        "text",
        [
            "Buy now and use code SAVE50!",
            "Limited offer, click the link in bio",
            "DM me for prices",
            "50% off, free shipping today only",
        ],
    )
    def test_english_promo_triggers(self, skill, text):
        assert skill.score_text(text, "en") > 0.0

    @pytest.mark.parametrize(
        "text",
        [
            "Jetzt kaufen mit Rabattcode!",
            "Nur heute gratis Versand",
        ],
    )
    def test_german_promo_triggers(self, skill, text):
        assert skill.score_text(text, "de") > 0.0

    def test_benign_text_scores_zero(self, skill):
        assert skill.score_text("See you at practice on Tuesday", "en") == pytest.approx(0.0)

    def test_score_is_bounded(self, skill):
        score = skill.score_text("buy now use code SAVE50 limited offer click the link", "en")
        assert 0.0 <= score <= 1.0
