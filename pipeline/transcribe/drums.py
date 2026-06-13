"""Best-effort automatic drum transcription.

Onset detection (librosa) + a per-onset spectral-band classifier that buckets each
hit into kick / snare / hi-hat. Deliberately lightweight and dependency-stable; a
learned ADT model (e.g. omnizart) can be swapped in behind this same interface for
higher accuracy. Output is a General-MIDI percussion track.
"""
from __future__ import annotations

from pathlib import Path

from ..config import DRUM_NOTES

_SR = 22050
_WIN = 0.05  # seconds of audio analysed per onset


def _classify(segment, sr) -> str:
    import numpy as np

    if len(segment) < 8:
        return "snare"
    spec = abs(np.fft.rfft(segment * np.hanning(len(segment))))
    freqs = np.fft.rfftfreq(len(segment), 1 / sr)
    low = spec[freqs < 150].sum()
    mid = spec[(freqs >= 150) & (freqs < 2000)].sum()
    high = spec[freqs >= 5000].sum()
    total = low + mid + high + 1e-9
    if low / total > 0.5:
        return "kick"
    if high / total > 0.35:
        return "hihat"
    return "snare"


def transcribe_drums(wav: Path, out_midi: Path) -> Path:
    import librosa
    import numpy as np
    import pretty_midi

    y, sr = librosa.load(str(wav), sr=_SR, mono=True)
    onset_times = librosa.onset.onset_detect(
        y=y, sr=sr, units="time", backtrack=True
    )

    pm = pretty_midi.PrettyMIDI()
    drum = pretty_midi.Instrument(program=0, is_drum=True, name="Drums")
    win = int(_WIN * sr)
    for t in onset_times:
        i = int(t * sr)
        label = _classify(y[i:i + win], sr)
        drum.notes.append(pretty_midi.Note(
            velocity=100, pitch=DRUM_NOTES[label], start=float(t), end=float(t) + 0.05,
        ))
    pm.instruments.append(drum)
    out_midi.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(out_midi))
    return out_midi
