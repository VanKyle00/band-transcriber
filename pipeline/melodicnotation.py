"""Hand-built MusicXML for monophonic pitched stems (bass, lead vocals).

music21's MIDI->MusicXML re-quantizes notes onto a t=0 grid and bars from t=0, so the
printed staff can't be phased to the downbeat and drifts off the beat. We render the
staff ourselves on the same downbeat-anchored 16th grid as the drum renderer (shared
duration/`_phase` helpers), with a leading pickup measure: the music's beats land on
the printed beats while the notation still spans the full audio, so the OSMD/alphaTab
playback cursor stays in sync. Monophonic only (one note at a time -> no chords); the
post-processor already enforces monophony on these stems.

The core (`_measure_tokens`, spelling, key) is pure; only `render_melodic_musicxml`
touches pretty_midi (lazily).
"""
from __future__ import annotations

from pathlib import Path

from .drumnotation import _GRID, _TYPE, _largest, _rest_xml

# MIDI pitch-class -> (step, alter) for sharp- and flat-leaning keys.
_SHARP = [("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
          ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0)]
_FLAT = [("C", 0), ("D", -1), ("D", 0), ("E", -1), ("E", 0), ("F", 0),
         ("G", -1), ("G", 0), ("A", -1), ("A", 0), ("B", -1), ("B", 0)]
_MAJOR = (0, 2, 4, 5, 7, 9, 11)
_ACC = {1: "sharp", -1: "flat", 0: "natural"}
# clef name -> (sign, line, octave-change). The 8vb clefs draw notes an octave higher
# than they sound (an "8" under the clef), which keeps low bass off the ledger lines.
_CLEF = {"treble": ("G", 2, 0), "bass": ("F", 4, 0),
         "treble_8vb": ("G", 2, -1), "bass_8vb": ("F", 4, -1)}


def _diatonic(fifths: int) -> set[int]:
    tonic = (7 * fifths) % 12
    return {(tonic + iv) % 12 for iv in _MAJOR}


def _best_fifths(pitches) -> int:
    """Pick the key signature (-7..7) that leaves the fewest out-of-key notes."""
    pcs = [p % 12 for p in pitches]
    best_f, best_cost = 0, None
    for f in range(-7, 8):
        dia = _diatonic(f)
        cost = sum(1 for pc in pcs if pc not in dia)
        if best_cost is None or cost < best_cost or (cost == best_cost and abs(f) < abs(best_f)):
            best_f, best_cost = f, cost
    return best_f


def _spell(pitch: int, fifths: int) -> tuple[str, int, int]:
    step, alter = (_SHARP if fifths >= 0 else _FLAT)[pitch % 12]
    return step, alter, pitch // 12 - 1


def _tie_values(dur: int) -> list[int]:
    """Split a duration (in 16th slots) into note-values joined by ties."""
    out = []
    while dur > 0:
        v = _largest(dur)
        out.append(v)
        dur -= v
    return out


def _measure_tokens(notes, n_slots: int, pickup: int):
    """Lay monophonic (onset, dur, pitch) events onto a phased measure grid.

    Returns a list of (implicit, tokens) per measure, where each token is
    ('rest', slots) or ('note', pitch, value, tie_in, tie_out). Notes that cross a
    barline are split and tied; durations are split into tied note-values.
    """
    barlines = [(0, pickup, True)] if pickup else []
    s = pickup
    while s < n_slots:
        barlines.append((s, min(s + _GRID, n_slots), False))
        s += _GRID

    notes = sorted(notes)
    ni = 0
    carry = None  # (pitch, remaining_slots) of a note continuing into this measure
    result = []
    for start, end, implicit in barlines:
        toks: list = []
        pos = start
        if carry is not None:
            pitch, remaining = carry
            seg = min(remaining, end - pos)
            cont = remaining > seg
            vals = _tie_values(seg)
            for j, v in enumerate(vals):
                toks.append(("note", pitch, v, True, j < len(vals) - 1 or cont))
            pos += seg
            carry = (pitch, remaining - seg) if cont else None
        while pos < end:
            if ni < len(notes) and notes[ni][0] <= pos:
                _, dur, pitch = notes[ni]
                ni += 1
                seg = min(dur, end - pos)
                cont = dur > seg
                vals = _tie_values(seg)
                for j, v in enumerate(vals):
                    toks.append(("note", pitch, v, j > 0, j < len(vals) - 1 or cont))
                pos += seg
                if cont:
                    carry = (pitch, dur - seg)
                    break
            else:
                nxt = notes[ni][0] if ni < len(notes) else end
                rest_end = min(nxt, end) if nxt > pos else end
                toks.append(("rest", rest_end - pos))
                pos = rest_end
        result.append((implicit, toks))
    return result


