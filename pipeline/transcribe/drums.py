"""Best-effort automatic drum transcription.

Per-band onset detection: kick, snare and hi-hat are each detected independently in
their own frequency band, so simultaneous hits (kick+hat on the downbeat, snare+hat
on the backbeat) all register. The previous single-onset + winner-take-all classifier
could only emit one drum per instant, so whenever a hi-hat coincided with a kick or
snare its broadband energy masked the louder, lower piece — kicks and snares went
undetected even when plainly audible. Deliberately lightweight and dependency-stable;
a learned ADT model (e.g. omnizart) can be swapped in behind this same interface for
higher accuracy. Output is a General-MIDI percussion track.
"""
from __future__ import annotations

from pathlib import Path

from ..config import DRUM_NOTES

_SR = 22050
_N_FFT = 2048
_HOP = 512

# Per-drum detection band (Hz). Each is detected on its own onset envelope so a hit in
# one never masks a simultaneous hit in another. Snare starts above the kick's harmonics
# (~150 Hz) and stops below the hi-hat region to limit cross-band double-triggering.
_BANDS = {"kick": (0.0, 150.0), "snare": (200.0, 2000.0), "hihat": (6000.0, None)}

# An onset only counts if that band's energy at the peak is >= this fraction of the
# band's loudest frame. Rejects spectral-flux leakage (a hi-hat's faint energy in the
# kick band looks like an onset but carries almost no low-end), while staying additive
# across simultaneous hits the way an energy-ratio test cannot.
_GATE = 0.2


def detect_drum_onsets(y, sr) -> dict[str, list[float]]:
    """Per-band onset times (seconds), keyed by drum. Each drum is detected on its own
    frequency band's onset envelope and gated by that band's energy, so a hi-hat never
    masks a coincident kick or snare. Shared by transcription and downbeat detection."""
    import librosa
    import numpy as np

    spec = np.abs(librosa.stft(y, n_fft=_N_FFT, hop_length=_HOP))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=_N_FFT)
    hits: dict[str, list[float]] = {}
    for label, (lo, hi) in _BANDS.items():
        mask = freqs >= lo if hi is None else (freqs >= lo) & (freqs < hi)
        band = spec[mask]
        energy = band.sum(axis=0)
        energy = energy / (energy.max() + 1e-9)
        env = librosa.onset.onset_strength(
            S=librosa.amplitude_to_db(band, ref=np.max), sr=sr, hop_length=_HOP
        )
        frames = librosa.onset.onset_detect(
            onset_envelope=env, sr=sr, hop_length=_HOP, backtrack=True
        )
        hits[label] = [float(librosa.frames_to_time(fr, sr=sr, hop_length=_HOP))
                       for fr in frames if energy[fr] >= _GATE]
    return hits


def transcribe_drums(wav: Path, out_midi: Path) -> Path:
    import librosa
    import pretty_midi

    y, sr = librosa.load(str(wav), sr=_SR, mono=True)
    pm = pretty_midi.PrettyMIDI()
    drum = pretty_midi.Instrument(program=0, is_drum=True, name="Drums")
    for label, times in detect_drum_onsets(y, sr).items():
        for t in times:
            drum.notes.append(pretty_midi.Note(
                velocity=100, pitch=DRUM_NOTES[label], start=t, end=t + 0.05,
            ))
    drum.notes.sort(key=lambda n: n.start)
    pm.instruments.append(drum)
    out_midi.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(out_midi))
    return out_midi
