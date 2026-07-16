"""Tests for the deepfake-layer registry and its discovery of the shipped layers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import deepfake.layer_registry as layer_registry_module
from deepfake.factory import StubDetector
from deepfake.layer_registry import DeepfakeLayerRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    DeepfakeLayerRegistry.reset()
    yield
    DeepfakeLayerRegistry.reset()


class TestDiscovery:
    def test_discovers_shipped_layers(self):
        DeepfakeLayerRegistry.discover()
        ids = {layer.layer_id for layer in DeepfakeLayerRegistry.all_layers()}
        assert ids == {"stub", "openai", "ollama", "local", "sightengine", "api"}

    def test_all_layers_sorted_by_order_then_id(self):
        layers = DeepfakeLayerRegistry.all_layers()
        orders = [layer.order for layer in layers]
        assert orders == sorted(orders)

    def test_auto_discovers_on_first_access(self):
        assert DeepfakeLayerRegistry.get("stub") is not None

    def test_get_unknown_returns_none(self):
        assert DeepfakeLayerRegistry.get("does_not_exist") is None

    def test_only_stub_enabled_by_default(self):
        DeepfakeLayerRegistry.discover()
        default_active = {layer.layer_id for layer in DeepfakeLayerRegistry.active_layers(None)}
        assert default_active == {"stub"}


class TestActiveLayers:
    def test_empty_list_yields_nothing(self):
        assert DeepfakeLayerRegistry.active_layers([]) == []

    def test_unknown_id_yields_nothing(self):
        assert DeepfakeLayerRegistry.active_layers(["does_not_exist"]) == []

    def test_explicit_list_overrides_manifest_default(self):
        # "openai" ships enabled: false, but an explicit list activates it anyway.
        active = DeepfakeLayerRegistry.active_layers(["openai"])
        assert [layer.layer_id for layer in active] == ["openai"]

    def test_explicit_list_can_exclude_default_enabled_layer(self):
        # "stub" ships enabled: true, but omitting it from an explicit list drops it.
        active = DeepfakeLayerRegistry.active_layers(["openai"])
        assert "stub" not in [layer.layer_id for layer in active]


class TestDiscoveryRobustness:
    def _use_tmp_layers_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(layer_registry_module, "_LAYERS_DIR", tmp_path)

    def test_duplicate_layer_id_is_skipped(self, monkeypatch, tmp_path):
        self._use_tmp_layers_dir(monkeypatch, tmp_path)
        (tmp_path / "a.md").write_text(
            "---\nlayer_id: dup\nprovider: stub\n---\n", encoding="utf-8"
        )
        (tmp_path / "b.md").write_text(
            "---\nlayer_id: dup\nprovider: stub\n---\n", encoding="utf-8"
        )
        DeepfakeLayerRegistry.discover()
        assert len(DeepfakeLayerRegistry.all_layers()) == 1

    def test_malformed_file_is_skipped_others_still_load(self, monkeypatch, tmp_path):
        self._use_tmp_layers_dir(monkeypatch, tmp_path)
        (tmp_path / "good.md").write_text(
            "---\nlayer_id: good\nprovider: stub\n---\n", encoding="utf-8"
        )
        (tmp_path / "bad.md").write_text("no frontmatter here", encoding="utf-8")
        DeepfakeLayerRegistry.discover()
        ids = {layer.layer_id for layer in DeepfakeLayerRegistry.all_layers()}
        assert ids == {"good"}

    def test_missing_directory_does_not_crash(self, monkeypatch, tmp_path):
        self._use_tmp_layers_dir(monkeypatch, tmp_path / "does_not_exist")
        DeepfakeLayerRegistry.discover()
        assert DeepfakeLayerRegistry.all_layers() == []


class TestGetDetectorFor:
    def test_caches_instance(self):
        layer = DeepfakeLayerRegistry.get("stub")
        det1 = DeepfakeLayerRegistry.get_detector_for(layer)
        det2 = DeepfakeLayerRegistry.get_detector_for(layer)
        assert det1 is det2
        assert isinstance(det1, StubDetector)

    def test_reset_clears_cache(self):
        layer = DeepfakeLayerRegistry.get("stub")
        det1 = DeepfakeLayerRegistry.get_detector_for(layer)
        DeepfakeLayerRegistry.reset()
        layer = DeepfakeLayerRegistry.get("stub")
        det2 = DeepfakeLayerRegistry.get_detector_for(layer)
        assert det1 is not det2

    def test_unavailable_provider_returns_none(self):
        with patch("config.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            mock_settings.openai_model = "gpt-4o"
            mock_settings.openai_api_base = "https://api.openai.com/v1"
            layer = DeepfakeLayerRegistry.get("openai")
            result = DeepfakeLayerRegistry.get_detector_for(layer)
        assert result is None

    def test_bad_custom_provider_class_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(layer_registry_module, "_LAYERS_DIR", tmp_path)
        (tmp_path / "bad_custom.md").write_text(
            "---\nlayer_id: bad_custom\nprovider: custom\n"
            "provider_class: not.a.real.module.Path\n---\n",
            encoding="utf-8",
        )
        DeepfakeLayerRegistry.discover()
        layer = DeepfakeLayerRegistry.get("bad_custom")
        assert DeepfakeLayerRegistry.get_detector_for(layer) is None

    def test_gdpr_warning_logged_for_third_party_layer(self, caplog):
        import logging

        with patch("config.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.openai_model = "gpt-4o"
            mock_settings.openai_api_base = "https://api.openai.com/v1"
            layer = DeepfakeLayerRegistry.get("openai")
            with caplog.at_level(logging.WARNING):
                DeepfakeLayerRegistry.get_detector_for(layer)
        assert any("GDPR notice" in record.message for record in caplog.records)

    def test_no_gdpr_warning_for_stub(self, caplog):
        import logging

        layer = DeepfakeLayerRegistry.get("stub")
        with caplog.at_level(logging.WARNING):
            DeepfakeLayerRegistry.get_detector_for(layer)
        assert not any("GDPR notice" in record.message for record in caplog.records)
