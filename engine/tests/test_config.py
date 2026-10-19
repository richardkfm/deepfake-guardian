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
