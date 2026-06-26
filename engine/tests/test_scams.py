"""Tests for the scams / phishing moderation skill."""

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
    return ModerationRegistry.get("scams")


class TestScamsSkill:
    def test_skill_exists_and_is_opt_in(self, skill):
        assert skill is not None
        assert skill.core is False

    @pytest.mark.parametrize(
        "text",
        [
            "Congratulations you won! Pay a small fee to claim your prize",
            "Your account has been suspended, click here to verify your password",
            "Send me your wallet seed phrase to validate your wallet",
            "Pay with gift cards to receive your reward",
            "We are the official Amazon support team, confirm your login",
        ],
    )
    def test_english_scam_triggers(self, skill, text):
        assert skill.score_text(text, "en") > 0.0

    @pytest.mark.parametrize(
        "text",
        [
            "Sie haben gewonnen! Zahlen Sie eine Gebühr um den Gewinn zu erhalten",
            "Ihr Konto wurde gesperrt, bestätigen Sie ihr Passwort",
        ],
    )
    def test_german_scam_triggers(self, skill, text):
        assert skill.score_text(text, "de") > 0.0

    def test_benign_text_scores_zero(self, skill):
        assert skill.score_text("can you send me the meeting notes?", "en") == pytest.approx(0.0)

    def test_score_is_bounded(self, skill):
        text = "you won! verify your account, send gift cards and your seed phrase"
        assert 0.0 <= skill.score_text(text, "en") <= 1.0
