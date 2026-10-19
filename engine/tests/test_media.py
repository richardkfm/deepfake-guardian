"""Tests for hardened media decoding (media.py) and its wiring into the routes."""
from __future__ import annotations

import base64
import io
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from media import (
    MAX_IMAGE_SIDE,
    MediaDecodeError,
    decode_base64,
    decode_image_bytes,
    load_image_frames,
    to_rgb,
)


def _encode(img: Image.Image, fmt: str = "PNG", **kwargs) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def _animated_gif(colours: list[tuple[int, int, int]]) -> bytes:
    frames = [Image.new("RGB", (32, 32), c) for c in colours]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100)
    return buf.getvalue()


class TestDecodeBase64:
    def test_plain(self):
        assert decode_base64(base64.b64encode(b"abc").decode()) == b"abc"

    def test_data_uri_prefix_tolerated(self):
        payload = "data:image/png;base64," + base64.b64encode(b"abc").decode()
        assert decode_base64(payload) == b"abc"

    def test_invalid_base64_raises_decode_error(self):
        with pytest.raises(MediaDecodeError):
            decode_base64("abc")  # incorrect padding

    def test_empty_payload_raises_decode_error(self):
        with pytest.raises(MediaDecodeError):
            decode_base64("====")


class TestDecodeImageBytes:
    def test_not_an_image(self):
        with pytest.raises(MediaDecodeError):
            decode_image_bytes(b"definitely not an image")

    def test_decode_error_is_a_value_error(self):
        """Callers that already catch ValueError keep working."""
        assert issubclass(MediaDecodeError, ValueError)

    def test_truncated_jpeg_still_decodes(self):
        """A clipped file still renders (partially) in chat clients, so it
        must be analysed rather than rejected (rejection = skipped moderation)."""
        img = Image.effect_noise((256, 256), 64).convert("RGB")
        data = _encode(img, "JPEG", quality=90)
        result = decode_image_bytes(data[: len(data) * 2 // 3])
        assert result.size == (256, 256)
        assert result.mode == "RGB"

    def test_exif_orientation_applied(self):
        """Orientation=6 means 'rotate 90° CW to display' — the decoded image
        must be the upright one (portrait), not the stored landscape pixels."""
        stored = Image.new("RGB", (40, 20), (10, 120, 200))
        exif = Image.Exif()
        exif[0x0112] = 6
        result = decode_image_bytes(_encode(stored, "JPEG", exif=exif))
        assert result.size == (20, 40)

    def test_16_bit_greyscale_not_clipped_to_white(self):
        """convert('RGB') clips I;16 — a 16-bit PNG would look blank to every model."""
        ramp = np.tile(np.linspace(0, 65535, 64, dtype=np.uint16), (64, 1))
        img = Image.fromarray(ramp)
        assert img.mode.startswith("I;16")
        result = decode_image_bytes(_encode(img))
        arr = np.asarray(result)
        assert arr.min() < 10
        assert arr.max() > 245
        assert 100 < arr.mean() < 155

    def test_float_image_rescaled(self):
        img = Image.fromarray(np.full((8, 8), 0.5, dtype=np.float32))
        result = to_rgb(img)
        assert result.mode == "RGB"
        assert 120 <= result.getpixel((0, 0))[0] <= 135

    @pytest.mark.parametrize("mode", ["RGBA", "LA", "P", "L", "1", "CMYK"])
    def test_any_common_mode_becomes_rgb(self, mode):
        fmt = "JPEG" if mode == "CMYK" else "PNG"
        result = decode_image_bytes(_encode(Image.new(mode, (8, 8)), fmt))
        assert result.mode == "RGB"

    def test_huge_image_downscaled(self):
        img = Image.new("RGB", (MAX_IMAGE_SIDE * 2, 64), (1, 2, 3))
        result = decode_image_bytes(_encode(img))
        assert max(result.size) == MAX_IMAGE_SIDE

    def test_decompression_bomb_rejected(self, monkeypatch):
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
        data = _encode(Image.new("RGB", (100, 100)))  # 10k px > 2 x 1000
        with pytest.raises(MediaDecodeError):
            decode_image_bytes(data)


class TestAnimatedImages:
    def test_still_image_single_frame(self):
        frames = load_image_frames(_encode(Image.new("RGB", (8, 8))), max_frames=10)
        assert len(frames) == 1

    def test_all_frames_returned_when_within_budget(self):
        data = _animated_gif([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
        frames = load_image_frames(data, max_frames=10)
        assert [f.getpixel((0, 0)) for f in frames] == [(255, 0, 0), (0, 255, 0), (0, 0, 255)]

    def test_frames_spread_over_long_animation(self):
        colours = [(i * 8, 0, 255 - i * 8) for i in range(30)]
        frames = load_image_frames(_animated_gif(colours), max_frames=3)
        assert len(frames) == 3
        reds = [f.getpixel((0, 0))[0] for f in frames]
        # Not just the first three frames: the last sample is from the end.
        assert reds[-1] > 150

    def test_max_frames_one_returns_first_frame(self):
        data = _animated_gif([(255, 0, 0), (0, 255, 0)])
        frames = load_image_frames(data, max_frames=1)
        assert len(frames) == 1
        assert frames[0].getpixel((0, 0)) == (255, 0, 0)


class TestRoutesRejectBadImages:
    def test_corrupt_image_returns_400_not_500(self, client):
        payload = base64.b64encode(b"not an image at all").decode()
        resp = client.post("/moderate_image", json={"image_base64": payload})
        assert resp.status_code == 400

    def test_invalid_base64_returns_400(self, client):
        resp = client.post("/moderate_image", json={"image_base64": "abc"})
        assert resp.status_code == 400

    def test_data_uri_image_accepted(self, client, small_image_b64):
        resp = client.post(
            "/moderate_image", json={"image_base64": "data:image/png;base64," + small_image_b64}
        )
        assert resp.status_code == 200

    def test_animated_gif_later_frame_is_analysed(self, client):
        """An innocuous first frame must not hide an explicit later frame."""
        data = _animated_gif([(0, 0, 255), (0, 0, 255), (255, 0, 0)])

        def _fake_classify(image):
            nsfw = 0.95 if image.getpixel((0, 0))[0] > 200 else 0.01
            return {"violence": 0.0, "sexual_violence": nsfw * 0.5, "nsfw": nsfw}

        with patch("classifiers.classify_image", side_effect=_fake_classify):
            resp = client.post(
                "/moderate_image", json={"image_base64": base64.b64encode(data).decode()}
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["scores"]["nsfw"] == pytest.approx(0.95)
        assert body["verdict"] == "delete"

    def test_url_with_undecodable_body_returns_400(self, client):
        async def _fake_fetch(url, timeout):
            return b"<html>not an image</html>"

        with patch("routes.fetch_media_url", side_effect=_fake_fetch):
            resp = client.post("/moderate_image", json={"image_url": "https://example.test/a.png"})
        assert resp.status_code == 400

    def test_url_image_decoded_from_fetched_bytes(self, client, small_image_b64):
        raw = base64.b64decode(small_image_b64)

        async def _fake_fetch(url, timeout):
            return raw

        with patch("routes.fetch_media_url", side_effect=_fake_fetch):
            resp = client.post("/moderate_image", json={"image_url": "https://example.test/a.png"})
        assert resp.status_code == 200

    def test_decode_image_never_fetches_urls(self):
        """URLs must go through the SSRF-checked routes.fetch_media_url."""
        from classifiers import decode_image

        with patch("httpx.get") as mock_get, patch("httpx.stream") as mock_stream:
            with pytest.raises(MediaDecodeError):
                decode_image(None, "http://169.254.169.254/latest/meta-data")
        mock_get.assert_not_called()
        mock_stream.assert_not_called()


class TestVideoDecodeErrors:
    def test_invalid_base64_video_returns_400(self, client):
        resp = client.post("/moderate_video", json={"video_base64": "abc"})
        assert resp.status_code == 400

    def test_decode_video_never_fetches_urls(self):
        from video_processing import decode_video

        with patch("httpx.get") as mock_get, patch("httpx.stream") as mock_stream:
            with pytest.raises(ValueError):
                decode_video(None, "http://127.0.0.1:11434/v.mp4")
        mock_get.assert_not_called()
        mock_stream.assert_not_called()
