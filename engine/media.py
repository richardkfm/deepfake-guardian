"""Hardened media decoding shared by the image, video and known-hash paths.

Everything that turns untrusted request bytes into pixels lives here so the
same defences apply to ``/moderate_image``, ``/moderate_video`` and
``/protected_images``:

* Malformed input (bad base64, not an image, truncated/corrupt file,
  decompression bomb, an unsupported colour mode) raises
  :class:`MediaDecodeError` — a ``ValueError`` the routes turn into a ``400`` —
  instead of an unhandled exception and a ``500`` (which the bots retry).
* Nothing here fetches URLs: ``image_url`` / ``video_url`` go through the
  SSRF-checked, size-capped async ``routes.fetch_media_url``.
* Images are canonicalised before analysis: EXIF orientation is applied
  (a phone photo stored sideways would otherwise defeat face detection and
  make the perceptual hash of a re-encoded copy differ from the original),
  16-bit / 32-bit / float images are rescaled instead of clipping to white,
  and very large images are downscaled.
* Animated GIF / WebP / APNG files expose *all* their frames via
  :func:`load_image_frames`, so harmful content can't hide behind an
  innocuous first frame.

Media is only ever held in memory for the duration of the request — nothing
here persists it (GDPR).
"""
from __future__ import annotations

import base64
import binascii
import io
import logging
import warnings

from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

#: Images larger than this on their longest side are downscaled before
#: analysis. Every classifier resizes to <=512px anyway; the cap only bounds
#: the memory/CPU spent on face detection and hashing for giant uploads while
#: staying large enough to keep the high-frequency detail deepfake detectors
#: look at in a face crop.
MAX_IMAGE_SIDE = 4096

_TRUNCATED_ERRORS = ("truncated", "broken data stream", "image file is truncated")


class MediaDecodeError(ValueError):
    """Raised when request media can't be decoded into something analysable."""


# ---------------------------------------------------------------------------
# Raw bytes
# ---------------------------------------------------------------------------


def decode_base64(data: str) -> bytes:
    """Decode base64 *data*, tolerating a ``data:<mime>;base64,`` URI prefix.

    Raises:
        MediaDecodeError: The payload is not valid base64.
    """
    payload = data.strip()
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]
    try:
        raw = base64.b64decode(payload)
    except (binascii.Error, ValueError) as exc:
        raise MediaDecodeError("Invalid base64 payload") from exc
    if not raw:
        raise MediaDecodeError("Empty media payload")
    return raw


# ---------------------------------------------------------------------------
# Pixel canonicalisation
# ---------------------------------------------------------------------------


def _high_bit_depth_to_l(image: Image.Image) -> Image.Image:
    """Rescale a 16-bit/32-bit/float greyscale image to 8-bit ``L``.

    ``Image.convert("RGB")`` *clips* these modes, so a 16-bit greyscale PNG
    comes out almost entirely white — the classifiers (and the perceptual
    hash) would then see nothing at all.
    """
    import numpy as np

    arr = np.asarray(image, dtype=np.float64)
    if image.mode.startswith("I;16"):
        scaled = arr / 257.0
    else:
        finite = arr[np.isfinite(arr)]
        lo = float(finite.min()) if finite.size else 0.0
        hi = float(finite.max()) if finite.size else 0.0
        if lo >= 0.0 and hi <= 1.0 and image.mode == "F":
            scaled = arr * 255.0
        elif lo >= 0.0 and hi <= 255.0:
            scaled = arr
        else:
            span = hi - lo
            scaled = (arr - lo) * (255.0 / span) if span > 0 else np.zeros_like(arr)
    scaled = np.nan_to_num(scaled, nan=0.0, posinf=255.0, neginf=0.0)
    return Image.fromarray(np.clip(scaled, 0, 255).astype(np.uint8), mode="L")


def to_rgb(image: Image.Image) -> Image.Image:
    """Convert *image* (any PIL mode) to an 8-bit RGB image.

    Raises:
        MediaDecodeError: The mode can't be converted.
    """
    if image.mode == "RGB":
        return image
    try:
        if image.mode in ("I", "F") or image.mode.startswith("I;16"):
            image = _high_bit_depth_to_l(image)
        return image.convert("RGB")
    except (ValueError, OSError) as exc:
        raise MediaDecodeError(f"Unsupported image mode '{image.mode}'") from exc


