"""open-fret adapter — learned MIDI -> guitar tab via the Fretting-Transformer (T5).

open-fret (github.com/Sidmaz666/open-fret, MIT) ships **no public weights** — you train
them yourself with its `scripts/train_model.py`. So this adapter is GATED: it only
activates when both the repo and a weights directory are present. Otherwise the caller
falls back to the deterministic assigner in `tab.py` (so guitar tabs work today either way).

It delegates to open-fret's own `scripts/inference.py` (via subprocess) rather than
re-implementing its MIDI tokenisation, so we use the model's exact encode/decode. The
script prints AlphaTex (which alphaTab can render) plus an ASCII preview to stdout; we
capture that. No heavy imports here — the ML runs inside the subprocess.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEFAULT_REPO_DIR = "/opt/open-fret"
DEFAULT_MODEL_DIR = "/models/open-fret/tiny-tab-v1/final"


def _repo_dir() -> Path:
    return Path(os.environ.get("OPENFRET_REPO_DIR", DEFAULT_REPO_DIR))


def _model_dir() -> Path:
    return Path(os.environ.get("OPENFRET_MODEL_DIR", DEFAULT_MODEL_DIR))


def available() -> bool:
    """True only if the open-fret repo AND a weights directory are both present."""
    return (_repo_dir() / "scripts" / "inference.py").exists() and _model_dir().exists()


def midi_to_tab_openfret(midi_path: str | Path, timeout: int = 600) -> str:
    """Run open-fret inference on a MIDI file; return its tab output. Raises on failure."""
    if not available():
        raise RuntimeError("open-fret repo or weights not available")
    result = subprocess.run(
        ["python", "scripts/inference.py",
         "--midi", str(Path(midi_path).resolve()),
         "--model", str(_model_dir())],
        cwd=str(_repo_dir()), capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"open-fret inference failed: {result.stderr.strip()[-400:]}")
    out = result.stdout.strip()
    if not out:
        raise RuntimeError("open-fret produced no output")
    return out
