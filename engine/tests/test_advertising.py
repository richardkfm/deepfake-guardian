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
            # get-rich-quick
            "Make money fast — financial freedom with passive income!",
            # crypto shilling
            "Guaranteed 100x returns on this altcoin presale, invest now",
            # supplements
            "Lose weight fast with these keto gummies, miracle pill",
            # sexual services
            "DM for nudes, onlyfans link in bio",
            # insurance
            "Lower your car insurance premium today",
        ],
    )
    def test_english_spam_triggers(self, skill, text):
        assert skill.score_text(text, "en") > 0.0

    @pytest.mark.parametrize(
        "text",
        [
            "Jetzt kaufen mit Rabattcode!",
            "Schnell reich mit passivem Einkommen",
            "Abnehmen mit diesem Wundermittel",
        ],
    )
    def test_german_spam_triggers(self, skill, text):
        assert skill.score_text(text, "de") > 0.0

    def test_link_spam_structural(self, skill):
        text = "look http://a.com http://b.com http://c.com"
        assert skill.score_text(text, "en") > 0.0

    def test_benign_text_scores_zero(self, skill):
        assert skill.score_text("See you at practice on Tuesday", "en") == pytest.approx(0.0)

    def test_score_is_bounded(self, skill):
        score = skill.score_text("buy now use code SAVE50 crypto 100x onlyfans keto", "en")
        assert 0.0 <= score <= 1.0
