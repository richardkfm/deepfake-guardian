"""Parser that turns a deepfake-layer markdown file into a :class:`DeepfakeLayer`.

File format (see ``engine/deepfake/layers/*.md``)::

    ---
    layer_id: openai
    display_name: OpenAI Vision (GPT-4o)
    provider: openai
    enabled: false
    weight: 1.0
    order: 20
    ---

    ## Description
    Free-text description of this detection layer.

    ## Prompt
    The instruction sent to the vision model, for prompt-driven providers
    (openai / ollama / custom) only.

The parser mirrors :mod:`moderation.loader`'s forgiving philosophy for the
markdown *body*: unknown sections are ignored rather than raising. Frontmatter
problems (missing frontmatter, unknown ``provider``, ``custom`` without a
``provider_class``) do raise, since those describe how to build the detector
and can't be silently guessed at.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from deepfake.layer import DeepfakeLayer

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_HEADER_RE = re.compile(r"^##\s+(.*?)\s*$")

KNOWN_PROVIDERS = {"openai", "ollama", "local", "sightengine", "api", "stub", "custom"}


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Split markdown *body* into ``(name, content)`` pairs by ``##`` headers."""
    sections: list[tuple[str, str]] = []
    current_name: str | None = None
    buffer: list[str] = []

    def _flush() -> None:
        if current_name is not None:
            sections.append((current_name, "\n".join(buffer).strip()))

    for line in body.splitlines():
        header = _HEADER_RE.match(line)
        if header:
            _flush()
            current_name = header.group(1).strip().lower()
            buffer = []
        else:
            buffer.append(line)
    _flush()
    return sections


def load_layer(path: Path) -> DeepfakeLayer:
    """Parse a single layer markdown *path* into a :class:`DeepfakeLayer`."""
    text = path.read_text(encoding="utf-8")
    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        raise ValueError(f"Layer file missing YAML frontmatter: {path}")

    meta = yaml.safe_load(fm_match.group(1)) or {}
    body = fm_match.group(2)

    layer_id = str(meta["layer_id"])
    provider = str(meta.get("provider", ""))
    if provider not in KNOWN_PROVIDERS:
        raise ValueError(
            f"Layer '{layer_id}' has unknown provider '{provider}' "
            f"(expected one of {sorted(KNOWN_PROVIDERS)})"
        )

    provider_class = meta.get("provider_class")
    if provider_class is not None:
        provider_class = str(provider_class)
    if provider == "custom" and not provider_class:
        raise ValueError(f"Layer '{layer_id}' has provider: custom but no provider_class")

    layer = DeepfakeLayer(
        layer_id=layer_id,
        display_name=str(meta.get("display_name", layer_id)),
        provider=provider,
        provider_class=provider_class,
        enabled=bool(meta.get("enabled", False)),
        weight=float(meta.get("weight", 1.0)),
        order=int(meta.get("order", 1000)),
    )

    for name, content in _split_sections(body):
        if name == "description":
            layer.description = content
        elif name == "prompt":
            layer.prompt = content

    return layer
