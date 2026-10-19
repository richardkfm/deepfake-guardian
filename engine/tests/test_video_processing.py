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


class TestPlanSampleIndices:
    def test_short_video_keeps_interval_sampling(self):
        """Unchanged behaviour: one frame every FRAME_INTERVAL from the start."""
        from video_processing import plan_sample_indices

        # 10 s at 25 fps, every 2 s -> 0, 50, 100, 150, 200
        assert plan_sample_indices(250, 25.0, 2.0, 10, 300) == [0, 50, 100, 150, 200]

    def test_long_video_spreads_budget_over_whole_duration(self):
        """Previously only the first MAX_FRAMES * FRAME_INTERVAL seconds (20 s)
        were looked at — a harmless intro hid everything after it."""
        from video_processing import plan_sample_indices

        fps = 25.0
        total = int(120 * fps)  # 2 minutes
        indices = plan_sample_indices(total, fps, 2.0, 10, 300)
        assert len(indices) == 10
        assert indices == sorted(indices)
        assert indices[-1] / fps > 100  # the last sample is near the end
        assert indices[0] / fps < 12  # and the first near the start

    def test_duration_cap_respected(self):
        from video_processing import plan_sample_indices

        fps = 25.0
        indices = plan_sample_indices(int(3600 * fps), fps, 2.0, 10, 300)
        assert max(indices) < 300 * fps

    def test_zero_or_unknown_frame_count(self):
        from video_processing import plan_sample_indices

        assert plan_sample_indices(0, 25.0, 2.0, 10, 300) == []

    def test_max_frames_below_one_treated_as_one(self):
        from video_processing import plan_sample_indices

        assert len(plan_sample_indices(1000, 25.0, 2.0, 0, 300)) == 1


def _sequential_cap(n_frames: int, fps: float = 25.0, frame_count: float = 0, raw: bool = False):
    """A VideoCapture mock that only supports front-to-back decoding.

    With *raw*, each retrieved "frame" is a 1x1x1 int64 array holding its
    frame index (for asserting which frames the sampler kept).
    """
    import cv2

    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.get.side_effect = lambda prop: {
        cv2.CAP_PROP_FPS: fps,
        cv2.CAP_PROP_FRAME_COUNT: frame_count,
    }.get(prop, 0)
    state = {"pos": -1}

    def _grab():
        state["pos"] += 1
        return state["pos"] < n_frames

    def _retrieve():
        if raw:
            return True, np.full((1, 1, 1), state["pos"], dtype=np.int64)
        return True, np.zeros((8, 8, 3), dtype=np.uint8)

    cap.grab.side_effect = _grab
    cap.retrieve.side_effect = _retrieve
    cap.read.return_value = (False, None)  # seeking unsupported
    return cap


class TestExtractFramesFallbacks:
    def _run(self, cap, max_frames=10, interval=2.0, duration=300):
        import cv2

        with (
            patch.object(cv2, "VideoCapture", return_value=cap),
            patch("config.settings") as mock_settings,
        ):
            mock_settings.frame_interval = interval
            mock_settings.max_frames = max_frames
            mock_settings.max_video_duration = duration
            from video_processing import extract_frames

            return extract_frames(b"fake video data")

    def test_unknown_frame_count_decoded_sequentially(self):
        """WebM / streamed MP4 often report 0 frames — previously that meant
        zero frames extracted and an unanalysed "allow"."""
        cap = _sequential_cap(n_frames=250, frame_count=0)  # 10 s, count unknown
        frames = self._run(cap)
        assert len(frames) == 5  # one every 2 s
        assert all(isinstance(f, Image.Image) for f in frames)

    def test_failed_seeks_fall_back_to_sequential(self):
        cap = _sequential_cap(n_frames=250, frame_count=250)
        frames = self._run(cap)
        assert len(frames) == 5

    def test_sequential_sampling_bounded(self):
        cap = _sequential_cap(n_frames=25 * 120, frame_count=-1)  # 2 min, unknown length
        frames = self._run(cap, max_frames=4)
        assert 1 <= len(frames) <= 4

    def test_sequential_respects_duration_cap(self):
        cap = _sequential_cap(n_frames=25 * 600, frame_count=0)
        self._run(cap, duration=10)
        # 10 s at 25 fps: never decodes past frame 250 (+1 for the failed grab)
        assert cap.grab.call_count <= 251

    def test_implausible_fps_does_not_break_sampling(self):
        import cv2

        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: float("nan"),
            cv2.CAP_PROP_FRAME_COUNT: 250,
        }.get(prop, 0)
        cap.read.return_value = (True, np.zeros((8, 8, 3), dtype=np.uint8))
        frames = self._run(cap)
        assert len(frames) == 5  # NaN fps -> assume 25

    def test_capture_released_on_success(self):
        cap = _sequential_cap(n_frames=50, frame_count=0)
        self._run(cap)
        assert cap.release.called

    def test_large_frames_downscaled(self):
        import cv2

        from media import MAX_IMAGE_SIDE

        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: 25.0,
            cv2.CAP_PROP_FRAME_COUNT: 1,
        }.get(prop, 0)
        cap.read.return_value = (True, np.zeros((16, MAX_IMAGE_SIDE + 1000, 3), dtype=np.uint8))
        frames = self._run(cap)
        assert max(frames[0].size) == MAX_IMAGE_SIDE


class TestSequentialSampler:
    def test_decimation_keeps_even_spread(self):
        from video_processing import _read_sequentially

        cap = _sequential_cap(n_frames=1000, raw=True)
        with patch("video_processing._to_pil", side_effect=lambda f: int(f[0, 0, 0])):
            kept = _read_sequentially(cap, fps=1.0, frame_interval=1.0, max_frames=5, max_duration=0)
        assert 3 <= len(kept) <= 5
        assert kept[0] == 0
        assert kept[-1] >= 500  # covers the second half, not just the first 5 frames
        steps = {b - a for a, b in zip(kept, kept[1:])}
        assert len(steps) == 1  # evenly spaced
