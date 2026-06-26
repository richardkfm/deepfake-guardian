"""Tests for the self-harm / eating-disorder promotion moderation skill."""

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
    return ModerationRegistry.get("self_harm")


class TestSelfHarmSkill:
    def test_skill_exists_and_is_opt_in(self, skill):
        assert skill is not None
        assert skill.core is False

    @pytest.mark.parametrize(
        "text",
        [
            "pro ana thinspo, here are fasting tips to lose weight",
            "you should just kill yourself, nobody would miss you",
            "best way to self-harm and cutting tips",
        ],
    )
    def test_english_promotion_triggers(self, skill, text):
        assert skill.score_text(text, "en") > 0.0

    @pytest.mark.parametrize(
        "text",
        [
            "pro ana magersucht tipps zum hungern",
            "bring dich doch um, niemand vermisst dich",
        ],
    )
    def test_german_promotion_triggers(self, skill, text):
        assert skill.score_text(text, "de") > 0.0

    def test_personal_distress_not_flagged(self, skill):
        # Someone expressing their own distress is NOT a violation — must not match
        assert skill.score_text("I had a rough day and feel really down", "en") == pytest.approx(0.0)

    def test_educational_message_offers_help(self, skill):
        # The message must route to crisis support
        msg = skill.messages.get("en", "")
        assert "findahelpline.com" in msg or "988" in msg

    def test_score_is_bounded(self, skill):
        assert 0.0 <= skill.score_text("thinspo pro ana kill yourself cutting tips", "en") <= 1.0
