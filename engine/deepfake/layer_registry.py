"""Deepfake-layer registry with auto-discovery.

On first use the registry loads every ``*.md`` file in
``engine/deepfake/layers/`` into a :class:`~deepfake.layer.DeepfakeLayer`.
Adding or retuning a detection layer = creating or editing one markdown file
in that directory — no Python changes required.

This mirrors :class:`moderation.registry.ModerationRegistry`, but additionally
owns a small cache of instantiated :class:`~deepfake.base.DeepfakeDetector`
objects (one per active layer), since building a provider can be expensive
(HTTP client setup, lazy ONNX session loading).
"""

from __future__ import annotations

import logging
from pathlib import Path

from deepfake.base import DeepfakeDetector
from deepfake.layer import DeepfakeLayer
from deepfake.layer_loader import load_layer

logger = logging.getLogger(__name__)

_LAYERS_DIR = Path(__file__).resolve().parent / "layers"

_GDPR_WARN_PROVIDERS = {"openai", "ollama", "sightengine", "api", "custom"}
_LOOPBACK_PREFIXES = ("http://localhost", "http://127.", "http://0.0.0.0")


class DeepfakeLayerRegistry:
    """Singleton registry mapping layer ids to :class:`DeepfakeLayer` instances."""

    _layers: dict[str, DeepfakeLayer] = {}
    _discovered: bool = False
    _detector_cache: dict[str, DeepfakeDetector] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @classmethod
    def discover(cls) -> None:
        """Load every layer markdown file in the layers directory."""
        cls._layers = {}
        if not _LAYERS_DIR.is_dir():
            logger.warning("Deepfake layers directory not found: %s", _LAYERS_DIR)
            cls._discovered = True
            return

        for path in sorted(_LAYERS_DIR.glob("*.md")):
            try:
                layer = load_layer(path)
            except Exception:
                logger.warning("Failed to load deepfake layer: %s", path.name)
                continue
            if layer.layer_id in cls._layers:
                logger.warning("Duplicate deepfake layer id: %s", layer.layer_id)
                continue
            cls._layers[layer.layer_id] = layer
            logger.info("Deepfake layer registered: %s (provider=%s)", layer.layer_id, layer.provider)

        cls._discovered = True

    @classmethod
    def _ensure_discovered(cls) -> None:
        if not cls._discovered:
            cls.discover()

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, layer_id: str) -> DeepfakeLayer | None:
        cls._ensure_discovered()
        return cls._layers.get(layer_id)

    @classmethod
    def all_layers(cls) -> list[DeepfakeLayer]:
        cls._ensure_discovered()
        return sorted(cls._layers.values(), key=lambda layer: (layer.order, layer.layer_id))

    @classmethod
    def active_layers(cls, enabled_ids: list[str] | None = None) -> list[DeepfakeLayer]:
        """Return the layers that should run.

        ``enabled_ids is None`` — use each manifest's own ``enabled:`` default.
        ``enabled_ids`` a list — the *exact* active set, overriding every
        manifest's default (lets an operator activate a disabled-by-default
        layer, or drop ``stub``, purely via ``DEEPFAKE_LAYERS``).
        """
        if enabled_ids is None:
            return [layer for layer in cls.all_layers() if layer.enabled]
        return [layer for layer in cls.all_layers() if layer.layer_id in enabled_ids]

    # ------------------------------------------------------------------
    # Detector instantiation / caching
    # ------------------------------------------------------------------

    @classmethod
    def get_detector_for(cls, layer: DeepfakeLayer) -> DeepfakeDetector | None:
        """Build (once) and cache a detector for *layer*.

        Returns ``None`` — never raises — if the provider can't be built or
        reports itself unavailable, so callers can simply skip this layer.
        """
        from deepfake.factory import build_provider

        detector = cls._detector_cache.get(layer.layer_id)
        if detector is None:
            try:
                detector = build_provider(
                    layer.provider,
                    prompt_override=layer.prompt,
                    provider_class=layer.provider_class,
                )
            except ValueError:
                logger.warning(
                    "Could not build deepfake layer '%s' (provider=%s)",
                    layer.layer_id,
                    layer.provider,
                )
                return None
            cls._detector_cache[layer.layer_id] = detector
            if layer.provider in _GDPR_WARN_PROVIDERS and detector.is_available():
                cls._maybe_warn_gdpr(layer)

        if not detector.is_available():
            return None
        return detector

    @classmethod
    def _maybe_warn_gdpr(cls, layer: DeepfakeLayer) -> None:
        if layer.provider == "ollama":
            from config import settings

            base_url = getattr(settings, "ollama_base_url", "")
            if base_url.startswith(_LOOPBACK_PREFIXES):
                return
        logger.warning(
            "GDPR notice: deepfake layer '%s' (provider=%s) may send face image "
            "data to a third party — review data flows before enabling for "
            "minors-facing deployments.",
            layer.layer_id,
            layer.provider,
        )

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    @classmethod
    def reset(cls) -> None:
        """Clear the registry and detector cache (used in tests to force re-discovery)."""
        cls._layers = {}
        cls._discovered = False
        cls._detector_cache = {}
