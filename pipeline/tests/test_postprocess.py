"""Tests for the (dependency-light) post-processing core. Run: python -m pytest pipeline/tests"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.postprocess import Grid, Note, build_meta, quantize_and_clean


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


def test_legato_bridges_subbeat_gap_to_next_onset():
    grid = Grid(bpm=120.0, beat_offset=0.0)        # slot = 0.125s; one beat = 4 slots
    # two distinct pitches a 2-slot (eighth) rest apart -> first extends to the second
    notes = [Note(0.0, 0.125, 40, 100), Note(0.375, 0.5, 42, 100)]
    out = quantize_and_clean(notes, grid, monophonic=True)
    assert out == [Note(0.0, 0.375, 40, 100), Note(0.375, 0.5, 42, 100)]


def test_legato_keeps_beat_or_longer_rests():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    # a full-beat (4-slot) gap is a genuine rest -> NOT bridged
    notes = [Note(0.0, 0.125, 40, 100), Note(0.625, 0.75, 42, 100)]
    out = quantize_and_clean(notes, grid, monophonic=True)
    assert out[0] == Note(0.0, 0.125, 40, 100)


def test_legato_preserves_onsets_and_pitches():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    notes = [Note(0.0, 0.125, 40, 100), Note(0.25, 0.375, 43, 100),
             Note(0.5, 0.75, 45, 100)]
    out = quantize_and_clean(notes, grid, monophonic=True)
    assert [n.start for n in out] == [0.0, 0.25, 0.5]   # onsets untouched
    assert [n.pitch for n in out] == [40, 43, 45]       # pitches untouched


def test_legato_only_applies_to_monophonic():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    notes = [Note(0.0, 0.125, 40, 100), Note(0.375, 0.5, 42, 100)]
    out = quantize_and_clean(notes, grid, monophonic=False)
    assert out[0] == Note(0.0, 0.125, 40, 100)          # polyphonic: gap left as a rest


def test_octave_fold_pulls_down_octave_outlier():
    from pipeline.postprocess import _octave_fold
    notes = [Note(i * 0.5, i * 0.5 + 0.25, p, 100) for i, p in enumerate([40, 40, 52, 40, 40])]
    assert [n.pitch for n in _octave_fold(notes)] == [40, 40, 40, 40, 40]


def test_octave_fold_keeps_moderate_leap():
    from pipeline.postprocess import _octave_fold
    # a +7 (perfect fifth) leap is real bass motion, below the threshold -> untouched
    notes = [Note(i * 0.5, i * 0.5 + 0.25, p, 100) for i, p in enumerate([40, 40, 47, 40, 40])]
    assert [n.pitch for n in _octave_fold(notes)] == [40, 40, 47, 40, 40]


def test_octave_fold_leaves_in_register_line():
    from pipeline.postprocess import _octave_fold
    notes = [Note(i * 0.5, i * 0.5 + 0.25, p, 100) for i, p in enumerate([40, 43, 45, 43, 40])]
    assert [n.pitch for n in _octave_fold(notes)] == [40, 43, 45, 43, 40]


def test_octave_fold_applies_only_to_monophonic():
    grid = Grid(bpm=120.0, beat_offset=0.0)
    notes = [Note(i * 0.5, i * 0.5 + 0.5, p, 100) for i, p in enumerate([40, 40, 52, 40, 40])]
    assert 52 in [n.pitch for n in quantize_and_clean(notes, grid, monophonic=False)]
    assert 52 not in [n.pitch for n in quantize_and_clean(notes, grid, monophonic=True)]


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

    # feature.tempo returns a shape-(1,) array; beat_track yields beat times in seconds.
    monkeypatch.setattr(librosa, "load", lambda *a, **k: (np.zeros(2048), 22050))
    monkeypatch.setattr(librosa.onset, "onset_strength", lambda **k: np.zeros(64))
    monkeypatch.setattr(librosa.feature, "tempo", lambda **k: np.array([184.6]))
    monkeypatch.setattr(librosa.beat, "beat_track",
                        lambda **k: (np.array([184.6]), np.array([0.05, 0.37])))

    grid = detect_tempo("ignored.wav")
    assert abs(grid.bpm - 184.6) < 1e-6
    assert abs(grid.beat_offset - 0.05) < 1e-9


def test_refine_tempo_snaps_to_true_grid():
    from pipeline.postprocess import _refine_tempo

    slot = (60.0 / 180.0) / 4.0                 # 16th note at the true tempo (180 BPM)
    onsets = [i * slot for i in range(64)]       # onsets sitting exactly on a 180 grid
    assert abs(_refine_tempo(onsets, 186.0) - 180.0) < 1.0


def test_refine_tempo_too_few_onsets_unchanged():
    from pipeline.postprocess import _refine_tempo

    assert _refine_tempo([0.0, 0.5], 185.0) == 185.0


def test_phase_pickup_puts_downbeat_on_barline():
    from pipeline.drumnotation import _GRID, _phase

    slots = [set() for _ in range(20)]
    out, pickup = _phase(slots, 120.0, 0.5)      # 16th = 0.125s -> 0.5s is 4 slots in
    assert pickup == 4
    assert (len(out) - pickup) % _GRID == 0


def test_phase_zero_downbeat_no_pickup():
    from pipeline.drumnotation import _GRID, _phase

    out, pickup = _phase([set() for _ in range(10)], 120.0, 0.0)
    assert pickup == 0
    assert len(out) % _GRID == 0


def test_drum_kick_lands_on_count_one(tmp_path):
    pretty_midi = pytest.importorskip("pretty_midi")
    pytest.importorskip("music21")
    from music21 import converter

    from pipeline.drumnotation import render_drum_musicxml

    pm = pretty_midi.PrettyMIDI()
    drum = pretty_midi.Instrument(program=0, is_drum=True)
    for t in (0.5, 1.0, 1.5, 2.0):               # kicks; 0.5s is the downbeat
        drum.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=t, end=t + 0.05))
    pm.instruments.append(drum)
    midi = tmp_path / "d.mid"
    pm.write(str(midi))

    xml = render_drum_musicxml(midi, tmp_path / "d.musicxml", bpm=120.0, downbeat=0.5)
    assert 'implicit="yes"' in xml.read_text(encoding="utf-8")     # a pickup measure exists
    first = next(n for n in converter.parse(str(xml)).recurse().notes)
    assert abs(first.beat - 1.0) < 1e-6                            # first kick on count 1


def test_consolidate_unifies_near_identical_measures():
    from pipeline.drumnotation import _GRID, _consolidate

    K, S, H = 36, 38, 42
    m1 = [({K} if i == 0 else {S} if i == 8 else {H} if i % 2 == 0 else set()) for i in range(_GRID)]
    m2 = [set(x) for x in m1]
    m2[6].discard(H)                                   # same groove, one dropped hi-hat
    out = _consolidate(m1 + m2, pickup=0)
    assert out[:_GRID] == out[_GRID:2 * _GRID]         # now rendered identically


def test_consolidate_keeps_distinct_measures():
    from pipeline.drumnotation import _GRID, _consolidate

    K, S = 36, 38
    groove = [({K} if i == 0 else set()) for i in range(_GRID)]
    fill = [{S} for _ in range(_GRID)]                 # nothing like the groove
    out = _consolidate([set(x) for x in groove] + [set(x) for x in fill], pickup=0)
    assert out[:_GRID] != out[_GRID:]                  # left distinct


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
