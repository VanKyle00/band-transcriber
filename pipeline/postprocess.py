"""Post-processing layer: tempo detection + rhythmic quantization + note cleanup.

Sits between transcription (raw MIDI) and notation. The pure-logic core
(`quantize_and_clean`) imports no ML deps so it unit-tests anywhere;
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
    """Estimate a global tempo + first-beat offset from the mix (librosa).

    Tempo is estimated with a log-normal prior centered at 140 BPM rather than
    librosa's default 120. Band music sits ~110-180, and the 120 prior tends to lock
    onto the *half* tempo (a real 184 BPM reads as 92), which doubles every printed
    note value. The prior is wide enough that a clearly slow song still reads slow.
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(str(wav), mono=True)
    oenv = librosa.onset.onset_strength(y=y, sr=sr)
    bpm = float(np.atleast_1d(
        librosa.feature.tempo(onset_envelope=oenv, sr=sr, start_bpm=140.0)
    )[0])  # feature.tempo returns a shape-(1,) array
    _, beats = librosa.beat.beat_track(onset_envelope=oenv, sr=sr, units="time", start_bpm=bpm)
    beat_offset = float(beats[0]) if len(beats) else 0.0
    return Grid(bpm=bpm, beat_offset=beat_offset)


def build_meta(bpm: float | None) -> dict:
    """Job-level metadata for the artifacts manifest. Empty when tempo is unknown."""
    if bpm is None or not math.isfinite(bpm) or bpm <= 0:
        return {}
    return {"bpm": round(bpm)}


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
