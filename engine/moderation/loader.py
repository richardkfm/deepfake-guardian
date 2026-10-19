"""Parser that turns a moderation-skill markdown file into a :class:`ModerationSkill`.

File format (see ``engine/moderation/skills/*.md``)::

    ---
    category_id: advertising
    display_name: Advertising / Spam
    core: false
    modalities: [text]
    thresholds: { minors_strict: 0.7, default: 0.85, permissive: 0.9 }
    flag_threshold: 0.4
    ---

    ## Description
    Free-text description of what this category detects.

    ## Patterns (en)
    - weight: 0.8  `(?i)\\b(buy now|use code)\\b`

    ## Structural patterns
    - weight: 0.5  `(https?://\\S+\\s*){3,}`

    ## Labels (en)
    - "hate speech" -> nsfw

    ## Educational message (en)
    This message looks like advertising.

The parser is intentionally forgiving: unknown sections are ignored and a
malformed pattern line is skipped rather than aborting the whole file.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from i18n.base import HarmPattern
from moderation.skill import ModerationSkill

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_HEADER_RE = re.compile(r"^##\s+(.*?)\s*$")
_LANG_SUFFIX_RE = re.compile(r"^(.*?)\s*\(([a-z]{2})\)\s*$")
_PATTERN_LINE_RE = re.compile(r"^-\s*weight:\s*([0-9.]+)\s+`(.+)`\s*$")
_LABEL_LINE_RE = re.compile(r'^-\s*"(.*?)"\s*->\s*(\w+)\s*$')


def _split_sections(body: str) -> list[tuple[str, str | None, str]]:
    """Split markdown *body* into ``(name, lang, content)`` triples by ``##`` headers."""
    sections: list[tuple[str, str | None, str]] = []
    current_name: str | None = None
    current_lang: str | None = None
    buffer: list[str] = []

    def _flush() -> None:
        if current_name is not None:
            sections.append((current_name, current_lang, "\n".join(buffer).strip()))

    for line in body.splitlines():
        header = _HEADER_RE.match(line)
        if header:
            _flush()
            title = header.group(1)
            lang_match = _LANG_SUFFIX_RE.match(title)
            if lang_match:
                current_name = lang_match.group(1).strip().lower()
                current_lang = lang_match.group(2)
            else:
                current_name = title.strip().lower()
                current_lang = None
            buffer = []
        else:
            buffer.append(line)
    _flush()
    return sections


def _parse_patterns(content: str, category: str) -> list[HarmPattern]:
    patterns: list[HarmPattern] = []
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        m = _PATTERN_LINE_RE.match(line)
        if not m:
            logger.warning("Skipping malformed pattern line: %s", line)
            continue
        try:
            weight = float(m.group(1))
        except ValueError:
            # e.g. "0.8." — skip this line rather than aborting the whole skill
            logger.warning("Skipping pattern line with invalid weight: %s", line)
            continue
        if not 0.0 <= weight <= 1.0:
            # Scores are validated to [0, 1] downstream; an out-of-range weight
            # would turn every matching message into a 500.
            logger.warning("Clamping pattern weight %s to [0, 1]: %s", weight, line)
            weight = min(max(weight, 0.0), 1.0)
        raw = m.group(2)
        try:
            compiled = re.compile(raw)
        except re.error as exc:
            logger.warning("Invalid regex in skill (%s): %s", exc, raw)
            continue
        patterns.append(HarmPattern(pattern=compiled, category=category, weight=weight))
    return patterns


def _parse_labels(content: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        m = _LABEL_LINE_RE.match(line)
        if m:
            labels[m.group(1)] = m.group(2)
    return labels


_TRUE_STRINGS = {"true", "yes", "on", "1"}
_FALSE_STRINGS = {"false", "no", "off", "0"}


def _parse_bool(value: object, field_name: str) -> bool:
    """Parse a frontmatter boolean, accepting quoted strings.

    ``bool("false")`` is ``True``, so a quoted ``core: "false"`` would
    otherwise turn an opt-in category into an always-on one.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in _TRUE_STRINGS:
        return True
    if text in _FALSE_STRINGS:
        return False
    raise ValueError(f"Invalid boolean for {field_name!r}: {value!r}")


def load_skill(path: Path) -> ModerationSkill:
    """Parse a single skill markdown *path* into a :class:`ModerationSkill`."""
    # utf-8-sig: tolerate the BOM some editors (e.g. Windows Notepad) prepend
    text = path.read_text(encoding="utf-8-sig")
    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        raise ValueError(f"Skill file missing YAML frontmatter: {path}")

    meta = yaml.safe_load(fm_match.group(1)) or {}
    body = fm_match.group(2)

    category_id = str(meta["category_id"])
    skill = ModerationSkill(
        category_id=category_id,
        display_name=str(meta.get("display_name", category_id)),
        core=_parse_bool(meta.get("core", True), "core"),
        order=int(meta.get("order", 1000)),
        modalities=list(meta.get("modalities", ["text"])),
        thresholds={k: float(v) for k, v in (meta.get("thresholds") or {}).items()},
        flag_threshold=float(meta.get("flag_threshold", 0.4)),
    )

    for name, lang, content in _split_sections(body):
        if name == "description":
            skill.description = content
        elif name == "patterns":
            parsed = _parse_patterns(content, category_id)
            if lang:
                skill.patterns.setdefault(lang, []).extend(parsed)
            else:  # bare "## Patterns" treated as structural / language-neutral
                skill.structural_patterns.extend(parsed)
        elif name == "structural patterns":
            skill.structural_patterns.extend(_parse_patterns(content, category_id))
        elif name == "labels" and lang:
            skill.labels.setdefault(lang, {}).update(_parse_labels(content))
        elif name == "educational message" and lang:
            skill.messages[lang] = content

    return skill
