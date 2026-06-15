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


def quantize_and_clean(notes, grid: Grid, *, monophonic: bool, subdiv: int = 4) -> list[Note]:
    """Snap notes to a 16th grid and drop spurious ones.

    (Same-pitch merge + monophony resolution are layered in by Task 3.)
    """
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
    return snapped
