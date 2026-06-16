"""Tests for the (dependency-light) post-processing core. Run: python -m pytest pipeline/tests"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.postprocess import Grid, Note, _fold_tempo, build_meta, quantize_and_clean


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


def test_apply_to_midi_quantizes_and_sets_tempo(tmp_path):
    pretty_midi = pytest.importorskip("pretty_midi")
    from pipeline.postprocess import apply_to_midi

    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=60, start=0.13, end=0.60))
    pm.instruments.append(inst)
    midi = tmp_path / "t.mid"
    pm.write(str(midi))

    apply_to_midi(midi, Grid(bpm=120.0, beat_offset=0.0), monophonic=False)

    out = pretty_midi.PrettyMIDI(str(midi))
    note = out.instruments[0].notes[0]
    assert abs(note.start - 0.125) < 1e-3
    assert abs(note.end - 0.625) < 1e-3
    _, tempi = out.get_tempo_changes()
    assert abs(float(tempi[0]) - 120.0) < 1e-2


def test_detect_tempo_unpacks_array_tempo(monkeypatch):
    librosa = pytest.importorskip("librosa")
    import numpy as np

    from pipeline.postprocess import detect_tempo

    # beat_track returns tempo as a shape-(1,) array and beats as times in seconds.
    monkeypatch.setattr(librosa, "load", lambda *a, **k: (np.zeros(1000), 22050))
    monkeypatch.setattr(librosa.beat, "beat_track",
                        lambda **k: (np.array([120.0]), np.array([0.05, 0.55])))

    grid = detect_tempo("ignored.wav")
    assert grid.bpm == 120.0
    assert abs(grid.beat_offset - 0.05) < 1e-9


def test_drum_slots_scale_with_tempo(tmp_path):
    pretty_midi = pytest.importorskip("pretty_midi")
    from pipeline.drumnotation import _slots

    pm = pretty_midi.PrettyMIDI()
    drum = pretty_midi.Instrument(program=0, is_drum=True)
    drum.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=0.0, end=0.05))
    drum.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=1.0, end=1.05))
    pm.instruments.append(drum)
    midi = tmp_path / "d.mid"
    pm.write(str(midi))

    slow = _slots(midi, bpm=60.0)    # 16th = 0.25s -> hit at 1.0s lands in slot 4
    fast = _slots(midi, bpm=120.0)   # 16th = 0.125s -> hit at 1.0s lands in slot 8
    slow_hits = [i for i, s in enumerate(slow) if 36 in s]
    fast_hits = [i for i, s in enumerate(fast) if 36 in s]
    assert fast_hits[1] > slow_hits[1]


def test_apply_key_inserts_key_signature():
    pytest.importorskip("music21")
    from music21 import key as m21key
    from music21 import note as m21note
    from music21 import stream

    from pipeline.notation import _apply_key

    score = stream.Score()
    part = stream.Part()
    for p in ("C4", "E4", "G4", "C5"):
        part.append(m21note.Note(p, quarterLength=1))
    score.append(part)

    _apply_key(score)

    found = score.parts[0].getElementsByClass(m21key.KeySignature)
    assert len(found) >= 1


def test_build_meta_rounds_bpm():
    assert build_meta(96.4) == {"bpm": 96}


def test_build_meta_rounds_bpm_up():
    assert build_meta(119.6) == {"bpm": 120}


def test_build_meta_none_is_empty():
    assert build_meta(None) == {}


def test_build_meta_nonpositive_is_empty():
    assert build_meta(0.0) == {}


def test_build_meta_negative_is_empty():
    assert build_meta(-120.0) == {}


def test_build_meta_inf_is_empty():
    assert build_meta(float("inf")) == {}


def test_build_meta_nan_is_empty():
    assert build_meta(float("nan")) == {}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok  {name}")
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {name}: {exc}")
    print("done")
