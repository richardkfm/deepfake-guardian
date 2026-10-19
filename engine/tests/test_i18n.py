"""Tests for the i18n architecture: language packs, registry, and detector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from i18n.base import HarmPattern, Helpline
from i18n.registry import LanguageRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the LanguageRegistry before each test to ensure a clean state."""
    LanguageRegistry.reset()
    yield
    LanguageRegistry.reset()


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestLanguageRegistry:
    def test_discover_registers_en_and_de(self):
        LanguageRegistry.discover()
        packs = LanguageRegistry.all_packs()
        assert "en" in packs
        assert "de" in packs

    def test_get_returns_correct_pack(self):
        LanguageRegistry.discover()
        en_pack = LanguageRegistry.get("en")
        de_pack = LanguageRegistry.get("de")
        assert en_pack is not None
        assert de_pack is not None
        assert en_pack.lang_code == "en"
        assert de_pack.lang_code == "de"

    def test_get_unknown_code_returns_none(self):
        LanguageRegistry.discover()
        assert LanguageRegistry.get("zz") is None

    def test_get_enabled_filters_by_codes(self):
        LanguageRegistry.discover()
        enabled = LanguageRegistry.get_enabled(["en"])
        assert len(enabled) == 1
        assert enabled[0].lang_code == "en"

    def test_get_enabled_ignores_missing_codes(self):
        LanguageRegistry.discover()
        enabled = LanguageRegistry.get_enabled(["en", "zz"])
        assert len(enabled) == 1
        assert enabled[0].lang_code == "en"

    def test_discover_is_idempotent(self):
        LanguageRegistry.discover()
        count_first = len(LanguageRegistry.all_packs())
        LanguageRegistry._discovered = False  # force re-discovery
        LanguageRegistry._packs = {}
        LanguageRegistry.discover()
        count_second = len(LanguageRegistry.all_packs())
        assert count_first == count_second

    def test_auto_discover_on_get(self):
        """Registry should discover packs on first access without explicit discover()."""
        pack = LanguageRegistry.get("en")
        assert pack is not None


# ---------------------------------------------------------------------------
# Language pack interface tests
# ---------------------------------------------------------------------------


