"""Tests for known-NCII-hash matching (known_content.py) and its wiring into
the moderation routes."""
from __future__ import annotations

import base64
import io
import random
from unittest.mock import patch

from PIL import Image


def _b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _pattern_image(seed: int, size: int = 64) -> Image.Image:
    """A deterministic noisy image — unlike a flat colour swatch, its
    perceptual hash actually varies with content (a solid colour always
    collapses to the same phash regardless of *which* colour)."""
    rng = random.Random(seed)
    pixels = [
        (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
        for _ in range(size * size)
    ]
    img = Image.new("RGB", (size, size))
    img.putdata(pixels)
    return img


class TestComputePhash:
    def test_deterministic_for_identical_images(self):
        from known_content import compute_phash

        img = Image.new("RGB", (64, 64), color=(255, 0, 0))
        assert compute_phash(img) == compute_phash(img.copy())

    def test_differs_for_very_different_images(self):
        from known_content import compute_phash, hamming_distance

        img_a = _pattern_image(1)
        img_b = _pattern_image(2)
        assert hamming_distance(compute_phash(img_a), compute_phash(img_b)) > 0


class TestHammingDistance:
    def test_zero_for_identical_hash(self):
        from known_content import compute_phash, hamming_distance

        img = Image.new("RGB", (32, 32), color=(10, 20, 30))
        h = compute_phash(img)
        assert hamming_distance(h, h) == 0


class TestSubmitAndDeleteProtectedImage:
    def test_submit_returns_id(self, client, small_image_b64):
        resp = client.post(
            "/protected_images",
            json={"image_base64": small_image_b64, "user_id": "victim-1", "platform": "telegram"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["id"], int)
        assert body["hash_type"] == "phash"

    def test_submit_missing_image_rejected(self, client):
        resp = client.post(
            "/protected_images", json={"user_id": "victim-1", "platform": "telegram"}
        )
        assert resp.status_code == 400

    def test_delete_by_submitter_succeeds(self, client, small_image_b64):
        submit = client.post(
            "/protected_images",
            json={"image_base64": small_image_b64, "user_id": "victim-2", "platform": "telegram"},
        )
        protected_id = submit.json()["id"]

        resp = client.request(
            "DELETE",
            f"/protected_images/{protected_id}",
            json={"user_id": "victim-2", "platform": "telegram"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_by_non_submitter_returns_404(self, client, small_image_b64):
        submit = client.post(
            "/protected_images",
            json={"image_base64": small_image_b64, "user_id": "victim-3", "platform": "telegram"},
        )
        protected_id = submit.json()["id"]

        resp = client.request(
            "DELETE",
            f"/protected_images/{protected_id}",
            json={"user_id": "someone-else", "platform": "telegram"},
        )
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.request(
            "DELETE",
            "/protected_images/999999",
            json={"user_id": "nobody", "platform": "telegram"},
        )
        assert resp.status_code == 404


class TestKnownHashMatchingDisabledByDefault:
    def test_matching_image_allowed_when_feature_off(self, client, small_image_b64):
        """KNOWN_IMAGE_HASH_MATCHING defaults to False — registering an image
        as protected must not affect moderation until explicitly enabled."""
        client.post(
            "/protected_images",
            json={"image_base64": small_image_b64, "user_id": "victim-4", "platform": "telegram"},
        )
        resp = client.post("/moderate_image", json={"image_base64": small_image_b64})
        assert resp.status_code == 200
        assert "known_ncii_match" not in resp.json()["reasons"]


class TestKnownHashMatchingEnabled:
    def test_matching_image_forces_delete(self, client):
        import config as config_module

        # Unique pattern per test to stay isolated from other tests' rows in
        # the shared test DB (the client fixture doesn't reset it per-test).
        protected_b64 = _b64(_pattern_image(1001))
        client.post(
            "/protected_images",
            json={"image_base64": protected_b64, "user_id": "victim-5", "platform": "telegram"},
        )

        config_module.settings.known_image_hash_matching = True
        try:
            resp = client.post("/moderate_image", json={"image_base64": protected_b64})
        finally:
            config_module.settings.known_image_hash_matching = False

        assert resp.status_code == 200
        body = resp.json()
        assert body["verdict"] == "delete"
        assert "known_ncii_match" in body["reasons"]

    def test_non_matching_image_not_affected(self, client):
        import config as config_module

        # Protect one noise pattern, then moderate an unrelated one — their
        # perceptual hashes should be far apart (verified empirically: both
        # differ from each other, and from any flat-colour hash used
        # elsewhere in this suite, by a wide margin above the match threshold).
        protected_b64 = _b64(_pattern_image(2002))
        unrelated_b64 = _b64(_pattern_image(3003))
        client.post(
            "/protected_images",
            json={"image_base64": protected_b64, "user_id": "victim-6", "platform": "telegram"},
        )

        config_module.settings.known_image_hash_matching = True
        try:
            resp = client.post("/moderate_image", json={"image_base64": unrelated_b64})
        finally:
            config_module.settings.known_image_hash_matching = False

        assert resp.status_code == 200
        assert "known_ncii_match" not in resp.json()["reasons"]

    def test_matching_video_frame_forces_delete(self, client):
        """A single matching frame among several is enough to force delete."""
        import config as config_module

        protected_img = _pattern_image(4004)
        protected_b64 = _b64(protected_img)
        client.post(
            "/protected_images",
            json={"image_base64": protected_b64, "user_id": "victim-7", "platform": "telegram"},
        )

        safe_frame = Image.new("RGB", (10, 10), color=(0, 200, 0))
        frames = [safe_frame, protected_img]

        config_module.settings.known_image_hash_matching = True
        try:
            with (
                patch("video_processing.extract_frames", return_value=frames),
                patch(
                    "video_processing.moderate_video_frames",
                    return_value={
                        "violence": 0.0, "sexual_violence": 0.0, "nsfw": 0.0, "deepfake_suspect": 0.0,
                    },
                ),
            ):
                resp = client.post("/moderate_video", json={"video_base64": "dGVzdA=="})
        finally:
            config_module.settings.known_image_hash_matching = False

        assert resp.status_code == 200
        body = resp.json()
        assert body["verdict"] == "delete"
        assert "known_ncii_match" in body["reasons"]
