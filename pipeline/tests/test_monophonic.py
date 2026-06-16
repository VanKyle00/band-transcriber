"""Dependency-light tests for the pYIN note-segmentation core.
Run: python -m pytest pipeline/tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.transcribe.monophonic import segment_pitches

DT = 0.01  # 10 ms frames


def _const(pitch, n):
    return [float(pitch)] * n


def test_two_distinct_notes_split():
    pitches = _const(40, 30) + _const(45, 30)
    notes = segment_pitches(pitches, DT, min_note_dur=0.05)
    assert [p for *_, p in notes] == [40, 45]
    assert abs(notes[0][1] - 0.30) < 0.02


def test_vibrato_stays_one_note():
    # +/-0.5 semitone wobble around 60 must not fragment into a staircase
    pitches = [60 + (0.5 if i % 2 else -0.5) for i in range(40)]
    notes = segment_pitches(pitches, DT)
    assert len(notes) == 1
    assert notes[0][2] == 60


def test_short_blip_dropped():
    pitches = _const(60, 2) + [None] * 40   # 0.02 s note -> below min_note_dur
    assert segment_pitches(pitches, DT, min_note_dur=0.05) == []


def test_same_pitch_rejoined_across_dropout():
    # a sustained note broken by a brief voicing dropout -> one note, not two
    pitches = _const(43, 20) + [None] * 8 + _const(43, 20)
    notes = segment_pitches(pitches, DT, max_gap=0.05, merge_gap=0.12)
    assert len(notes) == 1
    assert notes[0][2] == 43


def test_long_unvoiced_gap_breaks_note():
    pitches = _const(50, 20) + [None] * 30 + _const(50, 20)   # 0.30 s of silence
    notes = segment_pitches(pitches, DT, max_gap=0.05, merge_gap=0.10)
    assert len(notes) == 2


def test_single_frame_octave_jump_smoothed():
    pitches = _const(48, 10) + [60.0] + _const(48, 10)   # one stray octave-up frame
    notes = segment_pitches(pitches, DT)
    assert len(notes) == 1
    assert notes[0][2] == 48


def test_repeated_pitch_splits_on_onset():
    # same pitch played twice; an amplitude onset at the re-attack splits into two notes
    pitches = _const(40, 30) + _const(40, 30)
    notes = segment_pitches(pitches, DT, onset_frames=[30])
    assert len(notes) == 2
    assert [p for *_, p in notes] == [40, 40]


def test_repeated_pitch_stays_one_note_without_onset():
    # identical f0 with no onset info -> one note (legacy dropout-repair behavior preserved)
    pitches = _const(40, 30) + _const(40, 30)
    assert len(segment_pitches(pitches, DT)) == 1


def test_onset_does_not_break_sustained_dropout():
    # a held note with a brief dropout but no onset at the rejoin stays a single note
    pitches = _const(43, 20) + [None] * 8 + _const(43, 20)
    notes = segment_pitches(pitches, DT, max_gap=0.05, merge_gap=0.12, onset_frames=[0])
    assert len(notes) == 1


def test_empty_input():
    assert segment_pitches([], DT) == []


def test_all_unvoiced():
    assert segment_pitches([None] * 50, DT) == []
