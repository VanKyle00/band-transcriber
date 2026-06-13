"""Modal deployment of the Band Transcriber pipeline.

Topology (cost-aware):
  web (CPU)         -- FastAPI: create job + report status
  process_job (CPU) -- orchestrates one job; spawned, not awaited by the request
  separate_audio (GPU) -- the only GPU step: Demucs htdemucs_6s
  transcribe_stem (CPU) -- fanned out per stem: transcription + notation + tab + upload

Deploy:  modal deploy modal_app.py
Test:    modal run modal_app.py::process_job --job-id test --source song.wav --is-url false
"""
from __future__ import annotations

import os
import uuid

import modal

app = modal.App("band-transcriber")

# Demucs weights are baked into the image at build time so cold starts don't re-download them.
def _bake_models() -> None:
    from demucs.pretrained import get_model

    get_model("htdemucs_6s")


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "lilypond", "git")
    .pip_install("torch==2.3.1", "torchaudio==2.3.1")
    .pip_install_from_requirements("pipeline/requirements.txt")
    .pip_install("fastapi[standard]==0.115.0", "transformers==4.44.2")
    # open-fret repo (learned guitar tabs). No public weights ship, so it stays in
    # fallback until you mount a trained checkpoint at OPENFRET_MODEL_DIR (e.g. a Volume).
    .run_commands("git clone --depth=1 https://github.com/Sidmaz666/open-fret /opt/open-fret")
    .run_function(_bake_models)
    .add_local_python_source("pipeline")
)

secrets = [modal.Secret.from_name("band-transcriber-supabase")]


# --- MT3 image (isolated) ----------------------------------------------------------
# MT3 is JAX/T5X-based and conflicts with the PyTorch+TF base image, so it gets its own.
# NOTE: the jax/t5x/mt3 stack is famously version-sensitive — treat these pins as a
# starting point and validate the build on Modal; you may need to adjust jax/flax/orbax
# versions to match the current t5x `main`.
def _bake_mt3_checkpoint() -> None:
    import gcsfs  # public bucket, anonymous access

    fs = gcsfs.GCSFileSystem(token="anon")
    fs.get("gs://mt3/checkpoints/mt3/", "/models/mt3/", recursive=True)


mt3_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "libsndfile1", "git")
    .run_commands(
        "git clone --branch=main https://github.com/google-research/t5x /opt/t5x",
        "pip install -e /opt/t5x",
        "git clone --branch=main https://github.com/magenta/mt3 /opt/mt3",
        "pip install -e /opt/mt3",
    )
    .pip_install(
        "jax[cuda12]==0.4.25",  # GPU build; overrides the CPU jax pulled in above
        "librosa==0.10.2", "note-seq==0.0.5", "pretty_midi==0.2.10",
        "nest-asyncio", "gcsfs",
    )
    .run_function(_bake_mt3_checkpoint)
    .add_local_python_source("pipeline")
)


@app.function(image=image, gpu="L4", timeout=1800, secrets=secrets)
def separate_audio(input_wav: bytes) -> dict[str, bytes]:
    """GPU: separate one normalized WAV into stem WAVs (returned as bytes)."""
    import tempfile
    from pathlib import Path

    from pipeline import separate

    work = Path(tempfile.mkdtemp())
    src = work / "input.wav"
    src.write_bytes(input_wav)
    stems = separate.separate(src, work / "stems")
    return {name: path.read_bytes() for name, path in stems.items()}


@app.function(image=mt3_image, gpu="L4", timeout=1800)
def mt3_to_midi(stem_name: str, wav_bytes: bytes) -> bytes:
    """GPU: transcribe one polyphonic stem (guitar/piano) to MIDI with MT3."""
    import tempfile
    from pathlib import Path

    from pipeline.config import MT3_CHECKPOINT_DIR, MT3_MODEL_TYPE
    from pipeline.transcribe.mt3_transcribe import transcribe_mt3

    work = Path(tempfile.mkdtemp())
    wav = work / f"{stem_name}.wav"
    wav.write_bytes(wav_bytes)
    out = work / f"{stem_name}.mid"
    transcribe_mt3(wav, out, MT3_MODEL_TYPE, MT3_CHECKPOINT_DIR)
    return out.read_bytes()


