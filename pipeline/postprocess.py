"""Post-processing layer: tempo detection + rhythmic quantization + note cleanup.

Sits between transcription (raw MIDI) and notation. The pure-logic core
(`quantize_and_clean`, `_fold_tempo`) imports no ML deps so it unit-tests anywhere;
`detect_tempo` (librosa) and `apply_to_midi` (pretty_midi) import their heavy deps lazily.
"""
from __future__ import annotations

import math
from typing import NamedTuple


class Note(NamedTuple):
    start: float
    end: float
    pitch: int
    velocity: int


class Grid(NamedTuple):
    bpm: float
    beat_offset: float


def _fold_tempo(bpm: float) -> float:
    """Fold a detected tempo into a musical [60, 180] BPM range, inclusive (half/double-time guard)."""
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError(f"bad tempo: {bpm}")
    while bpm < 60:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return bpm


def _slot_seconds(grid: Grid, subdiv: int) -> float:
    return (60.0 / grid.bpm) / subdiv


def _snap(t: float, grid: Grid, slot: float) -> float:
    return grid.beat_offset + round((t - grid.beat_offset) / slot) * slot


def _merge_same_pitch(notes: list[Note], slot: float) -> list[Note]:
    """Merge consecutive same-pitch notes separated by less than one slot."""
    result: list[Note] = []
    last_idx: dict[int, int] = {}
    for n in notes:
        i = last_idx.get(n.pitch)
        if i is not None and n.start - result[i].end < slot:
            p = result[i]
            result[i] = p._replace(end=max(p.end, n.end),
                                   velocity=max(p.velocity, n.velocity))
        else:
            last_idx[n.pitch] = len(result)
            result.append(n)
    return result


def _enforce_monophony(notes: list[Note], slot: float) -> list[Note]:
    """Resolve overlaps so at most one note sounds at a time (monophonic stems)."""
    notes = sorted(notes, key=lambda n: (n.start, n.pitch))
    result: list[Note] = []
    for n in notes:
        if result and n.start < result[-1].end:
            prev = result[-1]
            if n.start - prev.start >= slot / 2:
                result[-1] = prev._replace(end=n.start)   # truncate prev, keep both
                result.append(n)
            elif (n.end - n.start) > (prev.end - prev.start):
                result[-1] = n                             # prev too short -> n wins
            # else: drop n (prev wins)
        else:
            result.append(n)
    return result


def quantize_and_clean(notes, grid: Grid, *, monophonic: bool, subdiv: int = 4) -> list[Note]:
    """Snap notes to a 16th grid, drop spurious ones, merge repeats, enforce monophony."""
    slot = _slot_seconds(grid, subdiv)
    kept = [Note(*n) for n in notes if (n[1] - n[0]) >= slot / 2]
    snapped: list[Note] = []
    for n in kept:
        s = _snap(n.start, grid, slot)
        e = _snap(n.end, grid, slot)
        if e < s + slot:
            e = s + slot
        snapped.append(n._replace(start=s, end=e))
    snapped.sort(key=lambda n: (n.start, n.pitch))
    merged = _merge_same_pitch(snapped, slot)
    if monophonic:
        merged = _enforce_monophony(merged, slot)
    return merged


def detect_tempo(wav) -> Grid:
    """Estimate a global tempo + first-beat offset from the mix (librosa beat tracking)."""
    import librosa

    y, sr = librosa.load(str(wav), mono=True)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    bpm = _fold_tempo(float(tempo))
    beat_offset = float(beats[0]) if len(beats) else 0.0
    return Grid(bpm=bpm, beat_offset=beat_offset)


def apply_to_midi(midi_path, grid: Grid, *, monophonic: bool, subdiv: int = 4):
    """Quantize+clean every instrument in a MIDI file and rewrite it at the grid tempo."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    out = pretty_midi.PrettyMIDI(initial_tempo=float(grid.bpm))
    for inst in pm.instruments:
        raw = [Note(n.start, n.end, n.pitch, n.velocity) for n in inst.notes]
        cleaned = quantize_and_clean(raw, grid, monophonic=monophonic, subdiv=subdiv)
        new_inst = pretty_midi.Instrument(program=inst.program, is_drum=inst.is_drum,
                                          name=inst.name)
        new_inst.notes = [pretty_midi.Note(velocity=int(c.velocity), pitch=int(c.pitch),
                                           start=float(c.start), end=float(c.end))
                          for c in cleaned]
        out.instruments.append(new_inst)
    out.write(str(midi_path))
    return midi_path
