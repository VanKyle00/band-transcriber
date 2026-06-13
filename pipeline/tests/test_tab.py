"""Tests for the (dependency-free) tablature logic. Run: python -m pytest pipeline/tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.config import BASS_TUNING, GUITAR_TUNING
from pipeline.tab import _placements, assign_columns, notes_to_tab, render_alphatex, render_tab


def test_placements_open_string():
    # Low E (40) sits only as open fret on the lowest guitar string.
    assert _placements(40, GUITAR_TUNING) == [(0, 0)]


def test_placements_multiple_positions():
    # High E (64) is playable on several strings; lowest fret is open high-E (str 5).
    places = dict(_placements(64, GUITAR_TUNING))
    assert places[5] == 0
    assert min(f for _, f in _placements(64, GUITAR_TUNING)) == 0


def test_assign_prefers_low_fret():
    cols = assign_columns([[40]], GUITAR_TUNING)
    assert cols == [{0: 0}]


def test_assign_chord_uses_distinct_strings():
    # An open low-E + high-E chord should land on two different strings.
    cols = assign_columns([[40, 64]], GUITAR_TUNING)
    assert len(cols[0]) == 2
    assert set(cols[0].keys()) == {0, 5}


def test_unplayable_note_dropped():
    # Pitch below the lowest open string cannot be placed -> dropped, not faked.
    assert _placements(20, GUITAR_TUNING) == []
    assert assign_columns([[20]], GUITAR_TUNING) == [{}]


def test_bass_monophonic_line():
    # E1 A1 D2 on a 4-string bass -> all open strings, frets 0.
    cols = assign_columns([[28], [33], [38]], BASS_TUNING)
    assert cols == [{0: 0}, {1: 0}, {2: 0}]


def test_render_has_one_line_per_string():
    tab = render_tab([{0: 0}], GUITAR_TUNING)
    assert tab.count("\n") == len(GUITAR_TUNING) - 1  # 6 strings -> 5 newlines


def test_notes_to_tab_contains_fret():
    out = notes_to_tab([(0.0, 40), (0.5, 47)], GUITAR_TUNING)
    assert "0" in out and "|" in out


def test_render_alphatex_header_and_single_note():
    # idx 0 is the low-E string -> AlphaTex string 6. Tuning lists high->low,
    # alphaTab octave = midi // 12 (one above scientific).
    tex = render_alphatex([{0: 0}], GUITAR_TUNING)
    assert tex == "\\tuning E5 B4 G4 D4 A3 E3\n:4 0.6"


def test_render_alphatex_string_numbering():
    # Low-E string (idx 0) -> string 6; high-E string (idx 5) -> string 1.
    assert render_alphatex([{0: 3}], GUITAR_TUNING).endswith("3.6")
    assert render_alphatex([{5: 0}], GUITAR_TUNING).endswith("0.1")


def test_render_alphatex_chord():
    # A column with several strings becomes a parenthesised beat, low string first.
    tex = render_alphatex([{0: 0, 1: 2, 2: 2}], GUITAR_TUNING)
    assert "(0.6 2.5 2.4)" in tex


def test_render_alphatex_empty_column_is_rest():
    assert render_alphatex([{}], GUITAR_TUNING).endswith(":4 r")


def test_render_alphatex_inserts_barlines():
    # 5 beats at 4 beats/bar -> exactly one bar separator.
    tex = render_alphatex([{0: 0}] * 5, GUITAR_TUNING)
    assert tex.count(" | ") == 1


def test_render_alphatex_bass_tuning():
    tex = render_alphatex([{0: 0}], BASS_TUNING)
    assert tex == "\\tuning G3 D3 A2 E2\n:4 0.4"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