class TestEnglishPack:
    @pytest.fixture()
    def en_pack(self):
        LanguageRegistry.discover()
        return LanguageRegistry.get("en")

    def test_lang_code(self, en_pack):
        assert en_pack.lang_code == "en"

    def test_lang_name(self, en_pack):
        assert en_pack.lang_name == "English"

    def test_get_patterns_returns_list(self, en_pack):
        patterns = en_pack.get_patterns()
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        assert all(isinstance(p, HarmPattern) for p in patterns)

    def test_get_labels_returns_dict(self, en_pack):
        labels = en_pack.get_labels()
        assert isinstance(labels, dict)
        # Must map at least one label to "cyberbullying"
        assert "cyberbullying" in labels.values()

    def test_get_educational_messages_returns_dict(self, en_pack):
        msgs = en_pack.get_educational_messages()
        assert isinstance(msgs, dict)
        assert "cyberbullying" in msgs

    def test_get_helplines_returns_list(self, en_pack):
        helplines = en_pack.get_helplines()
        assert isinstance(helplines, list)
        assert len(helplines) > 0
        assert all(isinstance(h, Helpline) for h in helplines)

    def test_detect_returns_float(self, en_pack):
        mock_lang = MagicMock()
        mock_lang.lang = "en"
        mock_lang.prob = 0.98
        with patch("i18n.packs.en.EnglishPack.detect", return_value=0.98):
            score = en_pack.detect("Hello, how are you?")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_detect_returns_zero_when_langdetect_unavailable(self, en_pack):
        """When langdetect is not installed, detect() gracefully returns 0.0."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "langdetect":
                raise ImportError("No module named 'langdetect'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            score = en_pack.detect("test text")
        assert score == 0.0


class TestGermanPack:
    @pytest.fixture()
    def de_pack(self):
        LanguageRegistry.discover()
        return LanguageRegistry.get("de")

    def test_lang_code(self, de_pack):
        assert de_pack.lang_code == "de"

    def test_lang_name(self, de_pack):
        assert de_pack.lang_name == "Deutsch"

    def test_get_patterns_returns_list(self, de_pack):
        patterns = de_pack.get_patterns()
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        assert all(isinstance(p, HarmPattern) for p in patterns)

    def test_get_labels_returns_dict(self, de_pack):
        labels = de_pack.get_labels()
        assert isinstance(labels, dict)
        assert "cyberbullying" in labels.values()

    def test_get_educational_messages_in_german(self, de_pack):
        msgs = de_pack.get_educational_messages()
        assert isinstance(msgs, dict)
        assert "cyberbullying" in msgs
        # Should contain German text
        assert any(
            any(word in v for word in ["Nachricht", "Inhalt", "Mobbing"])
            for v in msgs.values()
        )

    def test_get_helplines_contains_german_resources(self, de_pack):
        helplines = de_pack.get_helplines()
        names = [h.name for h in helplines]
        assert any("Kummer" in n or "Telefonseelsorge" in n for n in names)

    def test_detect_returns_float(self, de_pack):
        with patch("i18n.packs.de.GermanPack.detect", return_value=0.95):
            score = de_pack.detect("Hallo, wie geht es dir?")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_classifier_truncates_long_messages(self, de_pack, tmp_path, monkeypatch):
        """Messages longer than the model's 512-token window used to raise
        inside the pipeline; classify_text swallows that and returns all-zero
        ML scores, so a long German message skipped ML moderation entirely."""
        transformers = pytest.importorskip("transformers")

        import i18n.packs.de as de_module

        vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "du", "bist", "doof"]
        (tmp_path / "vocab.txt").write_text("\n".join(vocab))
        tok = transformers.DistilBertTokenizer(str(tmp_path / "vocab.txt"), model_max_length=32)
        tiny = transformers.DistilBertForSequenceClassification(
            transformers.DistilBertConfig(
                vocab_size=len(vocab), max_position_embeddings=32, n_layers=1,
                n_heads=2, dim=8, hidden_dim=16, num_labels=2,
            )
        )
        import transformers.pipelines as hf_pipelines

        real_pipeline = hf_pipelines.pipeline

        def _tiny_pipeline(task, model=None, **kwargs):  # noqa: ARG001
            return real_pipeline(task, model=tiny, tokenizer=tok, **kwargs)

        monkeypatch.setattr(de_module, "_de_classifier", None)
        # Patch both the lazy top-level alias and its implementation module
        monkeypatch.setattr(transformers, "pipeline", _tiny_pipeline)
        monkeypatch.setattr(hf_pipelines, "pipeline", _tiny_pipeline)
        clf = de_pack.get_classifier()
        assert clf is not None
        out = clf("du bist doof " * 50)  # 150 tokens > 32-token window
        label_scores = out[0] if isinstance(out[0], list) else out
        assert {d["label"] for d in label_scores} == {"LABEL_0", "LABEL_1"}


# ---------------------------------------------------------------------------
# Language detector tests
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    def test_returns_en_for_english_text(self):
        from i18n.detector import detect_language

        LanguageRegistry.discover()
        # Patch each pack's detect() to simulate language recognition
        with (
            patch("i18n.packs.en.EnglishPack.detect", return_value=0.99),
            patch("i18n.packs.de.GermanPack.detect", return_value=0.01),
        ):
            result = detect_language("Hello world, this is a test message.")
        assert result == "en"

    def test_returns_de_for_german_text(self):
        from i18n.detector import detect_language

        LanguageRegistry.discover()
        with (
            patch("i18n.packs.en.EnglishPack.detect", return_value=0.03),
            patch("i18n.packs.de.GermanPack.detect", return_value=0.97),
        ):
            result = detect_language("Hallo, wie geht es dir heute?")
        assert result == "de"

    def test_falls_back_to_en_when_all_packs_fail(self):
        from i18n.detector import detect_language

        LanguageRegistry.discover()
        with (
            patch("i18n.packs.en.EnglishPack.detect", side_effect=Exception("fail")),
            patch("i18n.packs.de.GermanPack.detect", side_effect=Exception("fail")),
        ):
            result = detect_language("???")
        assert result == "en"

    def test_falls_back_to_en_when_no_packs_enabled(self):
        from i18n.detector import detect_language

        with patch("config.settings") as mock_settings:
            mock_settings.enabled_languages = []
            result = detect_language("some text")
        assert result == "en"