def limit_size(image: Image.Image, max_side: int = MAX_IMAGE_SIDE) -> Image.Image:
    """Return *image*, or a downscaled copy whose longest side is <= *max_side*."""
    if max(image.size) <= max_side:
        return image
    out = image.copy()
    out.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    logger.debug("Downscaled image from %s to %s", image.size, out.size)
    return out


def canonicalize(image: Image.Image) -> Image.Image:
    """Apply EXIF orientation, convert to RGB and bound the size."""
    try:
        transposed = ImageOps.exif_transpose(image)
        if transposed is not None:
            image = transposed
    except Exception:  # malformed EXIF must not make the image unanalysable
        logger.debug("Ignoring malformed EXIF orientation data")
    return limit_size(to_rgb(image))


# ---------------------------------------------------------------------------
# Image decoding
# ---------------------------------------------------------------------------


def _open(data: bytes) -> Image.Image:
    """Open and fully load *data*, mapping every decoder failure to MediaDecodeError."""
    try:
        with warnings.catch_warnings():
            # Pillow only *warns* between MAX_IMAGE_PIXELS and 2x that; keep
            # the default limits but make sure the hard error path is mapped.
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            try:
                image.load()
            except OSError as exc:
                if not any(marker in str(exc).lower() for marker in _TRUNCATED_ERRORS):
                    raise
                # A truncated JPEG still renders (partially) in chat clients,
                # so analyse whatever decodes rather than rejecting it — a
                # rejection would let a deliberately clipped file skip moderation.
                logger.info("Image is truncated — analysing the decodable part")
                image = Image.open(io.BytesIO(data))
                previous = ImageFile.LOAD_TRUNCATED_IMAGES
                ImageFile.LOAD_TRUNCATED_IMAGES = True
                try:
                    image.load()
                finally:
                    ImageFile.LOAD_TRUNCATED_IMAGES = previous
    except Image.DecompressionBombError as exc:
        raise MediaDecodeError("Image dimensions exceed the decompression-bomb limit") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise MediaDecodeError("Could not decode image") from exc
    return image


def _frame_indices(n_frames: int, max_frames: int) -> list[int]:
    """Evenly spread up to *max_frames* indices over ``range(n_frames)``."""
    if n_frames <= 0:
        return []
    if max_frames <= 0 or n_frames <= max_frames:
        return list(range(n_frames))
    return sorted({int((i + 0.5) * n_frames / max_frames) for i in range(max_frames)})


def load_image_frames(data: bytes, max_frames: int = 1) -> list[Image.Image]:
    """Decode image bytes into canonical RGB frames.

    For a still image this is a single frame. For an animated GIF/WebP/APNG,
    up to *max_frames* frames spread evenly across the animation are
    returned (the first frame alone is often deliberately innocuous).

    Raises:
        MediaDecodeError: The bytes are not a decodable image.
    """
    image = _open(data)
    n_frames = int(getattr(image, "n_frames", 1) or 1)
    if n_frames <= 1 or max_frames <= 1:
        return [canonicalize(image)]

    frames: list[Image.Image] = []
    for idx in _frame_indices(n_frames, max_frames):
        try:
            image.seek(idx)
            frames.append(canonicalize(image.copy()))
        except (EOFError, OSError, ValueError):
            logger.debug("Could not decode animation frame %d of %d", idx, n_frames)
    if not frames:
        raise MediaDecodeError("Could not decode any animation frame")
    logger.info("Decoded %d of %d animation frame(s)", len(frames), n_frames)
    return frames


def decode_image_bytes(data: bytes) -> Image.Image:
    """Decode image bytes into a single canonical RGB image (first frame)."""
    return load_image_frames(data, max_frames=1)[0]


def read_image_source(image_base64: str | None, image_url: str | None) -> bytes | None:
    """Return the raw bytes of a base64 image request, or ``None`` if none given.

    URLs are deliberately *not* fetched here: a synchronous fetch can't do
    the per-redirect SSRF validation and size cap of the async
    :func:`routes.fetch_media_url`, which every endpoint must use instead.

    Raises:
        MediaDecodeError: Only *image_url* was given.
    """
    if image_base64:
        return decode_base64(image_base64)
    if image_url:
        raise MediaDecodeError(
            "image_url must be fetched with routes.fetch_media_url (SSRF-checked), "
            "then decoded with media.load_image_frames"
        )
    return None
