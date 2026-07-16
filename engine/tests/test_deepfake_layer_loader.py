"""Tests for the deepfake-layer markdown loader."""

from __future__ import annotations

import pytest

from deepfake.layer_loader import load_layer


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


class TestLoadLayer:
    def test_parses_frontmatter(self, tmp_path):
        path = _write(
            tmp_path,
            "demo.md",
            """---
layer_id: demo
display_name: Demo Layer
provider: openai
enabled: true
weight: 2.5
order: 42
---

## Description
A demo layer.
""",
        )
        layer = load_layer(path)
        assert layer.layer_id == "demo"
        assert layer.display_name == "Demo Layer"
        assert layer.provider == "openai"
        assert layer.enabled is True
        assert layer.weight == pytest.approx(2.5)
        assert layer.order == 42
        assert layer.description == "A demo layer."

    def test_defaults_when_omitted(self, tmp_path):
        path = _write(
            tmp_path,
            "demo.md",
            """---
layer_id: demo
provider: stub
---
""",
        )
        layer = load_layer(path)
        assert layer.display_name == "demo"
        assert layer.enabled is False
        assert layer.weight == pytest.approx(1.0)
        assert layer.order == 1000
        assert layer.provider_class is None
        assert layer.prompt is None

    def test_parses_prompt_section(self, tmp_path):
        path = _write(
            tmp_path,
            "demo.md",
            """---
layer_id: demo
provider: openai
---

## Prompt
Estimate the probability this face is a deepfake.
""",
        )
        layer = load_layer(path)
        assert layer.prompt == "Estimate the probability this face is a deepfake."

    def test_unknown_header_ignored(self, tmp_path):
        path = _write(
            tmp_path,
            "demo.md",
            """---
layer_id: demo
provider: stub
---

## Something Unrelated
This should not break parsing.

## Description
Real description.
""",
        )
        layer = load_layer(path)
        assert layer.description == "Real description."

    def test_missing_frontmatter_raises(self, tmp_path):
        path = _write(tmp_path, "bad.md", "no frontmatter here")
        with pytest.raises(ValueError):
            load_layer(path)

    def test_unknown_provider_raises(self, tmp_path):
        path = _write(
            tmp_path,
            "bad.md",
            """---
layer_id: demo
provider: not_a_real_provider
---
""",
        )
        with pytest.raises(ValueError):
            load_layer(path)

    def test_custom_without_provider_class_raises(self, tmp_path):
        path = _write(
            tmp_path,
            "bad.md",
            """---
layer_id: demo
provider: custom
---
""",
        )
        with pytest.raises(ValueError):
            load_layer(path)

    def test_custom_with_provider_class_parses(self, tmp_path):
        path = _write(
            tmp_path,
            "demo.md",
            """---
layer_id: demo
provider: custom
provider_class: mypackage.mymodule.MyDetector
---
""",
        )
        layer = load_layer(path)
        assert layer.provider == "custom"
        assert layer.provider_class == "mypackage.mymodule.MyDetector"
