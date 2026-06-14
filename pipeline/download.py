"""Acquire source audio and normalize it for the pipeline.

Two inputs: a local file (uploaded) or a URL (yt-dlp). Both end as a 44.1 kHz
stereo WAV, length-capped. yt-dlp from a cloud IP is frequently rate-limited or
blocked (see README) — pass `proxy` to route through a residential proxy.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .config import MAX_DURATION_SEC, TARGET_CHANNELS, TARGET_SR


class DownloadError(RuntimeError):
    """Raised when source audio could not be obtained (e.g. blocked URL)."""


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _normalize(src: Path, dst: Path) -> Path:
    """Transcode to capped 44.1 kHz stereo WAV."""
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", str(src),
         "-t", str(MAX_DURATION_SEC),
         "-ac", str(TARGET_CHANNELS), "-ar", str(TARGET_SR),
         "-vn", str(dst)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        size = src.stat().st_size if src.exists() else -1
        raise DownloadError(
            f"ffmpeg could not decode the input (exit {proc.returncode}; "
            f"input {size} bytes). {proc.stderr.strip()[-600:]}"
        )
    return dst


def from_url(url: str, workdir: Path, proxy: str | None = None) -> Path:
    """Download audio with yt-dlp, then normalize. Raises DownloadError if blocked."""
    raw = workdir / "source.%(ext)s"
    cmd = ["yt-dlp", "-x", "--audio-format", "wav", "--no-playlist",
           "--match-filter", f"duration < {MAX_DURATION_SEC + 60}",
           "-o", str(raw), url]
    if proxy:
        cmd += ["--proxy", proxy]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DownloadError(
            "yt-dlp failed (the URL may be blocked from this server's IP, "
            "geo-restricted, or too long). Try uploading the file instead.\n"
            + result.stderr.strip()[-500:]
        )
    downloaded = next(workdir.glob("source.*"), None)
    if downloaded is None:
        raise DownloadError("yt-dlp produced no output file.")
    return _normalize(downloaded, workdir / "input.wav")


def from_file(path: str | Path, workdir: Path) -> Path:
    """Normalize an already-local audio/video file."""
    src = Path(path)
    if not src.exists():
        raise DownloadError(f"Input file not found: {src}")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    return _normalize(src, workdir / "input.wav")


def fetch_audio(source: str, is_url: bool, workdir: Path,
                proxy: str | None = None) -> Path:
    """Single entry point used by the orchestrator."""
    workdir.mkdir(parents=True, exist_ok=True)
    wav = from_url(source, workdir, proxy) if is_url else from_file(source, workdir)
    if _probe_duration(wav) < 1.0:
        raise DownloadError("Decoded audio is empty or unreadable.")
    return wav
