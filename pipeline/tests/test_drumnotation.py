"""Drum-notation legibility: hits extend to the next hit instead of trailing short rests.
Run: python -m pytest pipeline/tests"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.drumnotation import (_event_xml, _lilypond_measure, _LY_DUR, _largest, _GRID,
                                   _consolidate, render_drum_musicxml)

KICK, SNARE, HIHAT, TOM, CYMBAL = 36, 38, 42, 47, 49


def _durations(xml):
    return [int(x) for x in re.findall(r"<duration>(\d+)</duration>", xml)]


def test_event_xml_extends_span_with_tie_no_rest():
    # span of 5 sixteenths: quarter tied to a 16th (clean types), never a trailing rest
    xml = _event_xml({KICK}, 5)
    assert "<rest/>" not in xml
    assert sum(_durations(xml)) == 5                     # full span covered
    assert "<type>quarter</type>" in xml and "<type>16th</type>" in xml
    assert '<tie type="start"/>' in xml and '<tie type="stop"/>' in xml


def test_event_xml_type_matches_duration():
    # every notehead's drawn type must equal its <duration> (OSMD cursor stays aligned)
    type_for = {16: "whole", 12: "half", 8: "half", 6: "quarter", 4: "quarter",
                3: "eighth", 2: "eighth", 1: "16th"}
    for span in range(1, 17):
        for note in re.findall(r"<duration>(\d+)</duration>[^<]*(?:<tie[^>]*/>)*<type>(\w+)</type>",
                               _event_xml({KICK}, span)):
            assert type_for[int(note[0])] == note[1]


def test_event_xml_chord_spans_share_duration():
    xml = _event_xml({KICK, SNARE}, 7)               # pieces 6 + 1, two voices each
    assert "<rest/>" not in xml
    assert xml.count("<chord/>") == 2                 # one chord member per piece
    assert sorted(_durations(xml)) == [1, 1, 6, 6]


def test_lilypond_measure_no_internal_16th_rests():
    # hits at slots 0,5,10,13 -> spans 5,5,3,3; none should leave a 16th rest
    slots = [set() for _ in range(_GRID)]
    for slot, p in [(0, KICK), (5, SNARE), (10, KICK), (13, SNARE)]:
        slots[slot] = {p}
    body = _lilypond_measure(slots)
    assert "r16" not in body
    assert "~" in body                                   # non-clean spans extend via ties


def _measure_sixteenths(body):
    inv = {v: k for k, v in _LY_DUR.items()}
    total = 0
    for tok in body.replace("~", " ").split():
        m = re.search(r"(\d+\.?)$", tok)
        if m:
            total += inv[m.group(1)]
    return total


def test_lilypond_measure_durations_sum_to_full_bar():
    slots = [set() for _ in range(_GRID)]
    for slot, p in [(0, KICK), (5, SNARE), (10, KICK), (13, SNARE)]:
        slots[slot] = {p}
    assert _measure_sixteenths(_lilypond_measure(slots)) == _GRID


def test_lilypond_empty_measure_is_a_single_rest():
    body = _lilypond_measure([set() for _ in range(_GRID)])
    assert body == "r1"                                  # whole-bar rest, not 16 r16s


def test_clean_eighth_groove_has_no_ties_or_rests():
    # kick/snare/hat on straight eighths: every span is a clean eighth -> tidy output
    slots = [set() for _ in range(_GRID)]
    for slot in range(0, _GRID, 2):
        slots[slot] = {42}
    slots[0] |= {KICK}
    slots[8] |= {SNARE}
    body = _lilypond_measure(slots)
    assert "r16" not in body and "~" not in body
    assert _measure_sixteenths(body) == _GRID


# ---- toms + cymbals (ADTOF's richer kit) ------------------------------------------
def _write_drum_midi(path, events):
    pretty_midi = pytest.importorskip("pretty_midi")
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0, is_drum=True, name="Drums")
    for start, pitch in events:
        inst.notes.append(pretty_midi.Note(velocity=100, pitch=pitch, start=start, end=start + 0.05))
    pm.instruments.append(inst)
    pm.write(str(path))


def test_musicxml_renders_toms_on_their_own_position(tmp_path):
    # a tom (47) must appear at a distinct staff position with a normal notehead, not be dropped
    mid = tmp_path / "d.mid"
    _write_drum_midi(mid, [(0.0, KICK), (0.5, SNARE), (1.0, TOM), (1.5, HIHAT)])  # 120 BPM bar
    xml = render_drum_musicxml(mid, tmp_path / "d.musicxml", bpm=120).read_text()
    assert "<display-step>D</display-step><display-octave>5</display-octave>" in xml  # tom position


def test_musicxml_renders_cymbals_with_x_notehead(tmp_path):
    # a crash/ride (49) must appear at the cymbal position with an x notehead
    mid = tmp_path / "d.mid"
    _write_drum_midi(mid, [(0.0, KICK), (0.0, CYMBAL), (0.5, SNARE)])
    xml = render_drum_musicxml(mid, tmp_path / "d.musicxml", bpm=120).read_text()
    assert "<display-step>A</display-step><display-octave>5</display-octave>" in xml  # cymbal position
    assert xml.count("<notehead>x</notehead>") >= 1                                   # drawn as x


def test_lilypond_renders_toms_and_cymbals():
    slots = [set() for _ in range(_GRID)]
    slots[0] = {TOM}
    slots[8] = {CYMBAL}
    body = _lilypond_measure(slots)
    assert "tomml" in body
    assert "cymc" in body


def test_consolidate_preserves_toms_and_cymbals():
    # two identical bars with a tom + cymbal: majority-vote consolidation must keep them,
    # not vote them out (they'd vanish if the kit vector ignores toms/cymbals)
    slots = [set() for _ in range(2 * _GRID)]
    for base in (0, _GRID):
        slots[base] = {KICK, CYMBAL}
        slots[base + 4] = {TOM}
        slots[base + 8] = {SNARE}
    out = _consolidate(slots, pickup=0)
    present = set().union(*out)
    assert TOM in present and CYMBAL in present
