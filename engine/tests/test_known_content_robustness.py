"""Robustness tests for known-NCII-hash matching (known_content.py):
low-information images, crops / borders / mirroring, legacy rows, threshold
clamping, EXIF orientation."""
from __future__ import annotations

import asyncio
import base64
import io
import random
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFilter


def _b64(img: Image.Image, fmt: str = "PNG", **save_kwargs) -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **save_kwargs)
    return base64.b64encode(buf.getvalue()).decode()


def _structured_image(seed: int, w: int = 400, h: int = 300) -> Image.Image:
    """A smooth, photo-like synthetic image (blurred shapes).

    Pure per-pixel noise has no stable low-frequency structure, so it is a
    poor stand-in for a photo when testing crop / border robustness.
    """
    rng = random.Random(seed)
    img = Image.new("RGB", (w, h), tuple(rng.randint(0, 255) for _ in range(3)))
    draw = ImageDraw.Draw(img)
    for _ in range(25):
        x0, y0 = rng.randint(0, w), rng.randint(0, h)
        x1, y1 = x0 + rng.randint(20, 150), y0 + rng.randint(20, 150)
        colour = tuple(rng.randint(0, 255) for _ in range(3))
        if rng.random() < 0.5:
            draw.ellipse((x0, y0, x1, y1), fill=colour)
        else:
            draw.rectangle((x0, y0, x1, y1), fill=colour)
    return img.filter(ImageFilter.GaussianBlur(2))


def _row(row_id: int, hash_hex: str, hash_type: str) -> SimpleNamespace:
    return SimpleNamespace(id=row_id, hash_hex=hash_hex, hash_type=hash_type)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Just enough of AsyncSession for find_match_any's single SELECT."""

    def __init__(self, rows):
        self.rows = rows
        self.queries = 0

    async def execute(self, _stmt):
        self.queries += 1
        return _FakeResult(self.rows)


def _match(rows, images, threshold=10, robust=False):
    from known_content import find_match_any

    session = _FakeSession(rows)
    match = asyncio.run(find_match_any(session, images, threshold, robust=robust))
    return match, session


def _protected_row(image: Image.Image, row_id: int = 1) -> SimpleNamespace:
    from known_content import HASH_TYPE_SET, compute_protected_hash_set

    return _row(row_id, compute_protected_hash_set(image), HASH_TYPE_SET)


def _centre_crop(img: Image.Image, keep: float) -> Image.Image:
    w, h = img.size
    cw, ch = int(w * keep), int(h * keep)
    left, top = (w - cw) // 2, (h - ch) // 2
    return img.crop((left, top, left + cw, top + ch))


class TestLowInformationImages:
    def test_flat_image_is_low_information(self):
        from known_content import is_low_information

        assert is_low_information(Image.new("RGB", (100, 100), (30, 30, 30)))
        assert is_low_information(Image.new("RGB", (1, 1), (200, 0, 0)))
        assert not is_low_information(_structured_image(1))

    def test_registering_flat_image_rejected(self, client, small_image_b64):
        """A flat image's phash (8000000000000000) would match every blank
        image and every black video frame — refuse it at registration."""
        resp = client.post(
            "/protected_images",
            json={"image_base64": small_image_b64, "user_id": "victim-x", "platform": "telegram"},
        )
        assert resp.status_code == 400

    def test_registering_corrupt_image_rejected(self, client):
        resp = client.post(
            "/protected_images",
            json={"image_base64": "bm90IGFuIGltYWdl", "user_id": "v", "platform": "telegram"},
        )
        assert resp.status_code == 400

    def test_registering_private_url_refused_without_fetching(self, client):
        """POST /protected_images uses the SSRF-checked fetch_media_url too."""
        from unittest.mock import patch

        with patch("httpx.get", side_effect=AssertionError("unguarded fetch")) as mock_get:
            resp = client.post(
                "/protected_images",
                json={
                    "image_url": "http://169.254.169.254/latest/meta-data",
                    "user_id": "v",
                    "platform": "telegram",
                },
            )
        assert resp.status_code == 400
        mock_get.assert_not_called()

    def test_registering_via_url_uses_fetched_bytes(self, client):
        from unittest.mock import patch

        raw = base64.b64decode(_b64(_structured_image(17)))

        async def _fake_fetch(url, timeout):
            return raw

        with patch("routes.fetch_media_url", side_effect=_fake_fetch) as mock_fetch:
            resp = client.post(
                "/protected_images",
                json={"image_url": "https://example.test/p.png", "user_id": "v", "platform": "t"},
            )
        assert resp.status_code == 200
        mock_fetch.assert_called_once()

    def test_legacy_degenerate_row_never_matches(self):
        """A flat image registered before the check must not delete blank frames."""
        from known_content import HASH_TYPE_SINGLE

        legacy = _row(1, "8000000000000000", HASH_TYPE_SINGLE)
        blank_frame = Image.new("RGB", (64, 64), (0, 0, 0))
        match, _ = _match([legacy], [blank_frame, _structured_image(2)])
        assert match is None


