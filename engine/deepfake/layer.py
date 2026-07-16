"""In-memory representation of a deepfake *detection layer*.

A layer is a single human-editable markdown file in
``engine/deepfake/layers/<layer_id>.md`` describing one detection backend:
which provider it wraps, whether it's active by default, how much weight it
carries when combined with other layers, and — for prompt-driven vision
providers (OpenAI, Ollama) — the actual instruction sent to the model. The
:mod:`~deepfake.layer_loader` parses each markdown file into one of these
objects and the :class:`~deepfake.layer_registry.DeepfakeLayerRegistry`
serves them to the rest of the engine.

This mirrors :class:`moderation.skill.ModerationSkill`, scoped to what
media-detection layers need: no thresholds or regex patterns (those stay in
``moderation/skills/deepfake.md``), just provider selection, activation, and
an optional prompt override.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DeepfakeLayer:
    """Parsed, ready-to-use representation of one deepfake detection layer."""

    layer_id: str
    display_name: str
    provider: str
    provider_class: str | None = None
    enabled: bool = False
    weight: float = 1.0
    order: int = 1000
    description: str = ""
    prompt: str | None = None
