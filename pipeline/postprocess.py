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
    """Fold a detected tempo into a musical 60-180 BPM range (half/double-time guard)."""
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError(f"bad tempo: {bpm}")
    while bpm < 60:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return bpm