@app.function(image=image, timeout=1800, secrets=secrets)
def transcribe_stem(stem_name: str, wav_bytes: bytes, job_id: str,
                    midi_bytes: bytes | None = None) -> dict:
    """CPU: render one stem (notation + tab + upload).

    If `midi_bytes` is supplied (e.g. from MT3), it's used as the transcription;
    otherwise the stem is transcribed here (drum classifier / basic-pitch).
    """
    import tempfile
    from pathlib import Path

    from pipeline.pipeline import process_stem

    work = Path(tempfile.mkdtemp())
    wav = work / f"{stem_name}.wav"
    wav.write_bytes(wav_bytes)
    precomputed = None
    if midi_bytes is not None:
        precomputed = work / f"{stem_name}.in.mid"
        precomputed.write_bytes(midi_bytes)
    return process_stem(stem_name, wav, work / "out", job_id, precomputed_midi=precomputed)


@app.function(image=image, timeout=3600, secrets=secrets)
def process_job(job_id: str, source: str, is_url: bool, stems: list[str],
                upload_bytes: bytes | None = None, proxy: str | None = None) -> dict:
    """CPU orchestrator (spawned): download -> GPU separate -> fan-out stems."""
    import tempfile
    from pathlib import Path

    from pipeline import download, storage
    from pipeline.config import MT3_STEMS

    work = Path(tempfile.mkdtemp())
    try:
        storage.update_job(job_id, status="processing", stage="downloading")
        if upload_bytes is not None:
            raw = work / "upload"
            raw.write_bytes(upload_bytes)
            wav = download.from_file(raw, work / "src")
        else:
            wav = download.fetch_audio(source, is_url, work / "src",
                                       proxy or os.environ.get("YTDLP_PROXY"))

        storage.update_job(job_id, stage="separating")
        stem_bytes = separate_audio.remote(wav.read_bytes())

        storage.update_job(job_id, stage="transcribing")
        available = [n for n in stems if n in stem_bytes]

        # Kick off MT3 (GPU) for polyphonic stems first so they run in parallel with
        # the CPU stems' rendering.
        mt3_calls = {n: mt3_to_midi.spawn(n, stem_bytes[n]) for n in available if n in MT3_STEMS}
        render_calls = [
            transcribe_stem.spawn(n, stem_bytes[n], job_id)
            for n in available if n not in MT3_STEMS
        ]
        for name, call in mt3_calls.items():
            try:
                midi = call.get()
            except Exception:
                midi = None  # MT3 failed -> transcribe_stem falls back to basic-pitch
            render_calls.append(transcribe_stem.spawn(name, stem_bytes[name], job_id, midi))

        results = [c.get() for c in render_calls]
        artifacts = {"stems": results}
        storage.update_job(job_id, status="done", stage="done", artifacts=artifacts)
        return artifacts
    except Exception as exc:
        storage.update_job(job_id, status="error", stage="error", error=str(exc))
        raise


@app.function(image=image, secrets=secrets)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile

    from pipeline import storage
    from pipeline.config import DEFAULT_STEMS, STEMS

    api = FastAPI(title="Band Transcriber")

    @api.post("/jobs")
    async def create(
        stems: str = Form(",".join(DEFAULT_STEMS)),
        url: str | None = Form(None),
        file: UploadFile | None = File(None),
    ):
        chosen = [s.strip() for s in stems.split(",") if s.strip() in STEMS]
        job_id = uuid.uuid4().hex[:12]
        if file is not None:
            data = await file.read()
            storage.create_job(job_id, "upload")
            process_job.spawn(job_id, file.filename or "upload", False, chosen, data, None)
        elif url:
            storage.create_job(job_id, "url")
            process_job.spawn(job_id, url, True, chosen, None, None)
        else:
            raise HTTPException(400, "Provide either a file or a url.")
        return {"job_id": job_id}

    @api.get("/jobs/{job_id}")
    def status(job_id: str):
        row = storage.get_job(job_id)
        if row is None:
            raise HTTPException(404, "Job not found.")
        return row

    return api