class TestMatchingRobustness:
    def test_registration_stores_full_and_crop_hashes(self):
        from known_content import CROP_KEEP_RATIOS, compute_phash, compute_protected_hash_set

        img = _structured_image(3)
        hash_set = compute_protected_hash_set(img)
        assert len(hash_set) == 16 * (1 + len(CROP_KEEP_RATIOS))
        assert len(hash_set) <= 64  # fits ProtectedImageHash.hash_hex String(64)
        assert hash_set[:16] == compute_phash(img)  # full image first

    def test_reencoded_and_resized_copy_matches(self):
        img = _structured_image(4)
        buf = io.BytesIO()
        img.resize((200, 150)).save(buf, format="JPEG", quality=40)
        copy = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        match, _ = _match([_protected_row(img)], [copy])
        assert match is not None

    def test_letterboxed_copy_matches_by_default(self):
        """A photo padded with black bars (e.g. turned into a 16:9 video)."""
        img = _structured_image(5)
        padded = Image.new("RGB", (img.width + 300, img.height), (0, 0, 0))
        padded.paste(img, (150, 0))
        match, _ = _match([_protected_row(img)], [padded])
        assert match is not None

    def test_mirrored_copy_needs_robust_matching(self):
        img = _structured_image(6)
        mirrored = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        row = _protected_row(img)
        assert _match([row], [mirrored])[0] is None
        assert _match([row], [mirrored], robust=True)[0] is not None

    def test_heavy_centre_crop_needs_robust_matching(self):
        img = _structured_image(7)
        cropped = _centre_crop(img, 0.7)
        row = _protected_row(img)
        assert _match([row], [cropped])[0] is None
        assert _match([row], [cropped], robust=True)[0] is not None

    def test_unrelated_image_does_not_match_even_when_robust(self):
        row = _protected_row(_structured_image(8))
        assert _match([row], [_structured_image(9)], robust=True)[0] is None

    def test_legacy_single_phash_row_still_matches(self):
        from known_content import HASH_TYPE_SINGLE, compute_phash

        img = _structured_image(10)
        legacy = _row(7, compute_phash(img), HASH_TYPE_SINGLE)
        match, _ = _match([legacy], [img])
        assert match is legacy

    def test_unparseable_row_is_skipped_not_raised(self):
        from known_content import HASH_TYPE_SINGLE

        img = _structured_image(11)
        rows = [_row(1, "not-hex!", HASH_TYPE_SINGLE), _protected_row(img, row_id=2)]
        match, _ = _match(rows, [img])
        assert match is not None and match.id == 2

    def test_closest_row_wins(self):
        img = _structured_image(12)
        near = _protected_row(_centre_crop(img, 0.95), row_id=1)
        exact = _protected_row(img, row_id=2)
        match, _ = _match([near, exact], [img])
        assert match is not None and match.id == 2

    def test_protected_list_loaded_once_for_all_frames(self):
        img = _structured_image(13)
        frames = [_structured_image(20 + i) for i in range(5)] + [img]
        match, session = _match([_protected_row(img)], frames)
        assert match is not None
        assert session.queries == 1

    def test_no_images_no_query(self):
        match, session = _match([_protected_row(_structured_image(16))], [])
        assert match is None
        assert session.queries == 0


class TestThresholdClamp:
    def test_absurd_threshold_clamped(self):
        from known_content import MAX_THRESHOLD, effective_threshold

        assert effective_threshold(64) == MAX_THRESHOLD
        assert effective_threshold(-3) == 0
        assert effective_threshold(10) == 10

    def test_threshold_64_does_not_match_everything(self):
        """KNOWN_IMAGE_HASH_THRESHOLD=64 would otherwise delete every upload."""
        row = _protected_row(_structured_image(14))
        unrelated = [_structured_image(100 + i) for i in range(10)]
        matches = [_match([row], [img], threshold=64)[0] for img in unrelated]
        assert any(m is None for m in matches)


class TestExifOrientation:
    def test_exif_rotated_upload_matches_upright_protected_image(self, client):
        """Phones store photos sideways plus an EXIF Orientation tag; a
        re-share (or the messenger's re-encode) bakes the rotation into the
        pixels. Both forms must hash the same."""
        import config as config_module

        upright = _structured_image(15)
        client.post(
            "/protected_images",
            json={"image_base64": _b64(upright), "user_id": "victim-exif", "platform": "telegram"},
        )

        # Pixels stored rotated, with Orientation=6 ("rotate 90 CW to
        # display") — what a phone camera writes.
        sideways = upright.transpose(Image.Transpose.ROTATE_90)
        exif = Image.Exif()
        exif[0x0112] = 6
        exif_b64 = _b64(sideways, "JPEG", quality=95, exif=exif)

        config_module.settings.known_image_hash_matching = True
        try:
            resp = client.post("/moderate_image", json={"image_base64": exif_b64})
        finally:
            config_module.settings.known_image_hash_matching = False

        assert resp.status_code == 200
        assert "known_ncii_match" in resp.json()["reasons"]
