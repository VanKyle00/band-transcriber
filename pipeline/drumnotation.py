"""Drum notation from a classified drum MIDI.

Two renderings from the same kick/snare/hi-hat 16th grid:
  - ``render_drum_musicxml`` → a proper percussion-staff MusicXML (distinct staff positions
    per piece, x-notehead hi-hats, hits extended to the next event so the rhythm reads as
    8ths/quarters). The browser renders this with OSMD, so the playback cursor works on it.
  - ``render_drum_pdf`` → a LilyPond ``\\drummode`` engraving for a clean printable download.

The 16th grid is quantized at the caller-supplied tempo (default 120 BPM); the pipeline
passes the song's detected tempo here so the rhythm reads at the right speed.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

# GM percussion -> LilyPond drum name.
_DRUM_LY = {36: "bd", 38: "sn", 42: "hh"}
# GM percussion -> (MusicXML display-step, display-octave, notehead) on a percussion staff.
_DRUM_POS = {36: ("F", 4, None), 38: ("C", 5, None), 42: ("G", 5, "x")}

_GRID = 16           # 16th-note grid
_ASSUMED_BPM = 120   # onsets are quantized at this tempo


def _slots(midi_path: Path, bpm: float = _ASSUMED_BPM) -> list[set[int]]:
    """Quantize the drum MIDI onto a 16th-note grid; each slot holds the GM pitches hit there."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    sec_per_slot = (60.0 / bpm) * (4.0 / _GRID)
    end = max(pm.get_end_time(), sec_per_slot)
    n = int(math.ceil(end / sec_per_slot))
    slots: list[set[int]] = [set() for _ in range(n)]
    for inst in pm.instruments:
        for note in inst.notes:
            p = int(round(note.pitch))
            if p in _DRUM_POS:
                i = min(max(int(round(note.start / sec_per_slot)), 0), n - 1)
                slots[i].add(p)
    while len(slots) % _GRID:  # pad out to whole 4/4 measures
        slots.append(set())
    return slots


# ---- MusicXML (for the interactive OSMD view) -------------------------------------
_TYPE = {1: ("16th", 0), 2: ("eighth", 0), 3: ("eighth", 1), 4: ("quarter", 0),
         6: ("quarter", 1), 8: ("half", 0), 12: ("half", 1), 16: ("whole", 0)}
_CLEAN = (16, 12, 8, 6, 4, 3, 2, 1)


def _largest(dur: int) -> int:
    return next(x for x in _CLEAN if x <= dur)


def _note_xml(pitch: int, dur: int, chord: bool = False,
              tie_start: bool = False, tie_stop: bool = False) -> str:
    step, octv, head = _DRUM_POS[pitch]
    t, dots = _TYPE[dur]
    hd = f"<notehead>{head}</notehead>" if head else ""
    kinds = (["stop"] if tie_stop else []) + (["start"] if tie_start else [])
    tie = "".join(f'<tie type="{k}"/>' for k in kinds)            # sounded tie (after duration)
    tied = "".join(f'<tied type="{k}"/>' for k in kinds)          # notated tie (in notations)
    notations = f"<notations>{tied}</notations>" if tied else ""
    return (f"<note>{'<chord/>' if chord else ''}<unpitched><display-step>{step}</display-step>"
            f"<display-octave>{octv}</display-octave></unpitched><duration>{dur}</duration>{tie}"
            f"<type>{t}</type>{'<dot/>' * dots}{hd}{notations}</note>")


def _rest_xml(dur: int) -> str:
    out = ""
    while dur > 0:
        d = _largest(dur)
        t, dots = _TYPE[d]
        out += f"<note><rest/><duration>{d}</duration><type>{t}</type>{'<dot/>' * dots}</note>"
        dur -= d
    return out


