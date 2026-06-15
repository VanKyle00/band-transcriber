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


def test_merge_consecutive_same_pitch_keeps_max_velocity():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    notes = [Note(0.0, 0.125, 60, 90), Note(0.125, 0.25, 60, 110)]
    out = quantize_and_clean(notes, grid, monophonic=False)
    assert out == [Note(0.0, 0.25, 60, 110)]


def test_does_not_merge_distant_same_pitch():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    notes = [Note(0.0, 0.125, 60, 100), Note(0.5, 0.625, 60, 100)]
    out = quantize_and_clean(notes, grid, monophonic=False)
    assert len(out) == 2


def test_polyphonic_keeps_overlapping_pitches():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    chord = [Note(0.0, 0.5, 60, 100), Note(0.0, 0.5, 64, 100)]
    out = quantize_and_clean(chord, grid, monophonic=False)
    assert len(out) == 2


def test_monophony_drops_overlap_keeps_longer():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    notes = [Note(0.0, 0.125, 60, 100), Note(0.0, 0.5, 67, 100)]
    out = quantize_and_clean(notes, grid, monophonic=True)
    assert [n.pitch for n in out] == [67]


def test_monophony_truncates_lingering_note():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    # 60 lingers (snaps 0.0..0.375) into 62 (snaps 0.25..0.5) -> 60 truncated to 0.25
    notes = [Note(0.0, 0.36, 60, 100), Note(0.25, 0.5, 62, 100)]
    out = quantize_and_clean(notes, grid, monophonic=True)
    assert out == [Note(0.0, 0.25, 60, 100), Note(0.25, 0.5, 62, 100)]


def test_quantize_empty_input_returns_empty():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    assert quantize_and_clean([], grid, monophonic=False) == []


def test_quantize_respects_nonzero_beat_offset():
    grid = Grid(bpm=120.0, beat_offset=0.5)   # grid lines at 0.5 + k*0.125
    out = quantize_and_clean([Note(0.52, 0.88, 60, 100)], grid, monophonic=False)
    assert out == [Note(0.5, 0.875, 60, 100)]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok  {name}")
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {name}: {exc}")
    print("done")
