"""Tests for the (dependency-light) post-processing core. Run: python -m pytest pipeline/tests"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.postprocess import Grid, Note, _fold_tempo


def test_fold_tempo_in_range_unchanged():
    assert _fold_tempo(120.0) == 120.0


def test_fold_tempo_doubles_slow():
    assert _fold_tempo(50.0) == 100.0


def test_fold_tempo_halves_fast():
    assert _fold_tempo(200.0) == 100.0


def test_fold_tempo_rejects_nonpositive():
    with pytest.raises(ValueError):
        _fold_tempo(0.0)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok  {name}")
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {name}: {exc}")
    print("done")
