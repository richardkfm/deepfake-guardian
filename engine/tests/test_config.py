"""Tests for environment-variable parsing in config.Settings."""
from __future__ import annotations

import logging

import pytest


def _fresh_settings():
    from config import Settings

    return Settings()


class TestModerationProfileParsing:
    @pytest.mark.parametrize("raw", ["Minors_Strict", "minors_strict ", " MINORS_STRICT"])
    def test_profile_name_is_case_and_whitespace_insensitive(self, monkeypatch, raw):
        """A stray capital or trailing space in .env must not silently drop a
        minors deployment back to the laxer ``default`` thresholds."""
        monkeypatch.setenv("MODERATION_PROFILE", raw)
        s = _fresh_settings()
        assert s.moderation_profile == "minors_strict"
        assert s.threshold_sexual_violence == pytest.approx(0.3)
        assert s.threshold_nsfw == pytest.approx(0.4)

    def test_unknown_profile_warns_and_uses_default(self, monkeypatch, caplog):
        monkeypatch.setenv("MODERATION_PROFILE", "strict")
        with caplog.at_level(logging.WARNING):
            s = _fresh_settings()
        assert s.moderation_profile == "default"
        assert s.threshold_nsfw == pytest.approx(0.8)
        assert any("strict" in r.getMessage() for r in caplog.records)


class TestThresholdOverrides:
    def test_empty_threshold_override_falls_back_to_profile(self, monkeypatch):
        """``THRESHOLD_VIOLENCE=`` (blank line in .env) used to crash startup
        with ``ValueError: could not convert string to float: ''``."""
        monkeypatch.setenv("MODERATION_PROFILE", "default")
        for var in (
            "THRESHOLD_VIOLENCE",
            "THRESHOLD_SEXUAL_VIOLENCE",
            "THRESHOLD_NSFW",
            "THRESHOLD_DEEPFAKE",
            "THRESHOLD_CYBERBULLYING",
        ):
            monkeypatch.setenv(var, "  ")
        s = _fresh_settings()
        assert s.threshold_violence == pytest.approx(0.5)
        assert s.threshold_nsfw == pytest.approx(0.8)
        assert s.threshold_cyberbullying == pytest.approx(0.65)

    def test_explicit_threshold_override_still_applies(self, monkeypatch):
        monkeypatch.setenv("THRESHOLD_NSFW", "0.55")
        assert _fresh_settings().threshold_nsfw == pytest.approx(0.55)


class TestListParsing:
    def test_enabled_categories_are_normalised(self, monkeypatch):
        """Skill ids are lowercase; ``Advertising`` must not be silently ignored."""
        monkeypatch.setenv("ENABLED_CATEGORIES", " Advertising , SCAMS,,hate_speech ")
        assert _fresh_settings().enabled_categories == ["advertising", "scams", "hate_speech"]

    def test_enabled_languages_are_normalised(self, monkeypatch):
        monkeypatch.setenv("ENABLED_LANGUAGES", "EN, De")
        assert _fresh_settings().enabled_languages == ["en", "de"]

    def test_mixed_case_category_is_actually_scored(self, monkeypatch):
        from moderation.registry import ModerationRegistry

        monkeypatch.setenv("ENABLED_CATEGORIES", "Advertising")
        s = _fresh_settings()
        scores = ModerationRegistry.score_text_categories(
            "Buy now and use code SAVE50!", "en", s.enabled_categories
        )
        assert scores.get("advertising", 0.0) > 0.0
