"""Tests for env parsing and the bot message files."""

from __future__ import annotations

import json
import string
from pathlib import Path

import pytest

from config import _float_env
from i18n.loader import available_languages, get_message

_I18N_DIR = Path(__file__).resolve().parent.parent / "i18n"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 5.0), ("", 5.0), ("12.5", 12.5), ("0", 0.0), ("abc", 5.0), ("-3", 5.0)],
)
def test_float_env(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("DG_TEST_FLOAT", raising=False)
    else:
        monkeypatch.setenv("DG_TEST_FLOAT", raw)
    assert _float_env("DG_TEST_FLOAT", 5.0) == expected


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_all_languages_share_keys_and_placeholders():
    en = json.loads((_I18N_DIR / "en.json").read_text(encoding="utf-8"))
    assert {"en", "de"} <= available_languages()
    for lang in available_languages() - {"en"}:
        other = json.loads((_I18N_DIR / f"{lang}.json").read_text(encoding="utf-8"))
        assert other.keys() == en.keys(), lang
        for key, template in en.items():
            assert _placeholders(other[key]) == _placeholders(template), (lang, key)


def test_every_admin_notice_has_no_admins_variant():
    en = json.loads((_I18N_DIR / "en.json").read_text(encoding="utf-8"))
    for key in ("flagged_content", "delete_failed", "warning_admin_notification",
                "warning_supervisor_escalation"):
        assert f"{key}_no_admins" in en


def test_unknown_language_falls_back_to_english():
    assert get_message("my_data_error", "xx").startswith("❌ Could not")
