"""Proper drum-staff notation from a classified drum MIDI.

LilyPond's ``\\drummode`` engraves real percussion notation — kick/snare/hi-hat at their
standard staff positions, an x-notehead for the hi-hat — which music21's
MusicXML->LilyPond path crashes on. We map the GM percussion pitches the drum transcriber
emits (see config.DRUM_NOTES) to LilyPond drum names, quantize onsets to a 16th-note grid,
and call LilyPond directly to produce a PDF (download) and an SVG (shown inline in the UI).

The 16th grid is quantized at a fixed assumed tempo — best-effort, like the rest of the
drum path; richer tempo estimation is a documented follow-up.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

# GM percussion -> LilyPond drum names (kick / snare / hi-hat).
_DRUM_LY = {36: "bd", 38: "sn", 42: "hh"}

_GRID = 16           # 16th-note grid
_ASSUMED_BPM = 120   # onsets are quantized at this tempo


def _slots(midi_path: Path) -> list[set[str]]:
    """Quantize the drum MIDI onto a 16th-note grid; each slot holds the drums hit there."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    sec_per_slot = (60.0 / _ASSUMED_BPM) * (4.0 / _GRID)
    end = max(pm.get_end_time(), sec_per_slot)
    n = int(math.ceil(end / sec_per_slot))
    slots: list[set[str]] = [set() for _ in range(n)]
    for inst in pm.instruments:
        for note in inst.notes:
            name = _DRUM_LY.get(int(round(note.pitch)))
            if name is None:
                continue
            i = min(max(int(round(note.start / sec_per_slot)), 0), n - 1)
            slots[i].add(name)
    while len(slots) % _GRID:  # pad out to whole 4/4 measures
        slots.append(set())
    return slots


def _lilypond(slots: list[set[str]]) -> str:
    tokens = []
    for s in slots:
        if not s:
            tokens.append("r16")
        elif len(s) == 1:
            tokens.append(f"{next(iter(s))}16")
        else:
            tokens.append("<" + " ".join(sorted(s)) + ">16")
    body = " ".join(tokens)
    return (
        '\\version "2.24.0"\n'
        "#(set-global-staff-size 18)\n"
        "\\score {\n"
        "  \\new DrumStaff \\drummode {\n"
        "    \\time 4/4\n"
        f"    {body}\n"
        "  }\n"
        "  \\layout { }\n"
        "}\n"
    )


def render_drum_notation(midi_path: Path, out_pdf: Path, out_svg: Path) -> tuple[Path, Path]:
    """Engrave a classified drum MIDI to a percussion-staff PDF + SVG via LilyPond."""
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    work = out_pdf.parent
    ly = work / "drums.ly"
    ly.write_text(_lilypond(_slots(midi_path)), encoding="utf-8")
    base = work / "drums_render"
    for fmt in ("svg", "pdf"):
        subprocess.run(
            ["lilypond", f"--{fmt}", "-dno-point-and-click", "-o", str(base), str(ly)],
            check=True, capture_output=True,
        )
    # LilyPond writes <base>.svg / <base>.pdf for a single page; glob as a fallback.
    svg = base.with_suffix(".svg")
    if not svg.exists():
        svg = next(work.glob(f"{base.name}*.svg"))
    svg.replace(out_svg)
    base.with_suffix(".pdf").replace(out_pdf)
    return out_pdf, out_svg
