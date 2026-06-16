"""Orchestration: source -> stems -> per-stem notation/tab -> uploaded artifacts.

`process_stem` is self-contained (CPU only) so the Modal app can fan it out across
stems in parallel. `run_pipeline` is the sequential entry point used by the local
CLI and by the Modal orchestrator. Per-output failures are captured as warnings so
one bad render (e.g. percussion engraving) never sinks the whole job.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from . import download, drumnotation, notation, opentab, postprocess, separate, storage, tab
from .config import DEFAULT_STEMS, OPENFRET_STEMS, STEMS
from .transcribe import transcribe

logger = logging.getLogger(__name__)


def _build_tab(stem_name: str, midi: Path, spec) -> tuple[str | None, str | None, str | None]:
    """Generate tab for a stem. Returns (ascii_tab, alphatex, warning).

    Uses open-fret's learned fingering when configured + available (ASCII only for
    now — see the design's non-goals), falling back to the deterministic assigner
    which produces both ASCII and AlphaTex. (None, None, warning) only if even the
    fallback fails.
    """
    if stem_name in OPENFRET_STEMS and opentab.available():
        try:
            return opentab.midi_to_tab_openfret(midi), None, None
        except Exception as exc:
            warn = f"open-fret failed, used heuristic tab: {exc}"
            try:
                return tab.midi_to_ascii_tab(str(midi), spec.tuning), None, warn
            except Exception as exc2:
                return None, None, f"tab failed: {exc2}"
    try:
        ascii_tab, alphatex = tab.midi_to_tabs(str(midi), spec.tuning)
        return ascii_tab, alphatex, None
    except Exception as exc:
        return None, None, f"tab failed: {exc}"


def process_stem(stem_name: str, stem_wav: Path, workdir: Path, job_id: str,
                 precomputed_midi: Path | None = None, grid=None) -> dict:
    """Transcribe + render one stem, upload its artifacts, return a URL manifest.

    `precomputed_midi`: MIDI already produced upstream (e.g. by the MT3 GPU function);
    when given, the transcription step is skipped and this MIDI is used directly.
    """
    spec = STEMS[stem_name]
    out: dict = {"name": stem_name, "experimental": spec.experimental, "warnings": []}
    sdir = workdir / stem_name
    sdir.mkdir(parents=True, exist_ok=True)

    if "audio" in spec.outputs:
        out["audio"] = storage.upload_artifact(stem_wav, job_id)

    if spec.transcriber == "none":
        return out

    midi = sdir / f"{stem_name}.mid"
    if precomputed_midi is not None:
        midi.write_bytes(Path(precomputed_midi).read_bytes())
    else:
        try:
            transcribe(stem_wav, midi, spec)
        except Exception as exc:  # transcription is the prerequisite for everything below
            out["warnings"].append(f"transcription failed: {exc}")
            return out
    if grid is not None and spec.transcriber == "melodic":
        try:
            postprocess.apply_to_midi(midi, grid, monophonic=not spec.polyphonic)
        except Exception as exc:
            out["warnings"].append(f"post-processing failed: {exc}")
    out["midi"] = storage.upload_artifact(midi, job_id)

    if spec.clef == "percussion":
        # Drums get real percussion notation: a MusicXML the browser renders interactively
        # with OSMD (so the playback cursor works), plus a LilyPond-engraved PDF to download.
        try:
            bpm = grid.bpm if grid is not None else 120.0
            xml = drumnotation.render_drum_musicxml(midi, sdir / f"{stem_name}.musicxml", bpm=bpm)
            out["musicxml"] = storage.upload_artifact(xml, job_id)
            pdf = drumnotation.render_drum_pdf(midi, sdir / f"{stem_name}.pdf", bpm=bpm)
            out["sheet_pdf"] = storage.upload_artifact(pdf, job_id)
        except Exception as exc:
            out["warnings"].append(f"drum notation failed: {exc}")
    elif "musicxml" in spec.outputs or "sheet" in spec.outputs:
        try:
            xml = notation.midi_to_musicxml(midi, sdir / f"{stem_name}.musicxml", spec.clef)
            if "musicxml" in spec.outputs:
                out["musicxml"] = storage.upload_artifact(xml, job_id)
            if "sheet" in spec.outputs:
                pdf = notation.musicxml_to_pdf(xml, sdir / f"{stem_name}.pdf")
                out["sheet_pdf"] = storage.upload_artifact(pdf, job_id)
        except Exception as exc:
            out["warnings"].append(f"notation failed: {exc}")

    if "tab" in spec.outputs and spec.tuning:
        ascii_tab, alphatex, warn = _build_tab(stem_name, midi, spec)
        if ascii_tab is not None:
            tab_txt = sdir / f"{stem_name}.tab.txt"
            tab_txt.write_text(ascii_tab, encoding="utf-8")
            out["tab"] = storage.upload_artifact(tab_txt, job_id)
        if alphatex is not None:
            tab_tex = sdir / f"{stem_name}.alphatex"
            tab_tex.write_text(alphatex, encoding="utf-8")
            out["tab_alphatex"] = storage.upload_artifact(tab_tex, job_id)
        if warn:
            out["warnings"].append(warn)

    return out


def run_pipeline(job_id: str, source: str, is_url: bool,
                 stems: tuple[str, ...] = DEFAULT_STEMS,
                 workdir: str | Path | None = None,
                 proxy: str | None = None) -> dict:
    """End-to-end run. Updates the job row at each stage; returns the manifest."""
    work = Path(workdir or tempfile.mkdtemp(prefix="bt-"))
    try:
        storage.update_job(job_id, status="processing", stage="downloading")
        wav = download.fetch_audio(source, is_url, work / "src", proxy)

        try:
            grid = postprocess.detect_tempo(wav)
        except Exception as exc:
            logger.warning("tempo detection failed; falling back to 120 BPM: %s", exc)
            grid = None

        storage.update_job(job_id, stage="separating")
        separated = separate.separate(wav, work / "stems")

        results = []
        for name in stems:
            if name not in separated:
                continue
            storage.update_job(job_id, stage=f"transcribing:{name}")
            results.append(process_stem(name, separated[name], work / "out", job_id, grid=grid))

        artifacts = {"stems": results}
        meta = postprocess.build_meta(grid.bpm if grid is not None else None)
        if meta:
            artifacts["meta"] = meta
        storage.update_job(job_id, status="done", stage="done", artifacts=artifacts)
        return artifacts
    except Exception as exc:
        storage.update_job(job_id, status="error", stage="error", error=str(exc))
        raise
