"""Pitched-instrument transcription via Spotify's basic-pitch (audio -> MIDI).

Near-perfect on isolated monophonic stems (bass, vocal melody); usable-but-messy on
polyphonic stems (guitar, piano) — those are flagged experimental upstream. Returns
the written MIDI path.
"""
from __future__ import annotations

from pathlib import Path

# Tighter onset/frame thresholds for polyphonic material trims spurious notes a bit.
_POLY = dict(onset_threshold=0.6, frame_threshold=0.4, minimum_note_length=90)
_MONO = dict(onset_threshold=0.5, frame_threshold=0.3, minimum_note_length=120)


def transcribe_melodic(wav: Path, out_midi: Path, polyphonic: bool = True) -> Path:
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict

    params = _POLY if polyphonic else _MONO
    _, midi_data, _ = predict(str(wav), ICASSP_2022_MODEL_PATH, **params)
    out_midi.parent.mkdir(parents=True, exist_ok=True)
    midi_data.write(str(out_midi))
    return out_midi