def _event_xml(pitches: set[int], dur: int) -> str:
    # Each hit fills the whole span to the next hit. A non-clean span is written as clean
    # note values tied together rather than a note trailed by a hard-to-read 16th/32nd
    # rest, so the hit reads as one extended note while every notehead's drawn type still
    # matches its <duration> (keeps the OSMD playback cursor aligned).
    pieces, d = [], dur
    while d > 0:
        x = _largest(d)
        pieces.append(x)
        d -= x
    ps = sorted(pitches)
    out = ""
    for idx, x in enumerate(pieces):
        ts, tp = idx < len(pieces) - 1, idx > 0
        out += _note_xml(ps[0], x, tie_start=ts, tie_stop=tp)
        out += "".join(_note_xml(p, x, chord=True, tie_start=ts, tie_stop=tp) for p in ps[1:])
    return out


_INSTS = (36, 38, 42)   # kick, snare, hi-hat


def _consolidate(slots: list[set[int]], pickup: int, *, tol: int = 4) -> list[set[int]]:
    """Make repeated drum measures render identically.

    Transcription noise makes the same groove come out slightly different bar to bar
    (a dropped hi-hat here, a ghost hit there). Cluster the full measures by Hamming
    distance over their kick/snare/hi-hat hit grid (<= `tol` differing hits), then
    replace every member of a cluster with the cluster's majority-vote pattern. So
    identical blocks look identical and stray hits get voted out. The pickup measure
    and genuinely-different bars (fills) are left untouched.
    """
    starts = list(range(pickup, len(slots), _GRID))
    vecs = [[1 if p in slots[s + i] else 0 for i in range(_GRID) for p in _INSTS]
            for s in starts]
    ham = lambda a, b: sum(x != y for x, y in zip(a, b))
    clusters: list[list] = []   # [canonical_vec, [member_index, ...]]
    for i, v in enumerate(vecs):
        for c in clusters:
            if ham(c[0], v) <= tol:
                c[1].append(i)
                break
        else:
            clusters.append([v, [i]])
    for _canon, members in clusters:
        if len(members) < 2:
            continue
        maj = [1 if sum(vecs[m][b] for m in members) * 2 >= len(members) else 0
               for b in range(_GRID * len(_INSTS))]
        pattern = [set() for _ in range(_GRID)]
        b = 0
        for i in range(_GRID):
            for p in _INSTS:
                if maj[b]:
                    pattern[i].add(p)
                b += 1
        for m in members:
            for i in range(_GRID):
                slots[starts[m] + i] = set(pattern[i])
    return slots


def _phase(slots: list[set[int]], bpm: float, downbeat: float) -> tuple[list[set[int]], int]:
    """Pickup length (in 16th slots) that puts `downbeat` on a barline, padding the slot
    list so whole 4/4 measures follow the pickup. pickup=0 when no/zero downbeat."""
    sec_per_slot = (60.0 / bpm) * (4.0 / _GRID)
    pickup = round(downbeat / sec_per_slot) % _GRID if downbeat and downbeat > 0 else 0
    while (len(slots) - pickup) % _GRID:
        slots.append(set())
    return slots, pickup


def _measure_xml(num: int, slots: list[set[int]], *, first: bool, implicit: bool = False) -> str:
    length = len(slots)
    attrs = ("<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type>"
             "</time><clef><sign>percussion</sign><line>2</line></clef></attributes>") if first else ""
    imp = ' implicit="yes"' if implicit else ""
    hits = [i for i in range(length) if slots[i]]
    body, pos = "", 0
    if not hits:
        body = _rest_xml(length)
    for k, i in enumerate(hits):
        if i > pos:
            body += _rest_xml(i - pos)
        nxt = hits[k + 1] if k + 1 < len(hits) else length
        body += _event_xml(slots[i], nxt - i)
        pos = nxt
    return f'<measure number="{num}"{imp}>{attrs}{body}</measure>'


