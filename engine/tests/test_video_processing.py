"""Tests for video frame extraction and moderation pipeline."""
from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from video_processing import decode_video, moderate_video_frames


class TestDecodeVideo:
    def test_decode_from_base64(self):
        data = b"fake video content"
        b64 = base64.b64encode(data).decode()
        result = decode_video(b64, None)
        assert result == data

    def test_raises_when_no_input(self):
        with pytest.raises(ValueError, match="Provide video_base64 or video_url"):
            decode_video(None, None)


class TestExtractFrames:
    def test_returns_empty_on_invalid_video(self):
        """Invalid video data should return empty list, not crash."""
        import cv2

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False

        with patch.object(cv2, "VideoCapture", return_value=mock_cap):
            from video_processing import extract_frames
            result = extract_frames(b"not a real video")
        assert result == []

    def test_extracts_frames_at_interval(self):
        """Mocked VideoCapture returns frames at expected intervals."""
        import cv2

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: 25.0,
            cv2.CAP_PROP_FRAME_COUNT: 250,  # 10 seconds
        }.get(prop, 0)

        fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)

        with (
            patch.object(cv2, "VideoCapture", return_value=mock_cap),
            patch.object(cv2, "cvtColor", return_value=fake_frame),
            patch("config.settings") as mock_settings,
        ):
            mock_settings.frame_interval = 2.0
            mock_settings.max_frames = 10
            mock_settings.max_video_duration = 300

            from video_processing import extract_frames
            result = extract_frames(b"fake video data")

        assert len(result) > 0
        assert all(isinstance(f, Image.Image) for f in result)

    def test_respects_max_frames(self):
        """Should not return more than MAX_FRAMES."""
        import cv2

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: 25.0,
            cv2.CAP_PROP_FRAME_COUNT: 2500,  # 100 seconds
        }.get(prop, 0)

        fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, fake_frame)

        with (
            patch.object(cv2, "VideoCapture", return_value=mock_cap),
            patch.object(cv2, "cvtColor", return_value=fake_frame),
            patch("config.settings") as mock_settings,
        ):
            mock_settings.frame_interval = 1.0
            mock_settings.max_frames = 3
            mock_settings.max_video_duration = 300

            from video_processing import extract_frames
            result = extract_frames(b"fake video data")

        assert len(result) <= 3


class TestModerateVideoFrames:
    def test_aggregates_max_scores(self):
        """moderate_video_frames returns max score across all frames."""
        frame1 = Image.new("RGB", (10, 10))
        frame2 = Image.new("RGB", (10, 10))

        scores_calls = [
            {"violence": 0.3, "sexual_violence": 0.1, "nsfw": 0.2},
            {"violence": 0.1, "sexual_violence": 0.5, "nsfw": 0.8},
        ]
        df_calls = [0.1, 0.6]

        with (
            patch("classifiers.classify_image", side_effect=scores_calls),
            patch("classifiers.detect_deepfake_suspect", side_effect=df_calls),
        ):
            result = moderate_video_frames([frame1, frame2])

        assert result["violence"] == pytest.approx(0.3)
        assert result["sexual_violence"] == pytest.approx(0.5)
        assert result["nsfw"] == pytest.approx(0.8)
        assert result["deepfake_suspect"] == pytest.approx(0.6)

    def test_empty_frames_returns_zeros(self):
        result = moderate_video_frames([])
        assert result["violence"] == 0.0
        assert result["deepfake_suspect"] == 0.0

    def test_sexual_violence_escalates_for_sexualised_deepfake_frame(self):
        """A frame with high nsfw + high deepfake score is non-consensual
        intimate imagery ("revenge porn" deepfake) and should escalate the
        sexual_violence score above the plain NSFW heuristic."""
        frame = Image.new("RGB", (10, 10))

        # sexual_violence heuristic (nsfw * 0.5) alone would be 0.45, but the
        # combined deepfake signal (nsfw * deepfake = 0.81) should win out.
        img_scores = {"violence": 0.0, "sexual_violence": 0.45, "nsfw": 0.9}
        df_score = 0.9

        with (
            patch("classifiers.classify_image", return_value=img_scores),
            patch("classifiers.detect_deepfake_suspect", return_value=df_score),
        ):
            result = moderate_video_frames([frame])

        assert result["sexual_violence"] == pytest.approx(0.81)
        assert result["deepfake_suspect"] == pytest.approx(0.9)
