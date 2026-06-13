"""Central configuration for the transcription pipeline.

One place to describe *what* each stem is and *how* it should be transcribed and
rendered. Everything downstream (separation, transcription, notation, the web UI)
reads from STEMS so the per-instrument behaviour stays consistent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---- Global limits / audio format -------------------------------------------------
MAX_DURATION_SEC = 480          # hard cap on input length (8 min) — keeps GPU cost bounded
TARGET_SR = 44100               # Demucs operates at 44.1 kHz stereo
TARGET_CHANNELS = 2

# Demucs model. htdemucs_6s gives all six stems (incl. guitar/piano) in one pass.
# Swap to "htdemucs_ft" for higher-quality 4-stem (no guitar/piano) — see README.
DEMUCS_MODEL = "htdemucs_6s"

# Standard tunings as MIDI note numbers, lowest string first.
GUITAR_TUNING = [40, 45, 50, 55, 59, 64]   # E2 A2 D3 G3 B3 E4
BASS_TUNING = [28, 33, 38, 43]             # E1 A1 D2 G2


@dataclass(frozen=True)
class StemSpec:
    """How a single separated stem is transcribed and rendered."""
    name: str
    transcriber: str                 # "drums" | "melodic" | "none"
    polyphonic: bool = False         # hint for the melodic transcriber
    outputs: tuple[str, ...] = ()     # subset of: midi, musicxml, sheet, tab, pianoroll, audio
    clef: str = "treble"             # treble | bass | grand | percussion | treble_8vb
    tuning: list[int] | None = None  # set => generate tablature with this tuning
    experimental: bool = False       # surfaced as a badge in the UI; never blocks the job


# Order matters: this is also the display order in the UI.
STEMS: dict[str, StemSpec] = {
    "drums": StemSpec(
        name="drums", transcriber="drums",
        outputs=("midi", "sheet", "pianoroll", "audio"), clef="percussion",
    ),
    "bass": StemSpec(
        name="bass", transcriber="melodic", polyphonic=False,
        outputs=("midi", "musicxml", "sheet", "tab", "pianoroll", "audio"),
        clef="bass", tuning=BASS_TUNING,
    ),
    "vocals": StemSpec(
        name="vocals", transcriber="melodic", polyphonic=False,
        outputs=("midi", "musicxml", "sheet", "pianoroll", "audio"), clef="treble",
    ),
    "guitar": StemSpec(
        name="guitar", transcriber="melodic", polyphonic=True,
        outputs=("midi", "musicxml", "sheet", "tab", "pianoroll", "audio"),
        clef="treble_8vb", tuning=GUITAR_TUNING, experimental=True,
    ),
    "piano": StemSpec(
        name="piano", transcriber="melodic", polyphonic=True,
        outputs=("midi", "musicxml", "sheet", "pianoroll", "audio"), clef="grand",
        experimental=True,
    ),
    "other": StemSpec(
        name="other", transcriber="none", outputs=("audio",),
    ),
}

# Stems we attempt to transcribe by default (the user can narrow this per job).
DEFAULT_STEMS = ("drums", "bass", "vocals", "guitar", "piano")

# General MIDI percussion note numbers used by the drum transcriber.
DRUM_NOTES = {"kick": 36, "snare": 38, "hihat": 42}

# --- MT3 (heavier polyphonic transcription) ----------------------------------------
# These stems are upgraded to Google MT3 when running on Modal (its own GPU image).
# Anywhere MT3 isn't available — local CLI, the CPU base image — they fall back to the
# default melodic transcriber (basic-pitch). See pipeline/transcribe/mt3_transcribe.py.
MT3_STEMS = ("guitar", "piano")
MT3_MODEL_TYPE = "mt3"               # "mt3" (multi-instrument) | "ismir2021" (piano-only)
MT3_CHECKPOINT_DIR = "/models/mt3"   # baked into the Modal MT3 image at build time

# --- open-fret (learned guitar tab) ------------------------------------------------
# These stems use open-fret's Fretting-Transformer for tab fingering WHEN weights are
# available (see pipeline/opentab.py); otherwise they fall back to tab.py's assigner.
OPENFRET_STEMS = ("guitar",)         # open-fret is 6-string guitar only; bass stays heuristic
