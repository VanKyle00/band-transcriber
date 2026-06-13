"""Transcription dispatch: pick the right engine for a stem."""
from __future__ import annotations

from pathlib import Path

from ..config import StemSpec
from .drums import transcribe_drums
from .melodic import transcribe_melodic


def transcribe(wav: Path, out_midi: Path, spec: StemSpec) -> Path | None:
    """Run the transcriber configured for `spec`. Returns MIDI path or None."""
    if spec.transcriber == "drums":
        return transcribe_drums(wav, out_midi)
    if spec.transcriber == "melodic":
        return transcribe_melodic(wav, out_midi, spec.polyphonic)
    return None
