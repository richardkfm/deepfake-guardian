"""Tests for classifiers._scores_from_multilabel output-shape handling."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from classifiers import _scores_from_multilabel

_LABEL_MAP = {"toxic": "cyberbullying", "obscene": "nsfw", "non_toxic": "safe"}


def test_flat_output():
    clf = MagicMock(return_value=[{"label": "toxic", "score": 0.7}, {"label": "non_toxic", "score": 0.3}])
    scores = _scores_from_multilabel(clf, "text", _LABEL_MAP)
    assert scores["cyberbullying"] == pytest.approx(0.7)


def test_nested_output_from_top_k_none_pipeline():
    """top_k=None pipelines return [[{label, score}, ...]] for a single string;
    this used to raise TypeError and silently zero the ML contribution."""
    clf = MagicMock(
        return_value=[[{"label": "toxic", "score": 0.8}, {"label": "obscene", "score": 0.6}]]
    )
    scores = _scores_from_multilabel(clf, "text", _LABEL_MAP)
    assert scores["cyberbullying"] == pytest.approx(0.8)
    assert scores["nsfw"] == pytest.approx(0.6)


def test_empty_output():
    clf = MagicMock(return_value=[])
    scores = _scores_from_multilabel(clf, "text", _LABEL_MAP)
    assert scores["cyberbullying"] == 0.0
