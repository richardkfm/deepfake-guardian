"""Tests for the deepfake detection factory."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from deepfake.factory import StubDetector, build_provider, get_detector, reset_detector


@pytest.fixture(autouse=True)
def _reset():
    """Reset the cached detector between tests."""
    reset_detector()
    yield
    reset_detector()


class TestStubDetector:
    def test_returns_005_per_face(self):
        from PIL import Image

        det = StubDetector()
        faces = [Image.new("RGB", (10, 10))] * 3
        scores = det.detect(faces)
        assert scores == [0.05, 0.05, 0.05]

    def test_is_available(self):
        assert StubDetector().is_available() is True


class TestFactory:
    def test_stub_provider(self):
        with patch("config.settings") as mock_settings:
            mock_settings.deepfake_provider = "stub"
            det = get_detector()
        assert isinstance(det, StubDetector)
        assert det.name == "stub"

    def test_unknown_provider_falls_back_to_stub(self):
        with patch("config.settings") as mock_settings:
            mock_settings.deepfake_provider = "nonexistent"
            det = get_detector()
        assert isinstance(det, StubDetector)

    def test_openai_provider_without_key_falls_back_to_stub(self):
        with patch("config.settings") as mock_settings:
            mock_settings.deepfake_provider = "openai"
            mock_settings.openai_api_key = ""
            mock_settings.openai_model = "gpt-4o"
            mock_settings.openai_api_base = "https://api.openai.com/v1"
            det = get_detector()
        assert isinstance(det, StubDetector)

    def test_ollama_provider_without_url_falls_back_to_stub(self):
        with patch("config.settings") as mock_settings:
            mock_settings.deepfake_provider = "ollama"
            mock_settings.ollama_base_url = ""
            mock_settings.ollama_model = "llava"
            det = get_detector()
        assert isinstance(det, StubDetector)

    def test_openai_provider_with_key(self):
        from deepfake.cloud_openai import OpenAIDetector

        with patch("config.settings") as mock_settings:
            mock_settings.deepfake_provider = "openai"
            mock_settings.openai_api_key = "sk-test"
            mock_settings.openai_model = "gpt-4o"
            mock_settings.openai_api_base = "https://api.openai.com/v1"
            det = get_detector()
        assert isinstance(det, OpenAIDetector)

    def test_ollama_provider_with_url(self):
        from deepfake.cloud_ollama import OllamaDetector

        with patch("config.settings") as mock_settings:
            mock_settings.deepfake_provider = "ollama"
            mock_settings.ollama_base_url = "http://localhost:11434"
            mock_settings.ollama_model = "llava"
            det = get_detector()
        assert isinstance(det, OllamaDetector)

    def test_unavailable_provider_falls_back_to_stub(self):
        """When is_available() returns False, factory falls back to stub."""
        with patch("config.settings") as mock_settings:
            mock_settings.deepfake_provider = "sightengine"
            mock_settings.sightengine_api_user = ""
            mock_settings.sightengine_api_secret = ""
            det = get_detector()
        assert isinstance(det, StubDetector)

    def test_detector_is_cached(self):
        with patch("config.settings") as mock_settings:
            mock_settings.deepfake_provider = "stub"
            det1 = get_detector()
            det2 = get_detector()
        assert det1 is det2


class TestBuildProvider:
    def test_stub(self):
        assert isinstance(build_provider("stub"), StubDetector)

    def test_openai_prompt_override(self):
        with patch("config.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.openai_model = "gpt-4o"
            mock_settings.openai_api_base = "https://api.openai.com/v1"
            det = build_provider("openai", prompt_override="custom prompt")
        assert det._system_prompt == "custom prompt"

    def test_openai_default_prompt_when_no_override(self):
        from deepfake.cloud_openai import _SYSTEM_PROMPT

        with patch("config.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.openai_model = "gpt-4o"
            mock_settings.openai_api_base = "https://api.openai.com/v1"
            det = build_provider("openai")
        assert det._system_prompt == _SYSTEM_PROMPT

    def test_ollama_prompt_override(self):
        with patch("config.settings") as mock_settings:
            mock_settings.ollama_base_url = "http://localhost:11434"
            mock_settings.ollama_model = "llava"
            det = build_provider("ollama", prompt_override="custom prompt")
        assert det._prompt == "custom prompt"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError):
            build_provider("does_not_exist")

    def test_custom_without_provider_class_raises(self):
        with pytest.raises(ValueError):
            build_provider("custom", provider_class=None)

    def test_custom_with_unimportable_class_raises(self):
        with pytest.raises(ValueError):
            build_provider("custom", provider_class="not.a.real.module.Path")

    def test_custom_with_non_detector_class_raises(self):
        with pytest.raises(ValueError):
            build_provider("custom", provider_class="builtins.str")

    def test_custom_with_valid_detector_class(self):
        det = build_provider("custom", provider_class="deepfake.factory.StubDetector")
        assert isinstance(det, StubDetector)
