"""Dependency-light tests for the hand-built monophonic MusicXML renderer.
Run: python -m pytest pipeline/tests"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.melodicnotation import _best_fifths, _measure_tokens, _spell, _tie_values


def test_tie_values_split_into_note_values():
    assert _tie_values(4) == [4]          # a clean quarter
    assert _tie_values(5) == [4, 1]       # quarter tied to a sixteenth
    assert _tie_values(7) == [6, 1]       # dotted quarter tied to a sixteenth
    assert _tie_values(16) == [16]        # a whole note


def test_spell_uses_sharps_for_sharp_keys():
    assert _spell(61, 2)[:2] == ("C", 1)   # C#4 in a sharp key


def test_spell_uses_flats_for_flat_keys():
    assert _spell(61, -2)[:2] == ("D", -1)  # Db4 in a flat key


def test_best_fifths_prefers_fewest_accidentals():
    assert _best_fifths([60, 62, 64, 65, 67, 69, 71]) == 0   # C major
    assert _best_fifths([62, 64, 66, 67, 69, 71, 73]) == 2   # D major (F#, C#)


def test_measure_tokens_phases_downbeat_to_a_barline():
    # pickup=4: the note at slot 4 (the downbeat) opens the first full measure on count 1
    toks = _measure_tokens([(4, 4, 60)], n_slots=20, pickup=4)
    assert toks[0][0] is True                                # measure 0 is the pickup
    assert toks[1][1][0] == ("note", 60, 4, False, False)    # downbeat note starts measure 1


def test_measure_tokens_ties_a_note_across_the_barline():
    toks = _measure_tokens([(14, 4, 60)], n_slots=32, pickup=0)
    assert toks[0][1][-1] == ("note", 60, 2, False, True)    # tie out of measure 0
    assert toks[1][1][0] == ("note", 60, 2, True, False)     # tie into measure 1


def test_render_preserves_pitch_and_aligns_downbeat(tmp_path):
    pretty_midi = pytest.importorskip("pretty_midi")
    pytest.importorskip("music21")
    from music21 import converter

    from pipeline.melodicnotation import render_melodic_musicxml

    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=33)
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=60, start=0.5, end=1.0))   # C4 on downbeat
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=62, start=1.0, end=1.5))   # D4 after
    pm.instruments.append(inst)
    midi = tmp_path / "b.mid"
    pm.write(str(midi))

    xml = render_melodic_musicxml(midi, tmp_path / "b.musicxml", clef="bass",
                                  bpm=120.0, downbeat=0.5)
    assert 'implicit="yes"' in xml.read_text(encoding="utf-8")    # pickup measure exists
    notes = list(converter.parse(str(xml)).recurse().notes)
    assert [n.pitch.midi for n in notes] == [60, 62]              # pitches preserved
    assert abs(notes[0].beat - 1.0) < 1e-6                        # downbeat note on count 1
