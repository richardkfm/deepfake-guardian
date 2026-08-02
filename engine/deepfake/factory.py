"""Factory for creating deepfake detector provider instances.

:func:`build_provider` is the reusable instantiation helper — it knows how to
construct any built-in provider (or a ``custom`` one from a dotted import
path) and is used both by the legacy single-provider :func:`get_detector`
below and by :class:`deepfake.layer_registry.DeepfakeLayerRegistry` for the
multi-layer mechanism.
"""
from __future__ import annotations

import importlib
import inspect
import logging

from PIL import Image

from deepfake.base import BASELINE_SCORE, DeepfakeDetector

logger = logging.getLogger(__name__)

_detector: DeepfakeDetector | None = None


class DeepfakeProviderUnavailable(RuntimeError):
    """Raised when the configured provider is unusable and fallback is forbidden.

    Only raised with ``DEEPFAKE_REQUIRE_PROVIDER=true`` — see
    :func:`get_detector`.
    """


class StubDetector(DeepfakeDetector):
    """Returns a fixed low score — for CI/testing or when no real provider is available."""

    name = "stub"

    def detect(self, face_images: list[Image.Image]) -> list[float]:
        return [BASELINE_SCORE] * len(face_images)

    def is_available(self) -> bool:
        return True


def _build_custom(provider_class: str | None, prompt_override: str | None) -> DeepfakeDetector:
    if not provider_class:
        raise ValueError("provider: custom requires a provider_class dotted import path")

    module_name, _, class_name = provider_class.rpartition(".")
    if not module_name:
        raise ValueError(f"Invalid provider_class '{provider_class}' — expected 'module.ClassName'")

    try:
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
    except (ImportError, AttributeError) as exc:
        raise ValueError(f"Could not import provider_class '{provider_class}': {exc}") from exc

    if not (isinstance(cls, type) and issubclass(cls, DeepfakeDetector)):
        raise ValueError(f"provider_class '{provider_class}' is not a DeepfakeDetector subclass")

    kwargs = {}
    if prompt_override is not None and "prompt" in inspect.signature(cls.__init__).parameters:
        kwargs["prompt"] = prompt_override

    return cls(**kwargs)


def build_provider(
    provider_key: str,
    *,
    prompt_override: str | None = None,
    provider_class: str | None = None,
) -> DeepfakeDetector:
    """Instantiate one :class:`DeepfakeDetector` for *provider_key*.

    Args:
        provider_key: One of ``openai|ollama|local|sightengine|api|stub|custom``.
        prompt_override: For ``openai``/``ollama`` (and ``custom`` classes that
            accept a ``prompt`` kwarg), overrides the provider's built-in
            detection prompt. Ignored for providers with no prompt concept.
        provider_class: Dotted import path to a :class:`DeepfakeDetector`
            subclass. Required (and only used) when ``provider_key == "custom"``.

    Raises:
        ValueError: Unknown *provider_key*, or an unresolvable/invalid
            ``custom`` provider class.
    """
    if provider_key == "openai":
        from deepfake.cloud_openai import OpenAIDetector

        return OpenAIDetector(prompt=prompt_override)
    if provider_key == "ollama":
        from deepfake.cloud_ollama import OllamaDetector

        return OllamaDetector(prompt=prompt_override)
    if provider_key == "local":
        from deepfake.local_detector import LocalOnnxDetector

        return LocalOnnxDetector()
    if provider_key == "sightengine":
        from deepfake.cloud_sightengine import SightEngineDetector

        return SightEngineDetector()
    if provider_key == "api":
        from deepfake.cloud_generic import GenericApiDetector

        return GenericApiDetector()
    if provider_key == "stub":
        return StubDetector()
    if provider_key == "custom":
        return _build_custom(provider_class, prompt_override)

    raise ValueError(f"Unknown provider '{provider_key}'")


def get_detector() -> DeepfakeDetector:
    """Return the configured deepfake detector (cached singleton).

    Reads ``DEEPFAKE_PROVIDER`` from :mod:`config` settings. Falls back to
    :class:`StubDetector` with a warning if the chosen provider is unavailable
    — which means deepfake detection is effectively **off** while the engine
    still looks healthy. Set ``DEEPFAKE_REQUIRE_PROVIDER=true`` to raise
    :class:`DeepfakeProviderUnavailable` instead of degrading silently.

    Raises:
        DeepfakeProviderUnavailable: The configured provider is unknown or
            unavailable and ``DEEPFAKE_REQUIRE_PROVIDER`` is set.
    """
    global _detector
    if _detector is not None:
        return _detector

    from config import settings

    provider = getattr(settings, "deepfake_provider", "stub")
    require = getattr(settings, "deepfake_require_provider", False)

    try:
        det: DeepfakeDetector = build_provider(provider)
    except ValueError as exc:
        if require:
            raise DeepfakeProviderUnavailable(
                f"DEEPFAKE_PROVIDER '{provider}' is not a known provider and "
                "DEEPFAKE_REQUIRE_PROVIDER is set."
            ) from exc
        logger.warning("Unknown DEEPFAKE_PROVIDER '%s' — falling back to stub", provider)
        det = StubDetector()

    if not det.is_available():
        if require:
            raise DeepfakeProviderUnavailable(
                f"Deepfake provider '{det.name}' is not available (check credentials "
                "and dependencies) and DEEPFAKE_REQUIRE_PROVIDER is set."
            )
        logger.warning(
            "Deepfake provider '%s' is not available — falling back to stub. "
            "Deepfake detection is now effectively DISABLED (every face scores %.2f). "
            "Check configuration and dependencies, or set DEEPFAKE_REQUIRE_PROVIDER=true "
            "to fail fast instead.",
            det.name,
            BASELINE_SCORE,
        )
        det = StubDetector()

    _detector = det
    logger.info("Deepfake detector initialised: %s", det.name)
    return _detector


def active_detector_status() -> dict[str, object]:
    """Describe the deepfake detection currently in effect, for ``GET /health``.

    Reports the configured provider or layer set alongside what is *actually*
    running, so a deployment that silently fell back to the stub is visible
    without reading logs. Never builds a provider as a side effect — an
    unbuilt detector is reported as ``"not_initialised"``.
    """
    from config import settings

    layers = getattr(settings, "deepfake_layers", [])
    if layers:
        status: dict[str, object] = {
            "mode": "layers",
            "configured": list(layers),
            "combine": getattr(settings, "deepfake_layer_combine", "max"),
        }
        try:
            from deepfake.layer_registry import DeepfakeLayerRegistry

            resolved = [ly.layer_id for ly in DeepfakeLayerRegistry.active_layers(list(layers))]
            status["resolved"] = resolved
            # A configured id that matches no manifest contributes nothing.
            status["degraded"] = not resolved
        except Exception:  # pragma: no cover — /health must never 500
            logger.exception("Could not resolve deepfake layers for health report")
        return status

    configured = getattr(settings, "deepfake_provider", "stub")
    active = _detector.name if _detector is not None else "not_initialised"
    return {
        "mode": "provider",
        "configured": configured,
        "active": active,
        # True only once we know detection is inert: the stub is running while
        # something else was asked for.
        "degraded": _detector is not None and active == "stub" and configured != "stub",
    }


def reset_detector() -> None:
    """Reset the cached detector (useful for testing)."""
    global _detector
    _detector = None
