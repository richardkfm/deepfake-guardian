"""Shared pytest fixtures for the engine test suite."""
from __future__ import annotations

import base64
import io
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

# ---------------------------------------------------------------------------
# Environment setup — must happen before any app modules are imported
# ---------------------------------------------------------------------------
os.environ.setdefault("API_KEY", "")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_guardian.db")
os.environ.setdefault("GDPR_SALT", "test-salt-for-tests")
os.environ.setdefault("DEEPFAKE_LAYERS", "")

_TEST_DB_PATH = "./test_guardian.db"
if os.path.exists(_TEST_DB_PATH):
    os.remove(_TEST_DB_PATH)

# Safe scores returned by the mocked classify_text
_SAFE_TEXT_SCORES = {
    "violence": 0.01,
    "sexual_violence": 0.01,
    "nsfw": 0.01,
    "cyberbullying": 0.01,
    "lang_code": "en",
}


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Clean up the test database file after the test session completes."""
    if os.path.exists(_TEST_DB_PATH):
        os.remove(_TEST_DB_PATH)


@pytest.fixture()
def client():
    """Return a TestClient with ML classifiers mocked out (fast, no GPU needed).

    The TestClient starts the FastAPI lifespan which calls ``init_db()``,
    creating the SQLite test database tables on first use.
    """
    from deepfake.factory import StubDetector

    with (
        patch("classifiers.classify_text", return_value=_SAFE_TEXT_SCORES),
        patch("classifiers._get_image_classifier") as mock_img_clf,
        patch("classifiers._get_violence_classifier", return_value=None),
        patch("deepfake.face_extractor._get_face_detector", return_value=None),
        patch("deepfake.factory.get_detector", return_value=StubDetector()),
    ):
        # Image classifier returns safe NSFW score
        mock_img_clf.return_value = MagicMock(
            return_value=[{"label": "normal", "score": 0.98}, {"label": "nsfw", "score": 0.02}]
        )

        from main import app

        with TestClient(app) as c:
            yield c


@pytest.fixture()
def client_with_key(monkeypatch):
    """Return a TestClient with API_KEY authentication enabled."""
    monkeypatch.setenv("API_KEY", "test-secret-key")

    from deepfake.factory import StubDetector

    with (
        patch("classifiers.classify_text", return_value=_SAFE_TEXT_SCORES),
        patch("classifiers._get_image_classifier") as mock_img_clf,
        patch("classifiers._get_violence_classifier", return_value=None),
        patch("deepfake.face_extractor._get_face_detector", return_value=None),
        patch("deepfake.factory.get_detector", return_value=StubDetector()),
    ):
        mock_img_clf.return_value = MagicMock(
            return_value=[{"label": "normal", "score": 0.98}, {"label": "nsfw", "score": 0.02}]
        )

        # Reload settings so the new env var is picked up
        import config as config_module

        config_module.settings.api_key = "test-secret-key"

        from main import app

        with TestClient(app) as c:
            yield c

        # Restore
        config_module.settings.api_key = ""


@pytest.fixture()
def small_image_b64() -> str:
    """Return a tiny 10×10 red PNG as a base64 string."""
    img = Image.new("RGB", (10, 10), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
