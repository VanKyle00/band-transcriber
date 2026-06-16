"""Drum detection must find kicks and snares even under a constant hi-hat.

The previous single-onset + winner-take-all classifier returned one drum per instant,
so a hi-hat coinciding with a kick/snare masked it and kicks/snares went undetected.
This guards the band-wise detector against that regression. Skips where audio deps are
unavailable. Run: python -m pytest pipeline/tests
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

np = pytest.importorskip("numpy")
pytest.importorskip("librosa")
pretty_midi = pytest.importorskip("pretty_midi")
wavfile = pytest.importorskip("scipy.io.wavfile")

from pipeline.config import DRUM_NOTES
from pipeline.transcribe.drums import transcribe_drums

SR = 22050
BPM = 120
BEAT = 60.0 / BPM


def _env(n, tau):
    return np.exp(-(np.arange(n) / SR) / tau)


def _kick():
    n = int(0.18 * SR); t = np.arange(n) / SR
    f = 120 * np.exp(-t / 0.03) + 50
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.06)


def _snare(rng):
    n = int(0.18 * SR); t = np.arange(n) / SR
    return (rng.standard_normal(n) * 0.8 + np.sin(2 * np.pi * 200 * t) * 0.5) * _env(n, 0.05)


def _hihat(rng):
    n = int(0.05 * SR)
    return np.diff(rng.standard_normal(n), prepend=0) * _env(n, 0.015) * 0.5


def _groove():
    """Two 4/4 bars: kick on 1&3, snare on 2&4, hi-hat on every eighth (so every
    kick/snare coincides with a hi-hat — the case that defeated the old detector)."""
    rng = np.random.default_rng(0)
    mix = np.zeros(int(2 * 4 * BEAT * SR) + SR)
    def place(sig, t):
        i = int(t * SR); mix[i:i + len(sig)] += sig
    for bar in range(2):
        b = bar * 4 * BEAT
        place(_kick(), b); place(_kick(), b + 2 * BEAT)
        place(_snare(rng), b + BEAT); place(_snare(rng), b + 3 * BEAT)
        for e in range(8):
            place(_hihat(rng), b + e * BEAT / 2)
    return mix / np.max(np.abs(mix)) * 0.9


def test_kicks_and_snares_detected_under_hihat(tmp_path):
    wav = tmp_path / "groove.wav"
    wavfile.write(str(wav), SR, (_groove() * 32767).astype(np.int16))
    midi = tmp_path / "groove.mid"
    transcribe_drums(wav, midi)

    pm = pretty_midi.PrettyMIDI(str(midi))
    pitches = [n.pitch for inst in pm.instruments for n in inst.notes]
    kicks = pitches.count(DRUM_NOTES["kick"])
    snares = pitches.count(DRUM_NOTES["snare"])

    # truth is 4 kicks + 4 snares; require the backbone be found (old detector got 0/0)
    assert kicks >= 3, f"expected >=3 kicks, got {kicks}"
    assert snares >= 3, f"expected >=3 snares, got {snares}"
