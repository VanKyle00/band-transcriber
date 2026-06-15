"""Tests for the (dependency-light) post-processing core. Run: python -m pytest pipeline/tests"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.postprocess import Grid, Note, _fold_tempo, quantize_and_clean


def test_fold_tempo_in_range_unchanged():
    assert _fold_tempo(120.0) == 120.0


def test_fold_tempo_doubles_slow():
    assert _fold_tempo(50.0) == 100.0


def test_fold_tempo_halves_fast():
    assert _fold_tempo(200.0) == 100.0


def test_fold_tempo_keeps_lower_bound():
    assert _fold_tempo(60.0) == 60.0


def test_fold_tempo_keeps_upper_bound():
    assert _fold_tempo(180.0) == 180.0


def test_fold_tempo_rejects_nonpositive():
    with pytest.raises(ValueError):
        _fold_tempo(0.0)


def test_quantize_snaps_to_16th_grid():
    grid = Grid(bpm=120.0, beat_offset=0.0)        # slot = (60/120)/4 = 0.125s
    out = quantize_and_clean([Note(0.13, 0.60, 60, 100)], grid, monophonic=False)
    assert out == [Note(0.125, 0.625, 60, 100)]


def test_quantize_drops_spurious_short_notes():
    grid = Grid(bpm=120.0, beat_offset=0.0)        # half-slot = 0.0625s
    notes = [Note(0.0, 0.04, 60, 100),             # 0.04 < 0.0625 -> dropped
             Note(0.0, 0.25, 62, 100)]             # kept
    out = quantize_and_clean(notes, grid, monophonic=False)
    assert [n.pitch for n in out] == [62]


def test_quantize_enforces_minimum_one_slot():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    # 0.46..0.54 both snap to 0.5 -> must be widened to one slot (0.5..0.625)
    out = quantize_and_clean([Note(0.46, 0.54, 60, 100)], grid, monophonic=False)
    assert out == [Note(0.5, 0.625, 60, 100)]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok  {name}")
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {name}: {exc}")
    print("done")
