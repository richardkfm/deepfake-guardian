"""Combine per-layer deepfake scores into a single scalar.

Kept as a small, pure, dependency-free module so the combination policy can
be unit-tested in isolation from the registry/provider machinery.
"""

from __future__ import annotations

import logging

from deepfake.layer import DeepfakeLayer

logger = logging.getLogger(__name__)

_STRATEGIES = {"max", "mean", "weighted_mean"}


def combine_scores(
    per_layer_scores: dict[str, float],
    layers: list[DeepfakeLayer],
    strategy: str = "max",
) -> float:
    """Combine one score per active layer into a single deepfake_suspect score.

    Args:
        per_layer_scores: ``{layer_id: score}`` for every layer that produced
            a usable score this call.
        layers: The layers that were active this call (used to look up each
            layer's ``weight`` for the ``weighted_mean`` strategy).
        strategy: ``"max"`` (default, most conservative) | ``"mean"`` |
            ``"weighted_mean"``. An unrecognised strategy falls back to
            ``"max"`` with a warning, rather than raising.

    Returns:
        A float 0.0-1.0. ``0.0`` if *per_layer_scores* is empty.
    """
    if not per_layer_scores:
        return 0.0

    if strategy not in _STRATEGIES:
        logger.warning("Unknown DEEPFAKE_LAYER_COMBINE strategy '%s' — falling back to max", strategy)
        strategy = "max"

    scores = list(per_layer_scores.values())

    if strategy == "max":
        return max(scores)

    if strategy == "mean":
        return sum(scores) / len(scores)

    # weighted_mean
    weight_by_id = {layer.layer_id: layer.weight for layer in layers}
    total_weight = 0.0
    weighted_sum = 0.0
    for layer_id, score in per_layer_scores.items():
        weight = weight_by_id.get(layer_id, 1.0)
        total_weight += weight
        weighted_sum += weight * score

    if total_weight <= 0:
        logger.warning("weighted_mean total weight <= 0 — falling back to max")
        return max(scores)

    return weighted_sum / total_weight