def render_drum_musicxml(midi_path: Path, out_xml: Path, bpm: float = _ASSUMED_BPM,
                         downbeat: float = 0.0) -> Path:
    """Emit a percussion-staff MusicXML (kick/snare/hi-hat at standard positions, x hi-hats).

    `downbeat` (seconds) phases the barlines so the first kick reads on count 1; the
    pre-downbeat audio becomes a leading pickup measure, which keeps the notation
    spanning the full-length stem audio so the playback cursor stays in sync.
    """
    slots, pickup = _phase(_slots(midi_path, bpm), bpm, downbeat)
    slots = _consolidate(slots, pickup)
    bounds = ([(0, pickup, True)] if pickup else [])
    bounds += [(i, i + _GRID, False) for i in range(pickup, len(slots), _GRID)]
    measures = "".join(
        _measure_xml(n if pickup else n + 1, slots[a:b], first=(n == 0), implicit=imp)
        for n, (a, b, imp) in enumerate(bounds)
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
           '"http://www.musicxml.org/dtds/partwise.dtd">\n'
           '<score-partwise version="3.1"><part-list><score-part id="P1"><part-name>Drums</part-name>'
           f'</score-part></part-list><part id="P1">{measures}</part></score-partwise>')
    out_xml.parent.mkdir(parents=True, exist_ok=True)
    out_xml.write_text(xml, encoding="utf-8")
    return out_xml


# ---- LilyPond PDF (for download) --------------------------------------------------
# 16th-grid duration -> LilyPond duration token (whole=1 ... 16th=16, dotted via ".").
_LY_DUR = {16: "1", 12: "2.", 8: "2", 6: "4.", 4: "4", 3: "8.", 2: "8", 1: "16"}


def _ly_dur(name: str, span: int, tie: bool) -> str:
    """A note/chord/rest of `span` 16ths as LilyPond tokens. Non-clean spans split into
    clean pieces joined by ties (notes) so a hit reads as one extended note instead of a
    note trailed by 16th rests; rests use the same split untied."""
    pieces, d = [], span
    while d > 0:
        x = _largest(d)
        pieces.append(f"{name}{_LY_DUR[x]}")
        d -= x
    return (" ~ " if tie else " ").join(pieces)


def _lilypond_measure(slots: list[set[int]]) -> str:
    length = len(slots)
    hits = [i for i in range(length) if slots[i]]
    if not hits:
        return _ly_dur("r", length, tie=False)
    out, pos = [], 0
    for k, i in enumerate(hits):
        if i > pos:
            out.append(_ly_dur("r", i - pos, tie=False))   # genuine silence before this hit
        nxt = hits[k + 1] if k + 1 < len(hits) else length
        names = sorted(_DRUM_LY[p] for p in slots[i])
        name = names[0] if len(names) == 1 else "<" + " ".join(names) + ">"
        out.append(_ly_dur(name, nxt - i, tie=True))       # hit extended to the next hit
        pos = nxt
    return " ".join(out)


def _lilypond(slots: list[set[int]], pickup: int = 0) -> str:
    measures = [slots[:pickup]] if pickup else []
    measures += [slots[a:a + _GRID] for a in range(pickup, len(slots), _GRID)]
    body = " |\n    ".join(_lilypond_measure(m) for m in measures)
    partial = f"\\partial 16*{pickup} " if pickup else ""
    return ('\\version "2.24.0"\n#(set-global-staff-size 18)\n'
            '\\score {\n  \\new DrumStaff \\drummode {\n    \\time 4/4\n'
            f'    {partial}{body}\n  }}\n  \\layout {{ }}\n}}\n')


def render_drum_pdf(midi_path: Path, out_pdf: Path, bpm: float = _ASSUMED_BPM,
                    downbeat: float = 0.0) -> Path:
    """Engrave a clean printable drum chart via LilyPond's drum mode."""
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    work = out_pdf.parent
    ly = work / "drums.ly"
    slots, pickup = _phase(_slots(midi_path, bpm), bpm, downbeat)
    slots = _consolidate(slots, pickup)
    ly.write_text(_lilypond(slots, pickup), encoding="utf-8")
    base = work / "drums_render"
    subprocess.run(["lilypond", "--pdf", "-dno-point-and-click", "-o", str(base), str(ly)],
                   check=True, capture_output=True)
    base.with_suffix(".pdf").replace(out_pdf)
    return out_pdf
