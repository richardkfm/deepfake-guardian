"""Tests for the moderation-skill markdown loader."""

from __future__ import annotations

import re

import pytest

from moderation.loader import load_skill


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


class TestLoadSkill:
    def test_parses_frontmatter(self, tmp_path):
        path = _write(
            tmp_path,
            "demo.md",
            """---
category_id: demo
display_name: Demo Category
core: false
order: 42
modalities: [text]
thresholds: { minors_strict: 0.3, default: 0.6, permissive: 0.9 }
flag_threshold: 0.25
---

## Description
A demo category.
""",
        )
        skill = load_skill(path)
        assert skill.category_id == "demo"
        assert skill.display_name == "Demo Category"
        assert skill.core is False
        assert skill.order == 42
        assert skill.modalities == ["text"]
        assert skill.thresholds == {"minors_strict": 0.3, "default": 0.6, "permissive": 0.9}
        assert skill.flag_threshold == pytest.approx(0.25)
        assert skill.description == "A demo category."

    def test_parses_language_patterns_and_structural(self, tmp_path):
        path = _write(
            tmp_path,
            "demo.md",
            """---
category_id: demo
thresholds: { default: 0.5 }
---

## Patterns (en)
- weight: 0.8  `(?i)\\bbuy now\\b`
- weight: 0.6  `(?i)\\bsale\\b`

## Patterns (de)
- weight: 0.7  `(?i)\\bjetzt kaufen\\b`

## Structural patterns
- weight: 0.5  `(https?://\\S+\\s*){3,}`
""",
        )
        skill = load_skill(path)
        assert len(skill.patterns["en"]) == 2
        assert len(skill.patterns["de"]) == 1
        assert len(skill.structural_patterns) == 1
        # Patterns are compiled and tagged with the category id
        en = skill.patterns["en"][0]
        assert en.category == "demo"
        assert isinstance(en.pattern, re.Pattern)
        assert en.pattern.search("BUY NOW please")  # (?i) inline flag works

    def test_parses_labels_and_messages(self, tmp_path):
        path = _write(
            tmp_path,
            "demo.md",
            """---
category_id: demo
thresholds: { default: 0.5 }
---

## Labels (en)
- "hate speech" -> nsfw
- "violence" -> violence

## Educational message (en)
Please be nice.
""",
        )
        skill = load_skill(path)
        assert skill.labels["en"] == {"hate speech": "nsfw", "violence": "violence"}
        assert skill.messages["en"] == "Please be nice."

    def test_malformed_pattern_line_skipped(self, tmp_path):
        path = _write(
            tmp_path,
            "demo.md",
            """---
category_id: demo
thresholds: { default: 0.5 }
---

## Patterns (en)
- weight: 0.8  `(?i)\\bok\\b`
- this line is not a valid pattern
""",
        )
        skill = load_skill(path)
        assert len(skill.patterns["en"]) == 1

    def test_missing_frontmatter_raises(self, tmp_path):
        path = _write(tmp_path, "bad.md", "no frontmatter here")
        with pytest.raises(ValueError):
            load_skill(path)

    def test_score_text_uses_max_weight(self, tmp_path):
        path = _write(
            tmp_path,
            "demo.md",
            """---
category_id: demo
thresholds: { default: 0.5 }
---

## Patterns (en)
- weight: 0.4  `(?i)\\bmild\\b`
- weight: 0.9  `(?i)\\bsevere\\b`
""",
        )
        skill = load_skill(path)
        assert skill.score_text("this is mild", "en") == pytest.approx(0.4)
        assert skill.score_text("this is severe and mild", "en") == pytest.approx(0.9)
        assert skill.score_text("nothing here", "en") == pytest.approx(0.0)
        assert skill.score_text("severe", "fr") == pytest.approx(0.0)  # unknown lang


class TestPatternWeights:
    def test_unparseable_weight_skips_line_not_whole_skill(self, tmp_path):
        """'0.8.' matches the weight regex but isn't a float; it used to raise
        ValueError and drop the entire skill (all its patterns + thresholds)."""
        path = _write(
            tmp_path,
            "demo.md",
            """---
category_id: demo
thresholds: { default: 0.5 }
---

## Patterns (en)
- weight: 0.8.  `(?i)\\btypo\\b`
- weight: 0.6  `(?i)\\bok\\b`
""",
        )
        skill = load_skill(path)
        assert [h.weight for h in skill.patterns["en"]] == [0.6]

    def test_weight_above_one_is_clamped(self, tmp_path):
        """Scores are validated to [0, 1]; a weight of 5 used to produce a 500
        for every message the pattern matched."""
        path = _write(
            tmp_path,
            "demo.md",
            """---
category_id: demo
thresholds: { default: 0.5 }
---

## Patterns (en)
- weight: 5  `(?i)\\bloud\\b`
""",
        )
        skill = load_skill(path)
        assert skill.score_text("loud", "en") == pytest.approx(1.0)

    def test_core_pattern_weight_above_one_yields_valid_scores(self):
        """A core (cyberbullying) pattern with weight > 1 must still produce a
        response-schema-valid score instead of a pydantic ValidationError."""
        from unittest.mock import MagicMock

        from cyberbullying import score_cyberbullying
        from models import ModerationScores
        from moderation.loader import _parse_patterns

        parsed = _parse_patterns("- weight: 1.5  `(?i)\\bzzbully\\b`", "cyberbullying")
        pack = MagicMock(get_patterns=MagicMock(return_value=parsed))
        score = score_cyberbullying("zzbully", pack)
        assert ModerationScores(cyberbullying=score).cyberbullying == pytest.approx(1.0)
