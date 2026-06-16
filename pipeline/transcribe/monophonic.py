"""Monophonic-stem transcription via pYIN (audio -> MIDI).

Bass and lead vocals are single-voice, so a monophonic f0 tracker (librosa pYIN)
beats the general polyphonic model on them: it locks onto the *fundamental* instead
of a harmonic (no more octave-jumped bass) and its voiced flag drops the phantom
notes a polyphonic model invents during breaths/consonants. Output is a MIDI track
that the post-processor then quantizes to the beat grid.

`segment_pitches` is pure (no heavy deps) so it unit-tests anywhere; the pYIN call
and MIDI writing import their deps lazily.
"""
from __future__ import annotations

import math
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


def _frame_length(fmin: float, sr: int) -> int:
    """pYIN needs a few periods of the lowest searched pitch per analysis frame."""
    need = 4.0 * sr / fmin
    return max(2048, 1 << int(math.ceil(math.log2(need))))


def transcribe_monophonic(wav: Path, out_midi: Path, *, fmin: float, fmax: float,
                          program: int = 0, sr: int = 22050, hop: int = 256,
                          prob_threshold: float = 0.5) -> Path:
    """Transcribe a known-monophonic stem to MIDI via pYIN f0 tracking."""
    import librosa
    import numpy as np
    import pretty_midi

    y, _ = librosa.load(str(wav), sr=sr, mono=True)
    f0, _voiced, vprob = librosa.pyin(
        y, fmin=fmin, fmax=fmax, sr=sr, hop_length=hop,
        frame_length=_frame_length(fmin, sr),
    )
    pitch = librosa.hz_to_midi(f0)
    frames = [float(m) if (np.isfinite(m) and vp >= prob_threshold) else None
              for m, vp in zip(pitch, vprob)]
    notes = segment_pitches(frames, hop / sr)

    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=program)
    for start, end, note in notes:
        inst.notes.append(pretty_midi.Note(velocity=80, pitch=note, start=start, end=end))
    pm.instruments.append(inst)
    out_midi.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(out_midi))
    return out_midi
