"""Tests for the moderation-skill registry and its discovery of the shipped skills."""

from __future__ import annotations

import pytest

from moderation.registry import ModerationRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    ModerationRegistry.reset()
    yield
    ModerationRegistry.reset()


class TestDiscovery:
    def test_discovers_core_and_opt_in_skills(self):
        ModerationRegistry.discover()
        ids = {s.category_id for s in ModerationRegistry.all_skills()}
        # Core child-safety categories
        assert {"violence", "sexual_violence", "nsfw", "deepfake_suspect", "cyberbullying"} <= ids
        # Opt-in categories
        assert {"advertising", "political_misinformation"} <= ids

    def test_core_skills_are_marked_core(self):
        core_ids = {s.category_id for s in ModerationRegistry.core_skills()}
        assert "cyberbullying" in core_ids
        assert "advertising" not in core_ids

    def test_opt_in_skills_are_not_core(self):
        opt_in_ids = {s.category_id for s in ModerationRegistry.opt_in_skills()}
        assert opt_in_ids == {
            "advertising",
            "scams",
            "political_misinformation",
            "hate_speech",
            "self_harm",
        }

    def test_auto_discovers_on_first_access(self):
        # No explicit discover() call
        assert ModerationRegistry.get("advertising") is not None

    def test_get_unknown_returns_none(self):
        assert ModerationRegistry.get("does_not_exist") is None


class TestActiveOptIn:
    def test_empty_enabled_list_yields_nothing(self):
        assert ModerationRegistry.active_opt_in([]) == []

    def test_filters_by_enabled_ids(self):
        active = ModerationRegistry.active_opt_in(["advertising"])
        assert [s.category_id for s in active] == ["advertising"]

    def test_ignores_unknown_and_core_ids(self):
        # "cyberbullying" is core, "zzz" is unknown — neither should appear
        active = ModerationRegistry.active_opt_in(["cyberbullying", "zzz", "advertising"])
        assert [s.category_id for s in active] == ["advertising"]


class TestScoreTextCategories:
    def test_disabled_by_default(self):
        result = ModerationRegistry.score_text_categories(
            "buy now! use code SAVE50", "en", []
        )
        assert result == {}

    def test_advertising_detected_when_enabled(self):
        result = ModerationRegistry.score_text_categories(
            "buy now! use code SAVE50", "en", ["advertising"]
        )
        assert result["advertising"] > 0.0

    def test_benign_text_scores_zero(self):
        result = ModerationRegistry.score_text_categories(
            "Let's meet at the library tomorrow.", "en", ["advertising"]
        )
        assert result["advertising"] == pytest.approx(0.0)

    def test_structural_link_spam_detected(self):
        text = "look http://a.com http://b.com http://c.com"
        result = ModerationRegistry.score_text_categories(text, "en", ["advertising"])
        assert result["advertising"] > 0.0


class TestAggregationHelpers:
    def test_labels_for_language_matches_legacy_en(self):
        labels = ModerationRegistry.labels_for_language("en")
        assert labels["violence"] == "violence"
        assert labels["hate speech"] == "nsfw"
        assert labels["harassment"] == "cyberbullying"

    def test_patterns_for_language_non_empty(self):
        assert len(ModerationRegistry.patterns_for_language("en")) > 0
        assert len(ModerationRegistry.patterns_for_language("de")) > 0

    def test_messages_for_language_has_core_categories(self):
        msgs = ModerationRegistry.messages_for_language("en")
        assert "cyberbullying" in msgs
        assert "violence" in msgs
