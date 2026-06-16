"""Monophonic-stem transcription via CREPE (audio -> MIDI).

Bass and lead vocals are single-voice. pYIN (the previous tracker) only reliably
followed ~half of a real-world bass and jumped around on the rest, so the notes it
produced were essentially noise. CREPE -- a deep neural pitch tracker -- follows the
same bass ~93% of the time and far more stably, including the low/fast lines pYIN
can't resolve. We keep the pure `segment_pitches` core and feed it CREPE's per-frame
pitch + confidence.

`segment_pitches` imports no heavy deps so it unit-tests anywhere; the CREPE call and
MIDI writing import torch/torchcrepe/pretty_midi lazily.
"""
from __future__ import annotations

from pathlib import Path


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _smooth(pitches: list[float | None], window: int) -> list[float | None]:
    """None-aware median smoothing: tames vibrato wobble and single-frame octave jumps."""
    if window <= 1:
        return list(pitches)
    half = window // 2
    out: list[float | None] = []
    for i in range(len(pitches)):
        seg = [p for p in pitches[max(0, i - half):i + half + 1] if p is not None]
        out.append(_median(seg) if seg else None)
    return out


def segment_pitches(pitches, frame_dt, *, smooth: int = 5, pitch_tol: float = 0.7,
                    min_note_dur: float = 0.06, max_gap: float = 0.05,
                    merge_gap: float = 0.10):
    """Turn a per-frame f0 track into note events.

    `pitches[i]` is the MIDI pitch of frame i, or None when unvoiced; `frame_dt` is
    the seconds per frame. Returns a list of (start, end, pitch) with integer pitch
    and times in seconds.

    A note runs while the smoothed pitch stays within `pitch_tol` semitones of its
    running median; it survives unvoiced gaps up to `max_gap`s. Same-pitch notes
    split by up to `merge_gap`s are re-joined (repairs sustained notes broken by brief
    voicing dropouts), and notes shorter than `min_note_dur` are dropped.
    """
    p = _smooth(list(pitches), smooth)
    runs: list[list] = []  # [start_idx, last_voiced_idx, [pitches]]
    cur: list | None = None
    for i, val in enumerate(p):
        if val is not None:
            if cur is None:
                cur = [i, i, [val]]
            elif abs(val - _median(cur[2])) <= pitch_tol:
                cur[1] = i
                cur[2].append(val)
            else:
                runs.append(cur)
                cur = [i, i, [val]]
        elif cur is not None and (i - cur[1]) * frame_dt > max_gap:
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)

    raw = [(s * frame_dt, (e + 1) * frame_dt, int(round(_median(ps)))) for s, e, ps in runs]
    merged: list[list] = []
    for start, end, pitch in raw:
        if merged and merged[-1][2] == pitch and start - merged[-1][1] <= merge_gap:
            merged[-1][1] = end
        else:
            merged.append([start, end, pitch])
    return [(start, end, pitch) for start, end, pitch in merged if end - start >= min_note_dur]


def transcribe_monophonic(wav: Path, out_midi: Path, *, fmin: float, fmax: float,
                          program: int = 0, confidence: float = 0.5,
                          model: str = "tiny") -> Path:
    """Transcribe a known-monophonic stem to MIDI via CREPE pitch tracking.

    `model` is the CREPE size: "tiny" is ~15x faster than "full" on CPU for the same
    coverage here, so it's the default. `confidence` gates CREPE's periodicity.
    """
    import librosa
    import numpy as np
    import pretty_midi
    import torch
    import torchcrepe

    sr, hop = 16000, 160                 # CREPE runs at 16 kHz; hop 160 = 10 ms frames
    y, _ = librosa.load(str(wav), sr=sr, mono=True)
    pitch_hz, periodicity = torchcrepe.predict(
        torch.tensor(y).unsqueeze(0), sr, hop_length=hop, fmin=fmin, fmax=fmax,
        model=model, return_periodicity=True, batch_size=512,
    )
    pitch = librosa.hz_to_midi(pitch_hz.squeeze().numpy())
    period = periodicity.squeeze().numpy()
    frames = [float(m) if (np.isfinite(m) and pr >= confidence) else None
              for m, pr in zip(pitch, period)]
    notes = segment_pitches(frames, hop / sr)

    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=program)
    for start, end, note in notes:
        inst.notes.append(pretty_midi.Note(velocity=80, pitch=note, start=start, end=end))
    pm.instruments.append(inst)
    out_midi.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(out_midi))
    return out_midi
