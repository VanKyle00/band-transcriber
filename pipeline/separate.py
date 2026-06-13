"""Stem separation with Demucs.

Runs the model once (htdemucs_6s by default -> 6 stems) and returns the path to
each stem WAV. This is the GPU-heavy stage; everything after it is CPU work.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .config import DEMUCS_MODEL, STEMS


def separate(input_wav: Path, outdir: Path, model: str = DEMUCS_MODEL) -> dict[str, Path]:
    """Separate `input_wav` into stems. Returns {stem_name: wav_path}.

    Uses the Demucs CLI (stable across versions). The model and its weights are
    expected to be baked into the runtime image / cached volume.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["python", "-m", "demucs", "-n", model, "-o", str(outdir),
         "--filename", "{stem}.{ext}", str(input_wav)],
        check=True,
    )
    # Demucs writes to <outdir>/<model>/<stem>.wav
    stem_dir = outdir / model
    found: dict[str, Path] = {}
    for name in STEMS:
        wav = stem_dir / f"{name}.wav"
        if wav.exists():
            found[name] = wav
    if not found:
        raise RuntimeError(f"Demucs produced no stems in {stem_dir}")
    return found