def _note_xml(pitch: int, value: int, *, fifths: int, dia: set, tie_in: bool, tie_out: bool) -> str:
    step, alter, octv = _spell(pitch, fifths)
    name, dots = _TYPE[value]
    alter_xml = f"<alter>{alter}</alter>" if alter else ""
    acc = f"<accidental>{_ACC[alter]}</accidental>" if (pitch % 12) not in dia else ""
    ties = ('<tie type="stop"/>' if tie_in else "") + ('<tie type="start"/>' if tie_out else "")
    tied = ('<tied type="stop"/>' if tie_in else "") + ('<tied type="start"/>' if tie_out else "")
    notations = f"<notations>{tied}</notations>" if tied else ""
    return (f"<note><pitch><step>{step}</step>{alter_xml}<octave>{octv}</octave></pitch>"
            f"<duration>{value}</duration>{ties}<type>{name}</type>{'<dot/>' * dots}{acc}{notations}</note>")


def _attributes(clef: str, fifths: int) -> str:
    sign, line, octave_change = _CLEF.get(clef, _CLEF["treble"])
    octc = f"<clef-octave-change>{octave_change}</clef-octave-change>" if octave_change else ""
    return ("<attributes><divisions>4</divisions>"
            f"<key><fifths>{fifths}</fifths></key>"
            "<time><beats>4</beats><beat-type>4</beat-type></time>"
            f"<clef><sign>{sign}</sign><line>{line}</line>{octc}</clef></attributes>")


def render_melodic_musicxml(midi_path: Path, out_xml: Path, clef: str = "treble",
                            bpm: float = 120.0, downbeat: float = 0.0,
                            name: str = "Part") -> Path:
    """Render a monophonic stem's MIDI to a downbeat-phased, pitched MusicXML staff."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    sec_per_slot = (60.0 / bpm) * (4.0 / _GRID)
    raw = sorted((round(n.start / sec_per_slot),
                  max(1, round((n.end - n.start) / sec_per_slot)),
                  int(round(n.pitch)))
                 for inst in pm.instruments for n in inst.notes)
    notes = []
    for k, (onset, dur, pitch) in enumerate(raw):
        if k + 1 < len(raw) and onset + dur > raw[k + 1][0]:   # keep it monophonic
            dur = max(1, raw[k + 1][0] - onset)
        notes.append((onset, dur, pitch))

    n_slots = max((o + d for o, d, _ in notes), default=0)
    pickup = round(downbeat / sec_per_slot) % _GRID if downbeat and downbeat > 0 else 0
    while (n_slots - pickup) % _GRID:
        n_slots += 1

    fifths = _best_fifths([p for _, _, p in notes]) if notes else 0
    dia = _diatonic(fifths)
    attrs = _attributes(clef, fifths)
    parts = []
    for n, (implicit, toks) in enumerate(_measure_tokens(notes, n_slots, pickup)):
        body = "".join(
            _rest_xml(t[1]) if t[0] == "rest"
            else _note_xml(t[1], t[2], fifths=fifths, dia=dia, tie_in=t[3], tie_out=t[4])
            for t in toks
        )
        imp = ' implicit="yes"' if implicit else ""
        num = n if pickup else n + 1
        parts.append(f'<measure number="{num}"{imp}>{attrs if n == 0 else ""}{body}</measure>')

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
           '"http://www.musicxml.org/dtds/partwise.dtd">\n'
           '<score-partwise version="3.1"><part-list><score-part id="P1">'
           f'<part-name>{name}</part-name></score-part></part-list>'
           f'<part id="P1">{"".join(parts)}</part></score-partwise>')
    out_xml.parent.mkdir(parents=True, exist_ok=True)
    out_xml.write_text(xml, encoding="utf-8")
    return out_xml
