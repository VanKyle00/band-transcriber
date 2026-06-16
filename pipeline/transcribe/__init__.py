"""Transcription dispatch: pick the right engine for a stem."""
from __future__ import annotations

from pathlib import Path

from ..config import StemSpec
from .drums import transcribe_drums
from .melodic import transcribe_melodic
from .monophonic import transcribe_monophonic


def transcribe(wav: Path, out_midi: Path, spec: StemSpec) -> Path | None:
    """Run the transcriber configured for `spec`. Returns MIDI path or None."""
    if spec.transcriber == "drums":
        return transcribe_drums(wav, out_midi)
    if spec.transcriber == "melodic":
        # Known-monophonic stems (bass, lead vocals) track far better with a pYIN
        # f0 tracker than the polyphonic model; guitar/piano stay on basic-pitch.
        if not spec.polyphonic and spec.fmin and spec.fmax:
            program = 33 if spec.clef == "bass" else 0
            return transcribe_monophonic(wav, out_midi, fmin=spec.fmin, fmax=spec.fmax,
                                         program=program)
        return transcribe_melodic(wav, out_midi, spec.polyphonic)
    return None
